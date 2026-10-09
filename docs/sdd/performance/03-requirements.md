# SDD Performance — 03 Requirements

Requisitos funcionais (FR) e não-funcionais (NFR) do programa de
desempenho. IDs estáveis para rastreabilidade em backlog, testes e
resultados.

## Funcionais

### PERF-FR-001 — Auditoria arquitetural versionada
- Objetivo: diagrama e fluxos da arquitetura real, com evidências do código.
- Subsistema: docs. Métrica: cobertura dos arquivos obrigatórios da Etapa Zero.
- Aceite: `01-architecture-audit.md` cita arquivo:linha para cada afirmação
  estrutural e classifica conclusões (CONFIRMED/HYPOTHESIS/NOT MEASURED/REJECTED).
- Teste: revisão por inspeção (grep das âncoras citadas).

### PERF-FR-002 — Framework de benchmark reproduzível
- Objetivo: importar logs do PS5, validar, calcular estatísticas, comparar
  baseline × candidato, emitir Markdown + JSON, sinalizar regressões.
- Subsistema: `tools/perf/`. Métrica: paridade com cálculo manual em fixtures.
- Aceite: ≥5 execuções/célula, A/B alternado, frio/quente separados,
  relatório com variância e veredito por métrica.
- Teste: `python3 tools/perf/test_perf.py` (host, stdlib apenas).

### PERF-FR-003 — Percentis de frametime a partir de amostras reais
- Objetivo: P50/P95/P99/P99.9 e contagem de frames acima do orçamento.
- Subsistema: instrumentação (`headless/graphics.cpp`, `performance.*`).
- Métrica: erro do percentil vs. série de intervalos por frame.
- Aceite: histograma/anel por frame com overhead desprezível e desligável;
  sem derivar percentis de agregados.
- Teste: fixture sintética com série conhecida; `check-performance.py`
  continua passando (nada no caminho crítico de produção).

### PERF-FR-004 — Experimentos de variável única com rollback
- Objetivo: cada otimização testável isoladamente e reversível.
- Subsistema: todos. Métrica: 100% das mudanças experimentais sob flag ou
  commit isolado.
- Aceite: hipótese, baseline, candidato, repetições, decisão
  (ACCEPTED/REJECTED/INCONCLUSIVE/REQUIRES_HARDWARE_VALIDATION) e
  procedimento de rollback registrados em 09.
- Teste: `git log` mostra um commit por experimento; flag documentada.

### PERF-FR-005 — Perfis por jogo respaldados por resultados
- Objetivo: Accurate/Balanced/Performance/Developer como configurações
  medidas, não combinações arbitrárias de switches.
- Subsistema: `headless/settings_store.h`, `main.cpp`.
- Métrica: cada parâmetro de perfil aponta para um experimento ACCEPTED.
- Aceite: matriz perfil × parâmetro × evidência em 04.
- Teste: host checks dos defaults; validação no console por título.

## Não-funcionais

### PERF-NFR-001 — Correção preservada
- Nenhuma regressão de correção gráfica, estabilidade ou compatibilidade no
  perfil padrão. Mudanças que reduzem precisão ficam em perfis
  experimentais opcionais. Gate: suítes `make test` + `tools/check-*.py`
  aplicáveis verdes; sem novos crashes conhecidos.

### PERF-NFR-002 — Overhead de instrumentação controlado
- Instrumentação desligável; produção sem `Timer`/`SampleCpu`/`cpu_state`
  nos caminhos quentes do JIT (imposto por `tools/check-performance.py`),
  sem logging síncrono por draw, sem alocações ou locks novos no caminho
  crítico, sem somar tempos sobrepostos como tempo sequencial de frame.

### PERF-NFR-003 — Reprodutibilidade
- Mesmo jogo/Build ID, vídeo, cena, firmware, runtime, temperatura
  aproximada; cache frio/quente separados; ≥5 repetições; build
  reproduzível a partir dos pins (`tools/deps.json`, `UPSTREAM.json`).
  Relatório registra limitações de cada experimento.

### PERF-NFR-004 — Segurança do JIT e da GPU
- W^X preservado (alias RW/RX, `jit-permissions.inc`); invalidação de
  blocos e coerência de memória intactas; barreiras Vulkan só mudam com
  prova de correção; sem data races; sem dependências de firmware não
  verificadas.

### PERF-NFR-005 — Memória compartilhada tratada como pool único
- CPU e GPU dividem a direct memory do PS5; orçamentos e GC decidem pelo
  bloco livre do pool (`graphics_usage_from_pool`, `kShortMemory`),
  nunca por contadores isolados do driver. Sem aumento cego de budgets;
  sem eviction excessiva nem OOM.

### PERF-NFR-006 — Triagem estatística honesta
- Regressão ≥2% em métrica crítica dispara investigação; ganho precisa
  exceder materialmente a variabilidade do benchmark (intervalos de
  confiança quando a variância for alta). Médias isoladas não aprovam nada.
