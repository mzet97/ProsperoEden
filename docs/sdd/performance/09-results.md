# SDD Performance — 09 Results

Registro append-only de experimentos. Um registro por experimento, uma
mudança por experimento (FR-004). Decisões: ACCEPTED, REJECTED,
INCONCLUSIVE, REQUIRES_HARDWARE_VALIDATION.

## Template

```text
Optimization ID: H-NN (backlog 05)
Subsystem: JIT | Vulkan | threads | memory | instrumentation
Hypothesis: ...
Evidence: contadores/arquivo:linha que motivaram
Baseline commit: ...
Candidate commit: ...
Environment: jogo + Build ID, cena, vídeo, firmware, runtime, deps-status, temp
Configuration: dev-settings.txt exato + perfil
Test cases: células frio/quente, runs, ordem A/B, warmup descartado
Number of repetitions: ...
Baseline results: report.json/md (anexar)
Candidate results: report.json/md (anexar)
Measured difference: métricas críticas + banda ±2%
Variance/uncertainty: stdev, overlap, IC quando aplicável
Correctness results: make test, checks da área, T-01..T-04
Compatibility risks: ...
Decision: ACCEPTED | REJECTED | INCONCLUSIVE | REQUIRES_HARDWARE_VALIDATION
Rollback procedure: switch ou revert do commit
```

## Log de experimentos

| ID | Data | Subsistema | Decisão | Resumo |
|----|------|------------|---------|--------|
| ENV-00 | 2026-10-08 | toolchain/host | INCONCLUSIVE (gate bloqueado) | Fedora 44: clang-18 ausente, 14/14 deps missing, `make test` não executável; `tools/perf` 40/40 + `check-frame-ring` PASS |
| H-01 | 2026-10-08 | instrumentação | REQUIRES_HARDWARE_VALIDATION | anel por frame dev-only + `frame_samples` + gate p95; sem PS5 e sem build aqui |
| H-07 | 2026-10-08 | instrumentação | REQUIRES_HARDWARE_VALIDATION | semântica `EDEN_GPU_TIME` validada no código; coerência no console pendente |
| ENV-01 | 2026-10-08 | CI/ambiente | INCONCLUSIVE (1ª run pendente) | workflow toolchain + estáticos em ubuntu-26.04; YAML validado, runs locais verdes |
| H-01a | 2026-10-08 | instrumentação | REQUIRES_HARDWARE_VALIDATION | overflow→`partial`, vereditos frame bloqueados; reset/janela imposto por check |
| H-01b | 2026-10-08 | instrumentação | ACCEPTED (docs-only) | intervalos = produção guest via Composite (incl. skipped); sem mudança de código |
| H-01c | 2026-10-08 | instrumentação | REQUIRES_HARDWARE_VALIDATION | `budget_ms` no marcador + contagens relativas + share over-budget |
| H-01d | 2026-10-08 | instrumentação | REQUIRES_HARDWARE_VALIDATION | over_budget→INFO diagnóstico, global `inconclusive`, share 2x, notas de relatório |

## Registros

```text
Optimization ID: ENV-00 (validação host Fase 0)
Subsystem: toolchain/host
Hypothesis: o host Fedora/Bazzite atual executa `make test`.
Evidence: bash tools/check-toolchain.sh → exit 1 (clang-18, ld.lld-18,
  llvm-*-18, ccache, nasm, meson, glslangValidator, bison/flex MISSING;
  host tem clang 22/gcc 16/cmake 4.4/python 3.14, sem podman/docker);
  python3 tools/deps.py status → 14/14 missing.
Baseline commit: 868669f (HEAD) + worktree H-01 (não commitado)
Candidate commit: n/a
Environment: Fedora Linux 44 (Container Image), x86-64
Configuration: n/a
Test cases: check-toolchain.sh, deps.py status, tools/perf/test_perf.py,
  tools/check-frame-ring.py
Number of repetitions: 1 (determinístico)
Baseline results: toolchain exit=1; deps 14/14 missing
Candidate results: tools/perf 40/40 OK (0.22 s); check-frame-ring exit=0
  worktree / exit=1 no HEAD (vermelho autêntico)
Measured difference: n/a (gate de ambiente, não A/B)
Variance/uncertainty: nenhuma (saídas determinísticas)
Correctness results: n/a
Compatibility risks: nenhum (nenhuma mudança de comportamento no produto)
Decision: INCONCLUSIVE (gate `make test` bloqueado: sem compilador
  qualificado e sem runtime de container; §13 proíbe modificar o SO do
  host; fetch de GBs sem compilador não tornaria o gate disponível)
Rollback procedure: n/a
```

```text
Optimization ID: H-01 (backlog 05)
Subsystem: instrumentation
Hypothesis: um anel estático de intervalos por frame no relatório Vulkan
  (dev-only) permite P50/P95/P99 reais e contagem acima do orçamento.
Evidence: gap CONFIRMED em 01 (só fps médio + worst + 5 baldes)
Baseline commit: 868669f
Candidate commit: worktree (headless/graphics.cpp:645-673,
  tools/perf/{collect,analyze,frame_samples,compare_metrics}.py,
  test_*.*, tools/check-frame-ring.py) — não commitado
Environment: host Fedora 44 (checks estáticos + pipeline); console pendente
Configuration: EDEN_DEV_PROFILE (zero overhead em release, por construção)
Test cases: tools/perf 40/40 incl. 6 testes H-01 (parse ms, percentis de
  8 amostras manuais, mismatch, vereditos p95/over20); check-frame-ring
  red-no-HEAD(1)/green-no-worktree(0) + pipeline real no formato emitido
Number of repetitions: suite 40/40 verde (2×); check-frame-ring 2×
Baseline results: n/a (marcador novo; logs antigos → frame NODATA, sem gate)
Candidate results: p50=16.7 em fixture manual; mismatch excluído; gate p95
  crítico + over20_share funcionando em stats sintéticos
Measured difference: n/a (instrumentação, não otimização)
Variance/uncertainty: nenhuma no host (determinístico)
Correctness results: produção inalterada (blocos #ifdef EDEN_DEV_PROFILE);
  compilação clang-18/PS5 PENDENTE (sem toolchain); A/B console PENDENTE
Compatibility risks: baixo — acréscimo dev-only; linha de até ~6 KB por
  janela no stdout do console (verificar truncamento de log no HW)
Decision: REQUIRES_HARDWARE_VALIDATION
Rollback procedure: revert do hunk em graphics.cpp (marcador some; logs
  antigos continuam comparáveis via window-level)
```

```text
Optimization ID: H-07 (backlog 05)
Subsystem: instrumentation
Hypothesis: EDEN_GPU_TIME separa gargalo GPU de CPU por submission.
Evidence: tools/prepare-vulkan-port.py:427-499 — timestamps
  TOP_OF_PIPE..BOTTOM_OF_PIPE por command buffer do scheduler, anel de
  512 slots (falha terminal failed=ring sem sobrescrever pendente),
  coleta sem wait (GetQueryResults sem WAIT bit), relatório 5 s com
  wall_ms/busy_ms/submissions/max_ms; worker thread only; opt-in
  gpu_time=on (dev_vulkan.h:19); parsers + testes já cobrem ambas as
  formas (tools/perf)
Baseline commit: n/a (validação de código, sem mudança)
Candidate commit: n/a
Environment: leitura estática + suite host; console pendente
Configuration: gpu_time=on (dev)
Test cases: test_perf.py (parse failed/ok, deltas, submissions)
Number of repetitions: n/a
Baseline results: n/a
Candidate results: semântica documentada; nenhuma medição numérica
Measured difference: nenhuma
Variance/uncertainty: n/a
Compatibility risks: queries de timestamp podem serializar — medir on/off
  no console antes de usar em A/B (risco registrado, não medido)
Decision: REQUIRES_HARDWARE_VALIDATION (coerência vs EDEN_DEV_GPU e
  overhead no RADV só no console)
Rollback procedure: n/a (nada mudou; switch default off)
```

```text
Optimization ID: ENV-01 (qualificação do build via CI)
Subsystem: CI/ambiente
Hypothesis: o workflow toolchain.yml valida clang-18 + estáticos em
  ubuntu-26.04 (GA 2026-09-17, verificado no changelog) sem tocar o Fedora.
Evidence: .github/workflows/toolchain.yml — job toolchain (checkout
  pinado por SHA como release.yml, lista canônica
  tools/ci/ubuntu-packages.txt, make toolchain, df -h) + job perf-static
  (test_perf.py, check-frame-ring.py, ambos sem dependências).
  Desvios do draft: lista canônica em vez de hand-kept (fonte única);
  trigger pull_request adicionado (filosofia do release.yml).
Baseline commit: 868669f
Candidate commit: worktree (workflow novo, não commitado)
Environment: GitHub-hosted ubuntu-26.04 (1ª run pendente de push/PR);
  validação local: YAML parseado (jobs toolchain+perf-static), comandos
  do job estático verdes neste host (suite 45/45, check exit 0)
Configuration: n/a
Test cases: parse YAML; test_perf.py; check-frame-ring.py
Number of repetitions: 1
Baseline results: n/a
Candidate results: YAML válido; estáticos verdes localmente
Measured difference: n/a (infra)
Variance/uncertainty: nenhuma local; run CI ainda não observada
Correctness results: n/a
Compatibility risks: nenhum (workflow novo, não toca release.yml)
Decision: INCONCLUSIVE (aguarda primeira run no push; nunca foi dado push
  sem pedido — autor deve abrir PR ou dispatch manual)
Rollback procedure: remover o arquivo do workflow
```

```text
Optimization ID: H-01a (revisão overflow)
Subsystem: instrumentation
Hypothesis: janelas com overflow>0 não devem gerar vereditos frame-level.
Evidence: o anel já reinicia por janela (reset após emissão,
  graphics.cpp:679-680, agora imposto por ordenação em
  check-frame-ring.py §3b); overflow só ocorre acima de ~204 FPS/janela.
  Pipeline: summarize_frames marca partial=overflow>0; judge() retorna
  NODATA("overflow>0...") nas 4 métricas frame (FRAME_KEYS).
Baseline commit: 868669f + H-01 worktree
Candidate commit: worktree (check + frame_samples + compare_metrics +
  computed_metrics split + 2 testes)
Environment: host Fedora 44; console pendente
Configuration: n/a (pipeline)
Test cases: overflow→partial; partial bloqueia p95 (NODATA+detalhe);
  suite 45/45; check exit 0
Number of repetitions: suite 2× verde após o split
Baseline results: n/a
Candidate results: comportamento verificado em fixtures sintéticas
Measured difference: n/a
Variance/uncertainty: nenhuma (determinístico)
Correctness results: split computed_metrics preserva comportamento
  (suite verde antes e depois, sem tocar asserções)
Compatibility risks: nenhum (logs sem overflow inalterados)
Decision: REQUIRES_HARDWARE_VALIDATION (compilação + console pendentes)
Rollback procedure: revert dos hunks (vereditos voltam a ignorar partial)
```

```text
Optimization ID: H-01b (semântica dos frametimes)
Subsystem: instrumentation (docs-only, sem mudança de código)
Hypothesis: documentar exatamente o evento delimitador dos intervalos.
Evidence: Eden pinado — RendererVulkan::Composite abre com
  SCOPE_EXIT { render_window.OnFrameDisplayed(); } (fetch do mirror
  5f142c79, renderer_vulkan.cpp); EmuWindow documenta "Called from GPU
  thread when a frame is displayed"; o return antecipado do SkipFrame
  (prepare-vulkan-port.py:547-551) está DENTRO de Composite, logo passa
  pelo guard. Conclusão: intervalos = cadência de produção de frames
  pelo guest na GPU thread, INCLUINDO skipped (not_shown à parte);
  mesmo evento de fps/worst (consistência por construção).
Baseline commit: n/a. Candidate commit: docs 02 + este registro.
Environment: n/a. Configuration: n/a. Test cases: n/a.
Decision: ACCEPTED (verificação documental completa e evidenciada)
Rollback procedure: n/a
```

```text
Optimization ID: H-01c (limiares relativos ao orçamento)
Subsystem: instrumentation
Hypothesis: contagens vs budget do jogo servem títulos 30/60/120 FPS;
  absolutos ficam como info adicional.
Evidence: game_millihertz = relógio vsync do jogo (60000 ÷ swap_interval
  ÷ speed_scale; patches FPS sobem; display_refresh.h:30-34, default
  60000, reset por sessão main.cpp:870). C++: budget_ms=1e6/mhz (>0,
  senão 0=desconhecido) no marcador; pipeline: budgeted_samples,
  over_budget, over_2x_budget por janela + share over-budget (não-crítico:
  shares perto de zero explodiriam Δ% — p95 crítico já blinda stutter).
Baseline commit: 868669f + H-01 worktree
Candidate commit: worktree (graphics.cpp, collect, frame_samples,
  computed_metrics, check + 3 testes)
Environment: host Fedora 44; console pendente
Configuration: EDEN_DEV_PROFILE
Test cases: budget parseado/obrigatório; janela 30 FPS (over=2/2x=0,
  absolutos intactos); share 5%==5% em runs de tamanhos distintos;
  check red-antes/green-depois no anchor budget; suite 45/45
Number of repetitions: suite 2× verde
Baseline results: n/a (formato novo, ainda não emitido em console)
Candidate results: fixtures sintéticas verificadas
Measured difference: n/a
Variance/uncertainty: nenhuma (determinístico)
Correctness results: produção inalterada (bloco dev-only)
Compatibility risks: baixo — formato novo sem emitentes legados
Decision: REQUIRES_HARDWARE_VALIDATION (compilação + console pendentes)
Rollback procedure: revert dos hunks (marcador volta sem budget)
```

```text
Optimization ID: H-01d (revisão técnica pré-B-000, 3 itens)
Subsystem: instrumentation (pipeline + relatórios; sem mudança C++)
1) over_budget diagnóstico: shares orçamentárias viraram INFO
   (BUDGET_DIAGNOSTIC_KEYS) — supersede o veredito de H-01c. Motivo:
   swap_interval=2 publica 30000 (correto p/ 30 FPS por swap), mas cap
   interno de 30 FPS com intervalo 1 publica 60000 (misflag vs 16,67);
   indistinguível estaticamente. Critério de reabilitação por título:
   mediana ≈ budget em B-000 (02, caveat H-01d).
2) Global inconclusive: MetricResult.blocked=True no ramo partial;
   overall() = regression > inconclusive > pass; CLI exit 3;
   métricas individuais preservadas (09: "não basta nodata").
3) Stutter além do p95: p99 já gateado como observado; nova share
   frame_over2x_share (INFO, mesmo caveat); relatórios com proveniência
   (samples/windows/budgets/overflow) + caveat produção-vs-tela no rodapé.
Evidence: suite 49/49 (5 testes red-first, 5 vermelhos observados);
  1 expectativa antiga atualizada (overbudget SAME→INFO — o veredito
  anterior era exatamente o comportamento rejeitado na revisão);
  split test_pipeline.py preservou verde; check-frame-ring exit 0.
Baseline commit: 868669f + H-01a/b/c worktree
Candidate commit: worktree (computed_metrics, compare_metrics, compare,
  test_compare, test_pipeline) — não commitado
Environment: host Fedora 44; console pendente
Configuration: n/a (pipeline)
Test cases: overbudget/over2x INFO; overall 3-way + precedência;
  proveniência/caveat no markdown; E2E partial→exit 3 via pipeline real
Number of repetitions: suite 2× verde
Correctness results: produção inalterada (zero C++ neste round)
Compatibility risks: nenhum (formato JSON ganha campo "blocked";
  exit 3 é código novo, documentado no README/CLI)
Decision: REQUIRES_HARDWARE_VALIDATION (budget por título + A/A + B-000)
Rollback procedure: revert dos hunks (volta overall 2-way e INFO→veredito)
```

## Baseline no console (protocolo executável, 02 §3)

| Rodada | Data | Build | Jogo/cena | Estado |
|--------|------|-------|-----------|--------|
| B-000 | — | dev `EDEN_DEV_PROFILE` + H-01 | a definir (2–3 títulos × cena fixa) | PENDENTE (sem console) |

Passo 0 — calibração A/A (antes de qualquer A/B): mesmo binário,
mesma célula, 2+ runs; comparar run×run com `compare.py`. Se |Δ|
excede ±2% com frequência, a banda não é critério confiável: alargar
a banda ou ampliar runs/janelas e re-calibrar. A validade da banda é
ela mesma um resultado do experimento, registrado aqui.

Passos por célula (frio/quente separados, ≥5 runs, A/B alternado):

1. No host: `make deps-status > run.deps.txt`; anotar jogo + Build ID,
   vídeo, cena/inputs, firmware, runtime, temperatura aproximada.
2. No console (build dev): limpar caches p/ célula fria; jogar a cena com
   `dev-settings.txt` vazio (defaults); salvar stdout completo em
   `B-000-<jogo>-<cena>-<frio|quente>-<n>.log`.
3. No host: `python3 tools/perf/collect.py --run B-000-... *.log > run.jsonl`
   → `python3 tools/perf/analyze.py --warmup-windows 1 run.jsonl > run.stats.json`
   → `python3 tools/perf/compare.py --init-baseline run.stats.json baseline.json`.
4. Anexar `report.json`, `run.deps.txt` e `EDEN_DEV_SETTINGS` do log ao
   registro 09; `incomplete_excluded` deve ser ≈0.

## Log de hipóteses rejeitadas

Evidência negativa permanente — consultar antes de reabrir qualquer item.

| Data | Hipótese | Motivo | Ref |
|------|----------|--------|-----|
| 2026-10-08 | A32 fastmem default on | mais lento que page-table no console; causa raiz aberta (H-03) | `main.cpp:644-646` |
| 2026-10-08 | Reverter `gc_keep_dirty` | 10 s a 3–9 FPS + 4,6 s de GC/5 s antes da correção | `performance.h:92-99` |
| 2026-10-08 | `compute_barriers=off` | LOD/culling quebram sem barreiras (AMD concorrente) | `dev_vulkan.h:25-29` |
| 2026-10-08 | LTO global | caminho qualificado é non-LTO + dynarmic thin | `CMakeLists.txt:43-45` |
