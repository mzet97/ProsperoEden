# AGENTS.md — ProsperoEden

Instruções para agentes trabalhando neste repositório.

## Leitura obrigatória antes de agir

1. [notes.md](notes.md) — achados, estado de trabalho e pendências.
2. `docs/sdd/performance/09-results.md` — registro append-only de experimentos (fonte canônica).
3. `docs/BUILDING.md` — como compilar; `UPSTREAM.json` — pins de dependências.

## Regras do projeto

- SDD: MEASURE → UNDERSTAND → SPECIFY → IMPLEMENT → VERIFY. Uma mudança por experimento.
- Nunca fabricar FPS ou resultados de hardware; marcar conclusões como
  CONFIRMED / HYPOTHESIS / NOT MEASURED / REJECTED.
- Não instalar toolchain no host Fedora/Bazzite; builds locais via distrobox
  `eden-build` (ubuntu:26.04). CI oficial em GitHub Actions (ubuntu-26.04).
- Preservar pins de deps, hashes e adaptações PS5; nunca editar arquivos gerados
  como se fossem fontes canônicas.
- Instrumentação dev-only: gate na camada CMake, nunca `#ifdef` interno no core
  (o core lib compila sem `EDEN_DEV_PROFILE`).
- `replay=off` = build jogável (input real); `replay=on` = benchmark determinístico.
- Armadilha de build incremental: ninja + ccache NÃO percebem header derivado
  NOVO (depfile/manifesto apontam o original). Após adicionar patch de header,
  delete os `.o` dependentes e rebuild com `CCACHE_RECACHE=1` juntos; sempre
  confirme com `strings` no eboot que os marcadores entraram.
- Patches no core: gate SÓ na camada CMake (`if(EDEN_DEV_PROFILE)`); nunca
  `#ifdef` interno — o core compila sem a macro (regressão 8fd18e4).
- Git: só commitar/pushear com autorização explícita do usuário nesta sessão.
- Ao corrigir um bug de comportamento: carregar a skill `bundled:durable-test-collateral`
  e manter o menor teste focado junto ao projeto.

## Portas de entrada

- Diagnóstico de desempenho: `headless/performance.{h,cpp}`, marcadores `EDEN_*`.
- Pipeline de métricas: `tools/perf/{collect,analyze,compare}.py` + `test_perf.py`.
- Falhas conhecidas e próximos passos: ver [notes.md](notes.md) §4–§6.
