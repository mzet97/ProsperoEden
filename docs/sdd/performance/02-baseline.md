# SDD Performance — 02 Baseline

Estado: instrumentação inventariada no código; **nenhuma medição numérica
coletada** — sem PS5 neste ambiente. Este documento é a especificação do
baseline a executar no console + o framework `tools/perf/` (testado no host).

## 1. Inventário da instrumentação existente

### 1.1 Contadores de frame (janelas de 5 s, fps médio + worst)
| Marcador | Onde | Conteúdo |
|----------|------|----------|
| `EDEN_DEV_FRAME` | graphics.cpp:277 | dev: frames/s/fps/worst_ms/total |
| `EDEN_GAME_FRAME` | graphics.cpp:294 | release: idem |
| `EDEN_VULKAN_FRAME` | graphics.cpp:647 | + not_shown + clock_hz |
| `EDEN_VULKAN_INTERVALS` | graphics.cpp:654 | 5 baldes (v1/v2/v3/v4plus/half) |
| `EDEN_VULKAN_FRAMES` | graphics.cpp:645-680 (H-01) | n/overflow/budget_ms + ms CSV por frame (dev) |

Semântica H-01b (CONFIRMED): cada intervalo vai de um retorno de
`RendererVulkan::Composite` ao seguinte, na GPU thread
(`SCOPE_EXIT { OnFrameDisplayed(); }` no Eden pinado; o `return`
antecipado do `SkipFrame` passa pelo guard —
`prepare-vulkan-port.py:547-551`). São intervalos de **produção de
frames pelo guest**, incluindo frames que o display não mostrou
(`not_shown` conta-os à parte na mesma janela); não é tempo de
submissão (esse é `EDEN_GPU_TIME`) nem fótons-no-display. O anel usa
exatamente o evento que já alimenta fps/worst — consistência por
construção. `budget_ms` = 1e6 ÷ `game_millihertz` (relógio vsync do
jogo: 60000, ÷ swap_interval ÷ speed_scale; 0 = desconhecido).

Caveat H-01d (30 FPS): o vsync clock publica 30000 para jogos com
swap_interval=2 (orçamento 33,33 ms correto), mas um jogo travado
internamente em 30 FPS com swap_interval=1 publica 60000 — e seus
frames normais de ~33 ms seriam misflagged contra 16,67 ms. Qual caso
vale por título NÃO é decidível estaticamente: `over_budget`/`over_2x`
são **diagnóstico** (veredito INFO, nunca gate) até a validação no
console. Critério por título em B-000: mediana dos frames ≈ budget ⇒
semântica válida; mediana ≈ 2× budget com intervalo 1 ⇒ título com cap
interno, budget segue diagnóstico. P99 exige n grande para
estabilidade — o relatório mostra contagens de amostras (proveniência)
para calibrar a leitura; desconfiar de p99 com poucas centenas de
amostras.
| `EDEN_LOADING_DONE` | graphics.cpp:248,618 | frames/s de loading |
| `EDEN_GAME_VISIBLE` | graphics.cpp:252 | 1º frame visível |
| `EDEN_PERF_GPU_FRAME` | performance.cpp:309 | frame + mono/cpu clocks |

Lacuna em fechamento: H-01 implementa o anel por frame + `frame_samples`
em `tools/perf` (percentis reais quando o marcador existe); compilação e
validação no console pendentes (09). Sem o marcador, percentis seguem
impossíveis → PERF-FR-003 continua aberto até o primeiro A/B com amostras.

### 1.2 GPU / guest / HLE (cumulativos; analisador tira deltas)
| Marcador | Onde | Conteúdo |
|----------|------|----------|
| `EDEN_DEV_GPU` | performance.cpp:424 | idle/dispatch/drain/present/full/draws |
| `EDEN_DEV_GUEST` | performance.cpp:432 | cpu_write/read, sync, dequeue, ipc, cache_lock, fs file/storage, jit r/w/x por núcleo, idle 0-2, cond[20] |
| `EDEN_DEV_HLE` | performance.cpp:393 | comandos ≥1 ms (service/cmd/calls/ns) |
| `EDEN_VULKAN_COST` | performance.h:230 | 24 APIs opt-in (não somar: sobrepõem) |
| `EDEN_GPU_TIME` | dev_vulkan.h:19 | tempo de execução de submissions (opt-in `gpu_time=on`) |
| `EDEN_DEV_DRAW/QUEUE` | graphics.cpp:271-276 | draws e fila no ponto de 5 s |

### 1.3 JIT / fastmem / memória / workers
| Marcador | Onde | Conteúdo |
|----------|------|----------|
| `EDEN_PERF_JIT` | performance.h:251 | compilações/compile_ns/evicções por núcleo |
| `EDEN_PERF_JIT_PROTECTION` | performance.h:258 | proteção de páginas RX |
| `EDEN_PERF_DUPLICATES` | performance.cpp:669 | blocos first/again + 6 faixas de lead (dev `jit_dups=on`) |
| `EDEN_PERF_JITPATH` | performance.cpp:678 | dispatch/lookup/hits |
| `EDEN_PERF_PROGRESS` | performance.cpp:682 | compilações + fases por núcleo |
| `EDEN_FASTMEM` | performance.cpp:460 | janela, páginas, chunks, direct r/w, faults, maps/unmaps/protects, kernel calls/ns, falhas |
| `EDEN_PERF_HEAP/DIRECT` | performance.cpp:383,413 | arenas, committed, sparse, total/largest_free/free/regions/short |
| `EDEN_WORKER_*` | performance.cpp:180-210 | topologia, placement, pinos |
| `EDEN_PERF_CLOCK*` | performance.cpp:801-817 | TSC válido?, custo de 100k leituras |
| `EDEN_SHADER_CACHE_LOADED` | main.cpp:1244 | marco nu (sem estatísticas) |
| `EDEN_DEV_SETTINGS` | main.cpp:816 | eco dos switches A/B ativos |

Overhead: `Timer` = 2 leituras de relógio (`performance.h:192-208`); custo
quantificado por `EDEN_PERF_CLOCK_READ`. Produção sem `Timer`/`SampleCpu`/
`cpu_state` nos hots paths do JIT, imposto por teste
(`check-performance.py:12-16`) [CONFIRMED].

## 2. Métricas obrigatórias do baseline

CPU: uso por núcleo/thread (`EDEN_PERF_WORKER/CPU_POINT`), compile_ns por
núcleo e por fase, blocos compilados, invalidações/evicções, contenção
(`cache_lock_contended/blocked`), idle (`idleN=calls/ms/sleeps`), HLE ≥1 ms.
GPU: `EDEN_DEV_GPU` deltas, `EDEN_VULKAN_COST` por API (opt-in, sem somar),
`EDEN_GPU_TIME`, fences/semáforos/present (`fence_wait/semaphore_wait/
present_sync`), `pipeline_ready_wait`, `shader_*`, GC (`texture_gc`,
downloads), `EDEN_PERF_DIRECT` (pool).
Frame pacing: fps médio/mínimo, P50/P95/P99/P99.9 (após PERF-FR-003; até lá:
fps + worst + `EDEN_VULKAN_INTERVALS` por janela de 5 s), frames acima do
orçamento, loading (`EDEN_LOADING_DONE`, `EDEN_GAME_VISIBLE`).

## 3. Protocolo de medição

1. Fixar: jogo + Build ID, vídeo (resolução/filtro/docked), cena e inputs
   (preferir replay cronometrado; `replay=off` só se documentado),
   firmware, runtime, `deps-status`, temperatura aproximada.
2. Células: cache FRIO (RADV + disco limpos) e QUENTE (pré-aquecidos)
   analisadas separadamente; dev (`EDEN_DEV_PROFILE`) para contadores
   profundos, release para números finais sem diagnóstico intrusivo.
3. ≥5 execuções comparáveis por célula; ordem A/B alternada; janelas de 5 s
   descartando warmup (marcar `EDEN_GAME_VISIBLE` como t0 da cena).
4. Coletar stdout completo + `EDEN_DEV_SETTINGS` + `deps-status` no cabeçalho.
5. `tools/perf/collect.py` importa e valida (linhas ausentes/quebradas
   invalidadas por janela, nunca interpoladas); `analyze.py` calcula
   estatísticas; `compare.py` emite Markdown + JSON com veredito por métrica.
6. Triagem: regressão ≥2% em métrica crítica → investigar; ganho só vale se
   exceder materialmente a variabilidade (IC quando variância alta).
7. Limitações registradas no relatório (modelo em 09).

## 4. Layout do `tools/perf/`

```text
tools/perf/
    README.md          # uso: importar → analisar → comparar
    collect.py         # stdin/arquivos → JSONL validado (parse EDEN_*)
    analyze.py         # JSONL → estatísticas (deltas, fps, baldes)
    compare.py         # CLI + reports (usa compare_metrics.py)
    compare_metrics.py # specs, vereditos por métrica, gate
    test_perf.py       # suite (34 testes, stdlib apenas, host)
    test_collect.py test_analyze.py test_compare.py
```

Regras: cumulativos (`EDEN_DEV_GPU/GUEST`, `EDEN_VULKAN_COST`) entram como
deltas entre relatórios consecutivos; séries sobrepostas nunca somadas;
percentis só de amostras reais (`statistics.quantiles`, n=100); janelas
incompletas marcadas `complete=false` e excluídas das comparações.

## 5. Divisão host × PS5

Host (executável aqui): `make test`, `tools/check-*.py`, `test_perf.py`,
lógica de parse/estatística, compilação cruzada. Host NÃO prova: números de
FPS, custo mprotect/alias, comportamento RADV/WSI, páginas RX no console,
afinidade real, pressão do pool, timings de present.
PS5 (pendente): todos os números de 02-§2, calibração de overhead da
instrumentação nova, validação A/B de cada hipótese do backlog.

## 6. Resultados do baseline

| Rodada | Data | Build | Jogo/cena | Estado |
|--------|------|-------|-----------|--------|
| B-000 | — | — | — | PENDENTE (sem console) |

Preencher via `compare.py --init-baseline`; histórico vive em 09.
