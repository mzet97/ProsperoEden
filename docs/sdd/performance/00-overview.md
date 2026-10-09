# SDD Performance — 00 Overview

Metodologia: Specification-Driven Development + engenharia de desempenho
baseada em evidências. Princípio: **MEASURE → UNDERSTAND → SPECIFY →
IMPLEMENT → VERIFY**.

Alvo: ProsperoEden (Eden `5f142c79` + frontend PS5 em `headless/`) no
PlayStation 5 real. Nenhuma otimização entra no perfil padrão sem
benchmark A/B reproduzível, testes de correção e registro em
[09-results.md](09-results.md).

## Mapa dos documentos

| Doc | Conteúdo | Estado |
|-----|----------|--------|
| 00-overview.md | este índice, princípios e estado | pronto |
| 01-architecture-audit.md | arquitetura auditada no código | pronto |
| 02-baseline.md | instrumentação, métricas, protocolo, tools/perf | pronto (medições PS5 pendentes) |
| 03-requirements.md | PERF-FR/NFR rastreáveis | pronto |
| 04-design.md | decisões de projeto + índice de ADRs | pronto |
| 05-optimization-backlog.md | hipóteses priorizadas | pronto |
| 06-test-strategy.md | suítes existentes + novos testes | pronto |
| 07-risk-register.md | riscos e mitigações | pronto |
| 08-implementation-plan.md | fases, gates e ordem de execução | pronto |
| 09-results.md | registro de experimentos | 11 registros (+GATE2A); PR #1 merged; nenhum A/B numérico ainda |

ADRs em `docs/adr/ADR-00X-*.md`.

## Regras do programa (resumo)

- Uma hipótese por experimento; uma mudança por benchmark; rollback sempre
  pronto (flag `dev-settings.txt` ou reversão do commit).
- Perfis `Accurate`/`Balanced`/`Performance`/`Developer` só ganham conteúdo
  respaldado por resultados; nada de combinações arbitrárias de switches.
- Proibido: remover barreiras Vulkan sem prova, violar W^X do JIT,
  data races, mascarar crashes, alterar velocidade interna dos jogos,
  FPS sintético ou interpolação.
- Arquivos derivados (`build/`, `.deps/`, saídas de `inject.cmake`,
  `prepare-vulkan-port.py`, `shared-jit.cmake`) nunca são editados como
  fonte canônica; pins em `tools/deps.json` não mudam sem motivo medido.
- Testes automatizados usam fixtures sintéticas (`fixtures/`,
  `tools/check-*.py`); jogos reais só em medições no console, com
  Build ID registrado.

## Estado atual (Etapa Zero)

- Auditoria estática concluída a partir do código; cada conclusão marcada
  como CONFIRMED, HYPOTHESIS, NOT MEASURED ou REJECTED.
- Baseline de código (contadores, janelas de 5 s, switches A/B)
  documentado; **nenhuma medição numérica foi coletada nesta sessão** —
  não há PS5 conectado ao ambiente. Todas as medições nativas estão
  marcadas como pendentes em 02 e 09.
- `tools/perf/` criado com importação, análise e comparação de logs,
  testado no host (stdlib apenas, sem dependências): 61 testes verdes
  (H-01e: warmup/run, deltas c/ fronteira, per-interval, gate c/
  evidência, tipos, banda, p99.9, sessão C++, vsync+half).
- PR #1 merged em main (00a0eef); Gates 1 e 2a verdes no CI
  (toolchain + perf-static + make-test ~26 min); próximo: Gate 2b
  (build dev PS5 compila H-01 sob EDEN_DEV_PROFILE); produção
  inalterada; otimizações JIT/Vulkan seguem congeladas até A/A + B-000.

## Convenções de evidência

- `CONFIRMED`: lido diretamente no código citado (`arquivo:linha`).
- `HYPOTHESIS`: inferência plausível, ainda sem medição.
- `NOT MEASURED`: número ou comportamento que só o console (ou um
  experimento) pode fornecer.
- `REJECTED`: decisão já tomada contra, com motivo e referência.
