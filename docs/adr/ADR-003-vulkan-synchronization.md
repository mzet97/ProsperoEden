# ADR-003 — Sincronização Vulkan conservadora

- Estado: aceito.
- Data: 2026-10-08.
- Contexto: backend Vulkan/RADV derivado por âncoras
  (`tools/prepare-vulkan-port.py`, `headless/vulkan.cmake`), com
  barreiras de compute default on (corrigiram LOD/culling —
  `dev_vulkan.h:25-29`), `hcr_mode=1` exato, conditional rendering on,
  handoff do rasterizer a cada 64 draws
  (`prepare-vulkan-port.py:93-98`) e `gc_keep_dirty` on com guarda de
  pool (`performance.h:92-127`).

## Decisão

1. Nenhuma barreira sai sem prova de correção no jogo afetado; o modo
   `compute_barriers=off` existe só como A/B de diagnóstico (dev).
2. `gc_keep_dirty` e uso-do-pool (`graphics_usage_from_pool`) não
   revertem (relato: 10 s a 3–9 FPS antes da correção).
3. Lotes (`dispatch_draws`), spins e tetos só mudam por varredura medida
   (H-04/H-06/H-08), comparando worst além da média — throughput não é
   latência.
4. Derivação continua por âncoras com falha fatal (`FATAL_ERROR`) quando
   o Eden pinado muda (R-06).

## Consequências

- Experimentos Vulkan exigem H-01 + H-07 prontos (ver antes de mexer).
- `sync_submissions` e `gpu_time` seguem opt-in de diagnóstico.
