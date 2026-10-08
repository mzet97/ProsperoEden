# ADR-001 — Instrumentação de desempenho de baixo overhead

- Estado: aceito (implementação de percentis pendente — H-01).
- Data: 2026-10-08.
- Contexto: `headless/performance.h`/`performance.cpp` + `graphics.cpp`
  já emitem janelas de 5 s (fps médio + worst), contadores cumulativos
  GPU/guest/HLE/JIT/fastmem e 24 APIs Vulkan opt-in (02 §1). Faltam
  amostras por frame (percentis impossíveis) e tempo de GPU por frame
  como série de primeira classe.

## Decisão

1. Reutilizar o sistema existente; instrumentação nova é aditiva, sob
   switch dev ou `EDEN_DEV_PROFILE`, desligável sem recompilar o default.
2. Produção nunca carrega `Timer`/`SampleCpu`/`cpu_state` nos caminhos
   quentes do JIT — imposto por `tools/check-performance.py:10-16`.
3. Sem logging síncrono por draw, sem alocações e sem locks novos no
   caminho crítico (NFR-002); overhead calibrado por
   `EDEN_PERF_CLOCK_READ`.
4. Cumulativos entram como deltas; séries sobrepostas nunca somam
   (`performance.h:210`); percentis só de amostras reais (FR-003).

## Consequências

- H-01 (anel por frame) e H-07 (`EDEN_GPU_TIME`) são pré-requisitos de
  qualquer experimento Vulkan/JIT quantitativo.
- Cada marcador novo ganha parser em `tools/perf/collect.py` + testes.
