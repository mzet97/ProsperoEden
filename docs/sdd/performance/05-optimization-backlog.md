# SDD Performance — 05 Optimization Backlog

Hipóteses priorizadas por evidência de código. Ordem = valor esperado ÷
(risco × custo de validação). Cada item vira no máximo um experimento
por vez (FR-004); o registro vive em 09. Nenhum item foi medido nesta
sessão — sem PS5 no ambiente.

## H-01 — Amostras de frametime por frame (pré-requisito, PERF-FR-003)

- Hipótese: um anel de intervalos por frame no relatório Vulkan permite
  P50/P95/P99/P99.9 reais e contagem de frames acima do orçamento.
- Gargalo: CEGO — hoje só há fps médio + worst por janela de 5 s e 5
  baldes (`graphics.cpp:639-656`); percentis são impossíveis [CONFIRMED gap].
- Proposta: histograma/anel por frame em `graphics.cpp`, emitido como
  `EDEN_VULKAN_FRAMES` junto ao `EDEN_VULKAN_FRAME`, desligável, sem
  alocação no caminho quente.
- Riscos: overhead por present; mitigação: anel estático + gate NFR-002.
- Benchmark: overhead medido por `EDEN_PERF_CLOCK_READ` + A/B on/off.
- Aceite: distribuições batem com série sintética; `check-performance.py` verde.
- Rollback: switch dev (default off até ACCEPTED).

## H-02 — Generalizar a block list do JIT para N jogos

- Hipótese: pré-compilar blocos listados elimina o stutter de primeira
  compilação em outros títulos como no jogo medido (426 vs 138.262
  compilações; 30,0 vs 22,3 FPS na janela — `jit_list.h:24-27`).
- Gargalo: compilação JIT em áreas novas [HYPOTHESIS p/ demais jogos].
- Proposta: sem código — medir 3+ títulos × frio/quente com `jit_list=on/off`.
- Riscos: lista de 12 MB por título; blocos fora dos módulos próprios
  excluídos por construção (`jit_list.h:13-18`).
- Benchmark: `EDEN_PERF_PROGRESS` compilations + fps/worst nas janelas iniciais.
- Aceite: ganho reproduzível ≥ banda em ≥2 títulos, sem regressão nos demais.
- Rollback: `jit_list=off` (default atual).

## H-03 — Causa raiz da lentidão do A32 fastmem (NÃO reativar ainda)

- Hipótese: o caminho page-table supera a janela de 4 GiB por alguma
  causa mensurável (TLB? alias? handler?) — `main.cpp:644-646`.
- Gargalo: DESCONHECIDO [NOT MEASURED]; reativação default: REJECTED.
- Proposta: instrumentar `EDEN_FASTMEM` por fase (faults, kernel_ns,
  maps/protects) em app 32-bit com `fastmem=on/off`; só então propor fix.
- Riscos: zero (medição sob switch existente).
- Aceite: causa identificada com contadores, ou hipótese registrada como
  INCONCLUSIVE em 09.
- Rollback: n/a (medição).

## H-04 — Varredura de `dispatch_draws` (lote do rasterizer)

- Hipótese: existe lote melhor que 64 draws para cenas pesadas; 8–512 já
  parametrizados (`performance.h:153-156`, `prepare-vulkan-port.py:93-98`).
- Gargalo: handoff worker (~16,7k/s, ~7 µs cada em cenas pesadas) [relato].
- Proposta: sem código — A/B 8/32/64/128/256/512 por cena, frio/quente.
- Riscos: lote grande aumenta latência de present; medir worst, não só média.
- Benchmark: fps/worst + `dispatch_ns`/`draws` por janela.
- Aceite: valor vence 64 em ≥2 cenas sem piorar worst em nenhuma.
- Rollback: `dispatch_draws=64` (default).

## H-05 — Varredura de `idle_spin_us` (wake-up entre núcleos)

- Hipótese: 100 µs não é ótimo para todos os jogos; hand-offs ~150/frame
  (`performance.h:147-152`; relato 55→59,6 FPS num racing).
- Proposta: sem código — A/B 0/25/50/100/200 µs; observar `idleN` + fps.
- Riscos: spin excessivo queima CPU do irmão SMT (mitigado pelo pinning
  exclusivo — verificar `EDEN_WORKER_PIN` no log).
- Aceite/rollback: como H-04, default 100 µs.

## H-06 — Varredura de `cache_spin` (locks tex/buf)

- Hipótese: 256 retries (~25 µs) não é ótimo global
  (`performance.h:63-80`; relato 1,5–3,2 ms/frame num mundo aberto).
- Proposta: sem código — A/B 0/64/256/1024; observar
  `cache_lock_contended/blocked` + `cpu_write_ns` + fps.
- Riscos: `cache_spin=0` volta ao upstream (comportamento conhecido).
- Aceite/rollback: como H-04, default 256.

## H-07 — Tempo de GPU por frame (pré-requisito Vulkan, R-09)

- Hipótese: `EDEN_GPU_TIME` (opt-in `gpu_time=on`,
  `prepare-vulkan-port.py:431-494`) separa gargalo GPU de CPU por submission.
- Proposta: validar o marcador contra `EDEN_DEV_GPU` deltas em 2+ cenas;
  documentar granularidade e overhead antes de qualquer experimento Vulkan.
- Riscos: queries de timestamp podem serializar; medir com on/off.
- Aceite: séries coerentes com present/dispatch; overhead desprezível.
- Rollback: `gpu_time` default off.

## H-08 — Curva de retenção do cache de shaders (antes de tocar no teto)

- Hipótese: o teto LRU de 64 MiB (`cache_budget.h:11-41`) causa
  evicção/recompilação mensurável entre sessões em alguns títulos.
- Proposta: instrumentação fria (contar entries/bytes/remoções por sessão
  em `TrimShaderCache`, fora do caminho quente) + medir; NÃO mudar o teto.
- Aceite: curva retenção × tamanho documentada; mudança de teto vira H-novo.

## H-09 — Gating do `RecordHle` (verificar antes de medir IPC)

- Hipótese: `RecordHle` sob `hle_mutex` global + mapa
  (`performance.cpp:360-370`) pode custar no caminho IPC se ativo em release.
- Proposta: auditoria de 1 dia — confirmar se chamadas são dev-only;
  se não, propor gate sem mudar semântica. Sem benchmark até confirmar.
- Estado: HYPOTHESIS.

## H-10 — `large_pages` / `sparse_tables` A/B

- Hipótese: huge pages (2 MiB, `memory_pages.cpp:42-47`) e tabelas
  esparsas (1 GiB economizado, `CMakeLists.txt:79-82`) têm custo/benefício
  mensurável por título via `large_pages=off` / `sparse_tables=off`.
- Proposta: sem código — A/B nos switches existentes; observar fps +
  `EDEN_PERF_HEAP` + faults.
- Riscos: zero (switches existentes, defaults mantidos).

## Explícitos NÃO-itens (REJECTED em 01, não reabrir sem dados novos)

- A32 fastmem default on; reverter `gc_keep_dirty`; `compute_barriers=off`;
  LTO global; pools CPU/GPU separados; mudar tetos sem medir retenção.
