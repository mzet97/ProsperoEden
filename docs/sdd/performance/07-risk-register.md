# SDD Performance — 07 Risk Register

Probabilidade × impacto em escala Baixa/Média/Alta. Dono = quem executa
a mitigação.

## R-01 — Otimizar sem baseline (medições PS5 pendentes)
- Risco: implementar "melhorias" sem números do console e regredir sem saber.
- P: Alta se houver pressa. I: Alto.
- Mitigação: ordem de execução travada em 08 (baseline antes de qualquer
  mudança); 09 registra INCONCLUSIVE quando faltar hardware.
- Estado: ativo; dono: perf owner.

## R-02 — Somar tempos sobrepostos como tempo de frame
- Risco: `Timer` por API/thread se sobrepõe; somar `EDEN_VULKAN_COST` ou
  contadores de threads distintas fabrica um caminho crítico falso.
- P: Média. I: Alto (decisões erradas).
- Mitigação: aviso normativo em `performance.h:210` e em 02; `tools/perf`
  nunca soma séries sobrepostas; caminho crítico só por timestamps.
- Estado: mitigado por construção; dono: perf owner.

## R-03 — Regressão de correção gráfica/estabilidade
- Risco: barreira removida, GC agressivo ou cache menor quebra jogos.
- P: Média. I: Alto.
- Mitigação: quality gates (06/08); mudanças de precisão só em perfil
  experimental; `gc_keep_dirty` e `compute_barriers` nunca revertem sem
  prova (ver REJECTED em 01).
- Estado: ativo; dono: autor de cada experimento.

## R-04 — W^X / invalidação do JIT violada
- Risco: alias RW/RX mal gerenciado, bloco obsoleto executado, fault em
  produção.
- P: Baixa (área bem testada). I: Alto.
- Mitigação: `check-jit-protection.py`, `check-jit-allocator.py`,
  `check-exclusive-monitor.py` em todo experimento JIT; sem bypass de
  `jit-permissions.inc`.
- Estado: mitigado por construção; dono: autor JIT.

## R-05 — Eviction excessiva ou OOM no pool compartilhado
- Risco: orçamento errado causa GC por frame (caso 4,8 GiB vs 4,5 medido
  em `performance.h:93-99`) ou falta de memória.
- P: Média. I: Alto.
- Mitigação: PERF-NFR-005; monitorar `EDEN_PERF_DIRECT` e
  `EDEN_PERF_HEAP`; mudanças de budget só com curva de retenção medida.
- Estado: ativo; dono: perf owner.

## R-06 — Deriva de pins (Eden/Dynarmic/Mesa/SDK)
- Risco: atualizar revisão upstream muda âncoras de derivação e invalida
  comparações antes/depois.
- P: Baixa. I: Médio.
- Mitigação: âncoras com `FATAL_ERROR` quando mudam
  (`prepare-vulkan-port.py:11-13`, `shared-jit.cmake:10-15`,
  `checked-fastmem.cmake`); `deps-status` no relatório de cada run.
- Estado: mitigado por construção; dono: build owner.

## R-07 — CI sem jobs de teste/lint
- Risco: regressões de host entram sem sinal; hoje só existe
  `.github/workflows/release.yml` (build+empacotamento).
- P: Média. I: Médio.
- Mitigação: propor jobs (estático, host tests, JIT regress, formato) em
  08; até lá, rodar `make test` + `check-*.py` localmente por experimento.
- Estado: ativo; dono: build owner.

## R-08 — Variância térmica/carga do console invalida A/B
- Risco: throttle ou ruído mascara ganhos pequenos.
- P: Média. I: Médio.
- Mitigação: protocolo em 02 (A/B alternado, ≥5 runs, temperatura
  aproximada registrada, intervalos de confiança).
- Estado: ativo; dono: operador do console.

## R-09 — Métricas ausentes induzem ponto cego (GPU)
- Risco: sem tempo de execução de comandos por frame e sem fila de
  apresentação instrumentada, gargalo GPU é inferido, não medido.
- P: Média. I: Médio.
- Mitigação: PERF-FR-003 + instrumentação GPU de baixo overhead como
  pré-requisito de qualquer experimento Vulkan (backlog 05).
- Estado: ativo; dono: perf owner.

## R-10 — Dependência de firmware/SDK não verificada
- Risco: comportamento novo em firmware não qualificado (ex.: correções
  13.60 do helper Lapy ainda pedem runs assistidos, `docs/BUILDING.md:30`).
- P: Baixa. I: Alto.
- Mitigação: firmware no cabeçalho de todo relatório; sem dependência
  nova de firmware sem runs assistidos; proibição normativa.
- Estado: ativo; dono: perf owner.
