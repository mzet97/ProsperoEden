# SDD Performance — 06 Test Strategy

## 1. Suítes existentes (reutilizar, não duplicar)

`make test` = `tools/build-headless-host.sh`: build host Release
(clang-18, sem LTO, sem Qt, `YUZU_TESTS=OFF`) + binários `eden-*-check`
+ scripts `tools/check-*.py` e `headless/check*.py`. Cobertura por área:

| Área | Checks host | Binários |
|------|-------------|----------|
| JIT /_dynarmic | `check-jit-allocator.py`, `check-jit-assert.py`, `check-jit-patch-lookup.py`, `check-jit-protection.py`, `check-exclusive-monitor.py`, `check-performance.py`, `check-startup-performance.py`, `check-nso-memory.py`, `check-tsc-fallback.py` | `eden-scalar-check`, `eden-memory-check` |
| GPU / Vulkan | `check-gpu-probe.py`, `check-gpu-producer-stop.py`, `check-gpu-sync-stop.py`, `check-native-gpu-thread.py`, `check-native-queue-probe.py`, `check-radv-native.py`, `check-hud.py`, `check-game-frame-summary.py`, `check-integer-buffer-clear.py` | — (console) |
| Memória | `check-heap-growth.py`, `check-sparse-header.py`, `headless/check_slab_lifetime.py` | `eden-memory-check` |
| Estabilidade | `check-crash-report.py`, `check-stop-limit.py`, `check-load-failure.py`, `check-nvdrv-process-lifetime.py`, `check-decoder-startup.py`, `check-game-capture-shutdown.py` | `eden-romfs-check`, `eden-devices-check`, `eden-mods-check`, `eden-settings-check`, `eden-patch-library-check`, `eden-update-check`, `eden-profiles-check`, `eden-ryujinx-check` |
| Threads | `check-worker-affinity.py` | — |

Fixtures sintéticas em `fixtures/`; nenhum teste exige ROMs, keys ou
firmware proprietários (regra 3.4 do master prompt).

## 2. Testes novos do programa de desempenho

| ID | O quê | Onde | Gate |
|----|-------|------|------|
| T-01 | Suite `tools/perf` (61 testes: + warmup/run, deltas c/ fronteira, per-interval, gate c/ evidência, tipos, banda, p99.9, vsync+half) | `tools/perf/test_*.py` | `python3 tools/perf/test_perf.py` verde |
| T-05 | Check estrutural do anel H-01 (dev-gating, limites, reset/janela, reset/sessão, budget × pipeline real) | `tools/check-frame-ring.py` | exit 0 no worktree; funciona sem build cache |
| T-02 | Percentis por frame vs série sintética (quando H-01 implementar) | novo `check-frame-percentiles.py` ou extensão de `test_perf.py` | paridade com cálculo manual |
| T-03 | A/B de switches dev sem console (parse + defaults) | estender `check-performance-settings.py` | defaults inalterados por experimento |
| T-04 | Regressão de JIT por experimento (proteção, allocator, monitor) | reutilizar T-01-lista JIT acima | todos verdes antes do A/B |

## 3. Divisão host × PS5

Host prova: lógica de parse/estatística, budgets JIT, W^X/allocator,
lifetimes, compilação cruzada, derivação por âncoras (falha fatal se o
Eden pinado mudar). Host NÃO prova: FPS, custo mprotect/alias no console,
comportamento RADV/WSI, páginas RX, afinidade real, pressão do pool,
timings de present (02 §5). Todo experimento termina em
REQUIRES_HARDWARE_VALIDATION até o A/B no console rodar.

## 4. Quality gates (promoção ao default)

1. `make test` + `tools/perf/test_perf.py` verdes.
2. Checks JIT/GPU da área tocada verdes.
3. Sem crashes/corrupção/erros gráficos novos conhecidos.
4. Ganho reproduzível além da variabilidade (IC quando variância alta).
5. Overhead de instrumentação calibrado (`EDEN_PERF_CLOCK_READ`).
6. Registro 09 completo + rollback documentado.
