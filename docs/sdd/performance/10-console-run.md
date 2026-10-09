# 10 — Runbook do console (build dev + bundle diagnóstico)

Build de teste para PS5 com instrumentação `EDEN_DEV_PROFILE` (H-01 incluído),
que abre um título automaticamente, e o conjunto de logs a recuperar do console
para diagnóstico de desempenho e de fechamentos do jogo (alvo atual: TotK,
`0100F2C0115B6000`).

## 1. O que o build dev faz

- `make dev DEV_TITLE=<id>` gera `build/dev/PPSA99008` com `EDEN_DEV_PROFILE=ON`
  (`tools/build-package.sh`, modo `dev`): contadores de profiling, chaves A/B via
  `dev-settings.txt` e autoboot do título ([main.cpp](/var/mnt/4TB/TI/git/ProsperoEden/headless/main.cpp:384)).
- O jogo é procurado em `<pasta de jogos>/roms` e `/data/assets/roms` (`.nsp`/`.xci`
  cujo nome contenha o title ID ou cujo metadata bata) ([main.cpp](/var/mnt/4TB/TI/git/ProsperoEden/headless/main.cpp:457)).
  Pasta de jogos padrão: `/data/prosperoeden` (Settings > Game files); `keys/` e
  `firmware/` ficam nela ([assets_dir.h](/var/mnt/4TB/TI/git/ProsperoEden/headless/assets_dir.h:1)).
- Autoboot é desligado se a última execução deixou crash report (abre o launcher
  em vez de travar em loop) ou se `dev-settings.txt` tiver `launcher=first`.
  `rom=<TITLEID>` (20 chars) troca o título sem rebuildar; `replay=off` desliga o
  replay cronometrado de inputs (ligado por padrão no título dev; é o que torna a
  cena reproduzível para benchmark).
- H-01 (anel de 1024 frametimes + resumo `EDEN_VULKAN_FRAMES` a cada 5 s) vai para
  **stdout**, com `fflush` por janela: sobrevive a crash exceto milissegundos no pipe
  ([graphics.cpp](/var/mnt/4TB/TI/git/ProsperoEden/headless/graphics.cpp:686), [log_pipe.h](/var/mnt/4TB/TI/git/ProsperoEden/headless/log_pipe.h:1)).

## 2. Artefatos do CI

Workflow `Dev PS5 build` (`.github/workflows/dev-ps5.yml`, manual: Actions > Run
workflow, qualquer branch; `title_id` default TotK; `replay` on/off, default on):

- `ProsperoEden-dev-<TITLE>-<sha>.zip` (7 dias): pasta `PPSA99008`, entradas 0777.
- `...-symbols` (30 dias): `build/symbols/ProsperoEden-dev-....elf`, o executável
  não-stripado — **obrigatório** para simbolizar crash reports
  (`python3 tools/symbolize-crash.py <report> <elf>`, `docs/BUILDING.md` § Crash reports).
- `replay=off` grava `dev-settings.txt` (`replay=off`) dentro do pacote: build
  jogável (controle físico; `-noreplay` no nome). Benchmarks (A/A, B-000) usam
  `replay=on` (determinístico). Apagar o arquivo no console restaura o replay.

Primeira execução num fork é fria (~1 h em 4 cores); depois usa os mesmos caches
do workflow de release (~10 min).

## 3. Instalação

1. Fechar o ProsperoEden no console.
2. Extrair o ZIP e copiar a pasta `PPSA99008` para `/data/homebrew/PPSA99008`:
   - FTP: `python3 tools/install-ftp.py <PS5_HOST> <extraído>/PPSA99008`
     (precisa de servidor FTP no console, ex. ftpsrv, porta 2121);
   - USB: copiar a pasta; o app também monta de USB (ShadowMountPlus).
3. ROM do TotK em `<pasta de jogos>/roms/` com `0100F2C0115B6000` no nome do
   arquivo (ou metadata com o title ID); `keys/prod.keys` + `firmware/` na pasta
   de jogos.
4. Opcional: `dev-settings.txt` na pasta instalada (`/data/homebrew/PPSA99008/`):
   `launcher=first` (inspecionar launcher), `rom=<id>` (outro título), `replay=off`.
5. Desligar/reabrir: cada processo resolve a pasta de jogos uma vez (`assets_dir.h`).

## 4. Execução e fluxo de crash

1. Abrir o app: ele dá autoboot no TotK e rejoga inputs (replay ligado).
2. Jogar a cena combinada (ver §7); repetir por célula (frio/quente separados).
3. Se o jogo fechar: o próximo boot abre o launcher e anuncia onde está o report;
   os logs da execução que crashou são movidos para junto dele (`-stderr.log`,
   `-heap.log`, `-eden_log.txt`); os 5 mais novos são mantidos
   ([crash_report.h](/var/mnt/4TB/TI/git/ProsperoEden/headless/crash_report.h:62), BUILDING § Crash reports).
4. Congelamento sem report: reabrir o app preserva a sessão anterior em
   `*.prev.log` ([main.cpp](/var/mnt/4TB/TI/git/ProsperoEden/headless/main.cpp:224)).

## 5. Bundle diagnóstico (o que copiar de volta)

Pasta de logs: `/data/prosperoeden/logs` (com acesso FS; sem ele,
`/download0/eden-headless-g7`). Copiar via FTP:

| Arquivo | Origem | Conteúdo relevante |
|---------|--------|--------------------|
| `stderr.log` | stderr (sem buffer) | `Eden::Report`, superfície/display Vulkan, erros do loader ("Check this ROM…"), `EDEN_JIT_PRESSURE`, shutdown, avisos do crash handler |
| `heap.log` | stdout (buffer 64 KB + pipe async) | **tudo de perf**: `EDEN_VULKAN_FRAME/INTERVALS/FRAMES` (H-01), `EDEN_PERF_*`, `EDEN_DEV_GPU/GUEST`, `EDEN_FASTMEM`, `EDEN_WORKER_*`, `EDEN_STAGE`, diags do alocador JIT |
| `user/log/eden_log.txt` | frontend Eden | log próprio do Eden (loader, serviços, renderer) |
| `result.tsv` | boot | recibo de fases do startup |
| `crash-*.txt` + `-stderr/-heap/-eden_log` | crash handler | report + logs da execução que crashou |
| `*.prev.log` | rotação | sessão anterior (congelamentos) |

Refino do protocolo 09 §B-000 passo 2: no console não é preciso "salvar stdout" —
**stdout já é `heap.log`** ([main.cpp](/var/mnt/4TB/TI/git/ProsperoEden/headless/main.cpp:240)).

## 6. Do bundle ao pipeline

No host, a partir da pasta com os logs copiados:

```bash
cat stderr.log heap.log | python3 tools/perf/collect.py --run TOTK-<cena>-<frio|quente>-<n> > run.jsonl
python3 tools/perf/analyze.py --warmup-windows 1 run.jsonl > run.stats.json
```

(`collect.py` lê um fluxo de linhas; a ordem entre os dois arquivos não afeta
agregados nem janelas de frames, delimitadas pelos resumos `EDEN_VULKAN_FRAMES`.)
Crash: `python3 tools/symbolize-crash.py crash-....txt <elf do artefato -symbols>`.

## 7. Hipóteses TotK (investigação guiada pelos logs — NOT MEASURED)

Nenhuma conclusão sem evidência de runtime. Ao ler o bundle, procurar o sinal
distinguisher de cada uma:

- **H-Z1 — loader/keys/firmware**: `Core load failed` / `Loader status` em
  `stderr.log`, linhas de loader em `eden_log.txt`, ausência de `EDEN_STAGE …
  phase=first_frame_callback`. Distingue: falha antes do primeiro frame, sem
  marcadores de perf do jogo.
- **H-Z2 — memória/shaders (OOM, eviction, pipeline stall)**: `EDEN_PERF_DIRECT`
  `short=1`, `largest_free` em queda, `EDEN_VULKAN_COST`/criação de pipelines
  concentrada no crash, `EDEN_JIT_PRESSURE`. Distingue: degradação de memória
  nas janelas antes da queda.
- **H-Z3 — JIT/guest fault**: `EDEN_PERF_JITPATH/GUEST_PC` + PC do crash dentro
  da região JIT após simbolizar; `EDEN_PERF_PROGRESS` com `evacuations` altas.
  Distingue: PC simbolizado em código gerado, não no host.
- **H-Z4 — GPU/sync/apresentação**: esperas de fence/semáforo, `not_shown` alto
  com `frames` baixo, erros RADV em `stderr.log`. Distingue: CPU produzindo,
  GPU não apresentando.

## 8. Protocolo A/A + B-000 (resumo executável)

1. Passo 0 — A/A: mesmo binário, mesma célula, 2+ runs; `compare.py` run×run.
   Se |Δ| > ±2% com frequência, a banda não vale: alargar banda/runs e re-calibrar.
2. Por célula (frio/quente separados, ≥5 runs, A/B alternado quando houver candidato).
3. Anotar por run: jogo + Build ID, vídeo (backend/resolução), cena/inputs,
   firmware, runtime, temperatura aproximada, `make deps-status` do build,
   `EDEN_DEV_SETTINGS` do log.
4. `incomplete_excluded` ≈ 0; overflow H-01 > 0 invalida a conclusão global
   (`inconclusive`, exit 3) — re-rodar janelas longas em sessões curtas.

Registros em `09-results.md`, um bloco por otimização (formato §15 do master prompt).
