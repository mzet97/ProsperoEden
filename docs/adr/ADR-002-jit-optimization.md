# ADR-002 — Otimização do JIT por variável única

- Estado: aceito (experimentos pendentes de console).
- Data: 2026-10-08.
- Contexto: Dynarmic A64 com `JitGroup` compartilhado por processo
  (`headless/dynarmic/shared-jit.cmake`, `jit_group.h`), batch ≤16
  blocos (`jit-compile-batch.inc:13`), budgets por núcleo
  (256/192/192/16 MiB A64 — `tools/check-performance.py:30-32`),
  W^X por alias RW/RX (`jit-permissions.inc`, `jit-alias.cmake`) e
  block list opt-in (`jit_list.h`).

## Decisão

1. Experimentos JIT mudam uma variável por vez (switch, budget, batch,
   lista) com A/B frio/quente e rollback imediato (FR-004).
2. Invariantes intocáveis sem estudo próprio: W^X, invalidação de
   blocos, coerência do monitor exclusivo, layout compartilhado
   (`EDEN_SHARED_JIT_LAYOUT`).
3. A32 fastmem segue desligado por padrão até H-03 identificar a causa
   raiz com contadores (`main.cpp:644-646`).
4. Não aumentar cache/batching sem evidência de ganho (regra 6.1).

## Consequências

- Todo experimento JIT roda os checks da área
  (`check-jit-protection/allocator/assert/exclusive-monitor`) + `make test`.
- Generalização da block list (H-02) é medição, não código, na primeira
  iteração.
