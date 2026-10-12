# notes.md — ProsperoEden: achados e estado de trabalho

> Notas vivas para agentes. Fonte canônica de resultados: `docs/sdd/performance/09-results.md`.
> Última atualização: 2026-10-12. Meta ativa: `faça esse plano e garanta resolve
> todos os erros` — 75%, pausada como bloqueada (aguarda repro no PS5).

## 1. O que é este projeto

ProsperoEden = fork do emulador Eden (Switch, ARM→x86-64 via Dynarmic JIT +
Vulkan/Mesa RADV) adaptado para rodar como payload no PlayStation 5.
Metodologia: SDD (MEASURE → UNDERSTAND → SPECIFY → IMPLEMENT → VERIFY).
Nunca fabricar FPS; conclusões marcadas CONFIRMED / HYPOTHESIS / NOT MEASURED / REJECTED.

## 2. Diagnóstico atual: freeze do inventário no TotK

- Jogo-alvo: Zelda TotK `0100F2C0115B6000`.
- Sintoma: trava ao abrir/navegar inventário/menu (build `.110`).
- Evidência (`/home/mzet/Downloads/`, sessão 310–345 s):
  - gap de 42 s sem frames + tempestade ~43k `Unmapped Read64 @ 0x8` (~1200/s);
  - gameplay 18–27 FPS dispatch-bound; textura 5.72 GB > orçamento crítico 5.58 GB,
    free até 851 MB; sem `mapping rejected`, sem asserts, sem OOM;
  - trigger candidato: burst 14x `Weapon_*.png 0x202` (TOTK Optimizer + UltraCam mods).
- Identidade do leitor nulo: NOT MEASURED — um repro no console resolve.

## 3. Tracer em main (TRACER-01)

- `main @ 8fd18e4` (merge PR #8): bloco dev-only em `headless/CMakeLists.txt` que
  injeta na função `Read64` do core um log throttled:
  - `EDEN_UNMAPPED_TRACE` (primeiros 8, thread + guest backtrace) + `EDEN_UNMAPPED_TOTAL` (1/8192);
  - `try/catch` + atômicos para não travar a log pipe nem o caminho `noexcept`.
- Convenção crítica (não quebrar): gate **só na camada CMake** (`if(EDEN_DEV_PROFILE)`).
  `EDEN_DEV_PROFILE=1` é definido apenas para o target `eden-headless`; o `#ifdef`
  interno foi removido porque o core lib compila sem a macro (0 strings no ELF).
- Build local verificado: `BUILD-EXIT=0`, `REBUILD-EXIT=0`, 2 strings em `llvm-pie.elf`.
- ZIP jogável `replay=off` pronto (não commitado): `dist-dev/ProsperoEden-dev-0100F2C0115B6000-tracer-local.zip` (67 entradas).

## 4. Pendências (ordem)

1. **Repro no PS5 (usuário)**: Exp. A (mods off, inventário 3x) OU instalar o ZIP
   tracer. Retornar `heap.log`, `stderr.log`, `user/log/eden_log.txt`,
   `boot-trace.txt`, `crash-*` + veredito travou/não-travou.
2. Com os logs: identificar leitor via `EDEN_UNMAPPED_TRACE` (ou isolar mod) → fix final.
3. Ao fazer o fix: carregar skill `bundled:durable-test-collateral` (teste focado junto).
4. Verificação: 3+ repros + CI verde; registrar em `09-results.md`.
5. Limpeza posterior: deletar draft releases `dev-totk-4306984`, `dev-totk-noreplay-50be9cb`.

## 5. Infra e comandos

- Build local: distrobox `eden-build` (ubuntu:26.04, `/var/mnt` montado, 24 cores).
  Host Fedora/Bazzite sem toolchain — nunca instalar toolchain no host.
- `replay=off` = jogável (input do controle); `replay=on` = benchmark determinístico.
- CI: `gh run list -R mzet97/ProsperoEden --workflow toolchain.yml`,
  `gh run view <ID> --log-failed`. Gate: toolchain + perf-static + make-test.
- Pipeline: `cat stderr.log heap.log | python3 tools/perf/collect.py --run R > r.jsonl`
  → `python3 tools/perf/analyze.py --warmup-windows 1 r.jsonl > r.stats.json`.
- Testes: `python3 tools/perf/test_perf.py` (61/61), `python3 -B tools/check-frame-ring.py`.

## 6. Riscos abertos

- Textura acima do crítico + free 851 MB: pressão real, OOM em sessão longa não descartado.
- Gameplay dispatch-bound a 2160p+FSR: precisa settings sweep após o freeze.
- JIT emit 81–82% do compile + contenção 23x do alocador: candidatos H-02 futuros.

## 7. Achados 12/out — sessão com 4 OOMs (journal: `.debug-journal.md`)

Logs novos em `/home/mzet/Downloads/` (stderr + heap + eden + boot-trace, 09:04).
Round 1 decisivo, 4 hipóteses julgadas:

- **H2 VAZAMENTO ENTRE SESSÕES — CONFIRMED (causa primária).** `capacity`
  (maior bloco livre no início da sessão): 7.44 → 5.98 → 5.54 → 3.00 → 2.26 →
  1.59 GB em 6 loads no mesmo processo; replicado no processo anterior
  (7.44 → 5.56 GB em 1 ciclo). Heap `pieces` cresce +~130 MB/sessão e nunca
  encolhe — explica só parte dos 0.5–2.5 GB/ciclo; o resto NOT MEASURED.
  Shutdown limpo e shutdown pós-OOM executam a mesma sequência
  (`gpu_core.reset()` em ambos) — o retentor está fora da sequência de teardown.
- **H1 PRESSÃO GENUÍNA — CONFIRMED (contribuinte).** Textura 3.2 → 5.3 GB vs
  crítico 5.58 GB (`memory_short=1`); regions 41 → 377; OOMs em
  `vulkan_memory_allocator.cpp:261 CreateBuffer` (1x) e `:224 CreateImage` (3x),
  `VkResult=-2`. Settings: 2x + FSR + framegen 2x @ 2160p.
- **H3 ASSERTS memory.cpp:563 — REFUTED como causa do OOM.** Burst único de boot
  (2096x em 17.85–19.49 s, `nullptr within the table` + `Mapped memory page
  without a pointer @ 0x1154410000`); OOMs minutos depois. Bug separado, a corrigir.
- **H4 BUILD ANTIGO — REFUTED.** Tracer disparou 1x (`thread=ARes Loading 0`,
  `@ 0x30`); build tracer instalada e funcional. Storm @ 0x8 NÃO reproduziu.
- Processo anterior (pid 331) morreu no meio do shader cache (stderr.prev termina
  em `2126 of 2985`, sem teardown) — crash/kill durante load, sem `crash-*` anexado.
- `result.tsv` = 0 bytes (build `replay=off` não produz resultado de benchmark).

Próximo (Passo 6): (a) usuário testa 1x + framegen off (toggle confirmatório do H1,
sem código); (b) código: medir o retentor de GBs entre sessões antes de qualquer
fix (candidatos: guest-RAM backing, pools do alocador Vulkan, JIT, mirrors do
shader cache) — NÃO adivinhar o fix (skill invariant #1).

## 8. Diagnóstico H3 embarcado (12/out, Passo 6)

- Mecanismo do assert storm fechado no estático: `PageEntryData` só representa
  45 bits → `Pointer()==null ⟺ host_ptr<0x1000`; `MapPages` calcula
  `host_ptr=GetPointer(target)−(base<<12)` e `GetPointer` não tem bounds-check.
  2096 nulls consecutivos ⟹ hipótese forte: backing de device memory mapeado em
  endereço host baixo. Falta 1 medição no console (base/target/devptr).
- Embarcado `EDEN_MAP_NULL` (primeiros 4 + `EDEN_MAP_NULL_TOTAL`/1024), dev-only
  via CMake, self-sufficient (próprio `<atomic>`), sem dependência de ordem.
- H3 refinado sem console: `Out of bounds target` = 0 ocorrências ⟹ variante
  underflow (target<DramBase) EXCLUÍDA; resta backing baixo como único mecanismo
  consistente. 2096 páginas = 1 único Map de ~8 MB (guest 0x1154410000) via
  caminho genérico do kernel (`k_page_table_base.cpp:5755/5806`, Map/MapGroup) —
  sem bug visível no caller. Coincide com fault do `ARes Loading 0` @ 18.38 s.
- Check mantido `tools/check-map-null-diag.py` (red→green observado, 56 LOC):
  pin único no mirror pinado por UPSTREAM.json + estrutura + snippet balanceado;
  wired em `tools/build-headless-host.sh` (full, com deps) e `perf-static` (estrutural).
- Build local `DEV-EXIT=0`; 2 strings em `eboot.bin`; novo ZIP 67 entradas com
  `replay=off` (atenção: `make-dev-dist.py` faz `rmtree` em `dist-dev/` — o ZIP
  tracer anterior foi substituído; o novo contém AMBOS os diagnósticos).
- Heap ratchet refinado: consumo real/ciclo = +1 piece (128 MiB), bate com queda
  do free total; resto é fragmentação pinada. Heap "não devolve" por design
  (`heap_arenas.inc`). Retentor residual: NOT MEASURED. `check-heap-growth.py`
  é o harness mantido para o futuro fix do heap.
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-mapnull-local.zip`
  + símbolos em `build/symbols/` (guardar junto para simbolizar crashes).

## 8b. H3 — árvore de decisão do fix (aguarda EDEN_MAP_NULL)

- SE `devptr ≈ base` (backing baixo confirmado): fix = garantir backing de
  device memory em endereço host alto (opção B, principiada) OU fallback limpo
  no MapPages p/ host_ptr irrepresentável (opção A, sintomática). Decidir pelo
  custo após ver os valores.
- SE `devptr` alto mas `hostptr<0x1000` mesmo assim: reabrir mecanismo (matemática
  atual não fecha) — NÃO aplicar fix.
- SE `target < DramBase`: underflow real (assert irmã deveria ter pego) —
  investigar caller (kernel Map) antes de qualquer fix.

## 9. Retentor residual estreitado (12/out, sem console)

- Série `[ps5-opengl-heap]` (já nos logs): fim de sessão 7→14→20→27→34 MB e
  460k→909k→1366k→1827k→2292k blocos — delta CONSTANTE +7 MB/+450k por ciclo em
  sessões de 19–190 s ⟹ per-cycle, gameplay excluída (s1 já prova).
- Contadores do heap auditados e CORRETOS (todos os paths dão charge;
  `ambiguous_zero_reallocs=0`) ⟹ números confiáveis.
- Load contribui só +20k; +450k acumulam na sessão e PLATEAU ⟹ acumulador com
  capa (~16 B/bloco em média) ⟹ pinning extremo do heap ⟹ +1 piece/ciclo.
- Rasterizer EXCLUÍDO como dono persistente (`gpu_core` resetado por ciclo).
  Suspeito principal (HIPÓTESE): estrutura recarregada idêntica por ciclo e nunca
  liberada. Falsificador: 2 loads de workload minúsculo (homebrew) — delta deveria
  colapsar se for específico do load do TotK.

## 10. Sessão 1x + framegen-off (12/out 10:04) — vereditos

- **1X-01: settings INSUFICIENTES (INCONCLUSIVE→fix de código obrigatório).**
  s1 2x quit sem OOM; s2 1x OOM em ~110 s (CreateImage); s3 1x OOM em ~8 s
  (CreateBuffer, capacity inicial 2.13 GB). Capacities 7.44→5.67→2.13 GB.
  Framegen OFF confirmado (sem linha `launch: Frame generation`); FSR ainda ON.
  O leak per-cycle domina: a s3 morreu em 8 s por começar pobre, não por pressão.
- **BOW-01: erros do arco+item IDENTIFICADOS (não-fatais).** Upload GPU de 68 KB
  (@ 0x869ef000) com tail 28 KB unmapped (7 págs 0x869f9000–0x869ff000) → zeros
  na textura (ReadBlockUnsafe memset 0). Determinístico: mesmo endereço em 3
  processos. Coincide com bursts de `/icon/Weapon_*.png` (252.25 s vs fault
  252.21 s — o fault precede os ícones: é o asset do menu). Causa raiz do gap
  GMMU (over-read de size vs páginas perdidas) INDECISA — precisa diagnóstica
  dedicada ou comparação upstream. GMMU sem patches do port (Eden puro).
- **H3: sem trigger (0 asserts)** — burst é ASLR-dependente (guest vaddrs
  variam por boot); 0 MAPNULL esperado, sem perda de dados.
- **Build-id STALE descoberto**: `__DATE__/__TIME__` da TU main.cpp não
  recompilada → mesmo stamp 07:53:53 em builds diferentes. Corrigido:
  `build-id.txt` (sha + clean/dirty, sem timestamp, determinístico) escrito por
  `make-dev-dist.py` + logado no boot-trace (`build id: ...`) + check
  `tools/check-build-id.py` (red-no-HEAD→green, wired no perf-static).
- Leak replicado 3º processo: s1→s2 +8 MB/+519k blocos. Assinatura mantida.
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-buildid-local.zip`
  (68 entradas: +build-id.txt, replay=off, ambos diagnósticos).

## 11. Round 5 — GMMU + regressão do tracer + armadilha ccache (12/out)

- **GMMU-01 EMBARCADO**: `EDEN_GMMU_GAP` (site safe/unsafe via
  `__PRETTY_FUNCTION__`, verificado no clang-18 + teste direto) + TOTAL/512,
  pin duplo (safe+unsafe) em header derivado (precedente slab_helpers), check
  `tools/check-gmmu-gap-diag.py` red→green, wired nos 2 gates.
- **REGRESSÃO DO TRACER ACHADA E CORRIGIDA**: merge 8fd18e4 re-adicionou
  `#ifdef EDEN_DEV_PROFILE` interno; core compila SEM a macro (provado via
  compile_commands.json: NO-DEF) ⟹ tracer morto em main desde o merge.
  Branch 8426da4 (build 07:58) não tinha o ifdef ⟹ TRACE disparou na sessão
  09:04. Fix: ifdef interno removido (gate só no CMake) + check
  `tools/check-unmapped-tracer.py` (falha no HEAD, verde na árvore) wired.
- **ARMADILHA CCACHE+NINJA (documentar!)**: (1) ninja não recompila TU cujo
  depfile aponta o header ORIGINAL (derived novo é invisível); (2) ccache
  depend-mode serve .o stale mesmo após `rm` (manifesto antigo não lista o
  derived). Sequência correta p/ header derivado novo: `rm` o .o + rebuild
  com `CCACHE_RECACHE=1` (juntos!). Verificação obrigatória: `strings` no
  eboot (6 strings: GMMU×2 + MAPNULL×2 + UNMAPPED×2 — CONFIRMADO neste build).
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-full-local.zip`
  (68 entradas, replay=off, build-id, TRÊS diagnósticos verificados).

## 12. Exp. A + fix H3 (12/out 11:31)

- **BOW = MODS (ISOLADO)**. Sem mods + 1x: arco+bomba FUNCIONAM. ReadBlocks
  persistem mas REDUZIDOS (21→7, 1 evento) e sem impacto visível.
- **GMMU-01 DECISIVO**: `site=unsafe addr=0x869ef000 size=69632 mapped=10/17
  first_bad=0x869f9000` — tail limpa (over-read de size), path unsafe (Linear/
  buffer, sem flush). Benigno sem mods ⟹ SEM fix de código (risco de regressão
  em size calc sem benefício); documentado.
- **MAPNULL DECISIVO**: `base=0x11af600000 target=0x16f400000
  devptr=0x11af600000 hostptr=0x0` — backing baixo CONFIRMADO (devptr==base
  exato). Opção A da árvore §8b executada.
- **H3-FIX APLICADO**: assert per-page → warning throttled (primeiros 4), store
  idêntico, incondicional (spam atinge todo build). Check estendido red→green.
  Build DEV-EXIT=0; eboot: 6 diagnósticos + H3WARN×1 + assert antiga×0.
- **LEAK MODS-INDEPENDENTE**: +8 MB/+561k blocos por ciclo sem mods (até MAIOR).
  OOMs s2 234 s + s3 159 s (CreateBuffer). Prebuild roda PÓS-game_loaded ⟹ o
  +1M de blocos criados no início da sessão INCLUI os 2985 pipelines
  (~188 blocos/pipeline retidos?) — suspeito principal.
- Falsificador pendente: 2º título (ou homebrew) — decide TotK-específico vs
  genérico per-cycle.
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-h3fix-local.zip`
  (68 entradas, replay=off, build-id, 3 diagnósticos + fix H3).

## 13. Reframe OOM + census (12/out 11:59, sem console)
- heap.log minerado (82 heap samples, 60 DIRECT, 20 TEXTURE_BUDGET): OOM é bleed
  WITHIN-session (pool 3.5→0.54 GB, recovery limpa no shutdown 0.68→4.67);
  retenção cross-session ~200 MB (pieces, by design). s2 = throw
  OUT_OF_DEVICE_MEMORY (stderr); s3 morreu no shutdown.
- "Texture usage" 5.59>5.58 GB critical é POOL (6 GB − largest_free), não
  texturas! GC pressionado por heap/guest/driver. Texture-actual NOT MEASURED.
- Heap: 610M/30k→1446M/2.6M na sessão (System, liberado); sobreviventes globais
  +560k×17B/sessão LINEAR (560k→1120k→1684k). JitGroup EXONERADO (flat_map);
  accounting auditado OK; memory_pages/host_memory limpos. Dono NOT MEASURED.
- CENSUS BUILD: TEXTURE_BUDGET += images/dirty/image_bytes (1 walk LRU/300f) +
  EDEN_JIT_GROUPS pós-shutdown. 6/6 checks; eboot com tudo + H3WARN×1.
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-census-local.zip`
  (67 entradas, replay=off default p/ TotK, build-id `8fd18e4 dirty`).
  H3FIX SUPERSEDED — instalar este.
- Próximo: 1 run console (2 sessões em sequência) → silêncio H3 + dono do bleed
  + veredito 560k.

## 14. CENSUS-01 resultados + fix GC-SHIELD (12/out 12:25, console)
- H3 SILÊNCIO CONFIRMADO: 0 asserts, 4 warnings (cap). H3-FIX VERIFIED.
- Bleed particionado: +2.18G/sessão = +1.11G texturas (3511→6957 imgs) + ~1.1G
  não-textura (heap +837M). Dirty 1673→750 (GC evicta sob pressão) mas total
  sobe ⟹ evicções efetivas < alocações.
- Grupos EXONERADOS: alive=0 ×3. Sobreviventes 571k→1157k→1741k (ainda sem dono;
  10 MB/sessão, não é o OOM).
- GC-SHIELD (mecanismo): budget conta VISITAS; skips queimam e param o scan;
  keep_dirty forma shield no head LRU. FIX: conta evicções, scan cap 8192,
  gc_scan=upstream restaura. Decisões de evicção inalteradas.
- ZIP atual: `dist-dev/ProsperoEden-dev-0100F2C0115B6000-8fd18e4-gcscan-local.zip`
  (+ traced-cap). CENSUS SUPERSEDED.
- Próximo: run console → images/usage achatam? + dono heap +840M.

## 15. Controle morto = replay timed (12/out 13:44, estático)
- Dev local define ROM_ID == PROFILE_TITLE == DEV_TITLE ⟹ main.cpp:1500 liga o
  TIMED REPLAY sem replay=off — e aí pad->Poll() é pulado (controle morto,
  TotK parado: script sem inputs p/ TotK). NÃO é regressão do fix GC.
- Gap: CI -noreplay injeta replay=off; pacote local nunca injetou. Runs antigos
  funcionaram por leftover no app folder; install limpo perdeu → replay on.
- FIX: build-package.sh (dev) injeta replay=off pós-freeze (= CI) +
  check-dev-playable.py. ZIP gcscan reempacotado (mesmo nome + dev-settings).
- Validar: run com controle + 4 logs.
