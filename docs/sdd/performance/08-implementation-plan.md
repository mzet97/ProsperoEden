# SDD Performance — 08 Implementation Plan

## Fase 0 — Fundação (esta sessão, sem PS5)

- [x] 01 auditoria estática com evidências do código.
- [x] 02 protocolo de baseline + inventário de instrumentação.
- [x] 03 requisitos PERF-FR/NFR.
- [x] `tools/perf/` + suite verde (40 testes após H-01).
- [x] 04/05/06/07/08/09 + ADRs.
- [ ] Validar `make test` no host Fedora/Bazzite → BLOQUEADO com evidência
  (ENV-00 em 09): `check-toolchain.sh` exit 1 (sem clang-18, sem podman/
  docker para o container Ubuntu 26.04); `deps.py status` 14/14 missing.
  Desbloqueio: ENV-01 (CI ubuntu-26.04) abaixo.

## ENV-01 — Qualificação do build via CI (marco intermediário)

- [x] Workflow `.github/workflows/toolchain.yml`: job toolchain
  (pacotes canônicos + `make toolchain` + `df -h`) + job perf-static
  (suite + check H-01, sem dependências). YAML validado localmente.
- [x] Gate 1: primeira run verde — run 37858755115 success
  (toolchain "All host tools found", perf-static 49 testes + check H-01;
  91G livres). Registro ENV-01-RUN em 09.
- [x] Gate 2a: job `make-test` verde — run 37925538267 success
  (host build + suítes PASS, ~26 min). PR #1 merged em 00a0eef.
- [ ] Gate 2b: build dev PS5 com H-01 (teste real de compilação do anel
  sob EDEN_DEV_PROFILE; release não o compila). Requer job CI com
  Payload SDK + RADV (pesado, horas) ou build manual qualificado.
- [ ] Gate 3: B-000 com calibração A/A prévia (mesmo binário × ele mesmo;
  se |Δ| A/A excede ±2% com frequência, a banda não é critério confiável —
  alargar banda ou ampliar runs antes de qualquer A/B).
- H-01 revisado antes do benchmarking: H-01a overflow→`partial` +
  bloqueio de vereditos; H-01b semântica CONFIRMED (produção guest,
  incl. skipped); H-01c `budget_ms` + contagens relativas; H-01d
  over_budget diagnóstico, global `inconclusive` sob overflow, P99 +
  far-over-budget observados, caveat produção-vs-tela nos relatórios.
  Compilação e console pendentes (09).

## Congelamento (decisão de revisão — vigente)

Nenhuma otimização JIT/Vulkan (H-02 a H-10) até: (1) CI verde,
(2) H-01 compilar no build dev, (3) calibração A/A + B-000 medidos.
Priorização de H-02+ sai do impacto medido, não do ganho esperado.

## Fase 1 — Instrumentação mínima (H-01, H-07)

1. Implementar anel de intervalos por frame (H-01) sob switch dev.
2. Validar `EDEN_GPU_TIME` (H-07) em cenas de referência.
3. Calibrar overhead; `check-performance.py` continua verde.
4. Gate: T-02 passa; nenhuma mudança de default.

## Fase 2 — Baseline no console (B-000…)

1. Escolher 2–3 títulos × cenas fixas; registrar Build IDs.
2. Rodar protocolo 02 §3 (frio/quente, ≥5 runs, A/B alternado).
3. Importar via `tools/perf/`; publicar `baseline.json` por célula.
4. Gate: janelas completas, `incomplete_excluded`≈0, settings no cabeçalho.

## Fase 3 — Experimentos sem código (H-02, H-04, H-05, H-06, H-10)

Ordem: H-04 → H-05 → H-06 (1 dia cada, switches existentes) →
H-02 (N jogos) → H-10. Um por vez; cada um termina em 09 com
ACCEPTED/REJECTED/INCONCLUSIVE + rollback.

## Fase 4 — Experimentos com código (H-03, H-08, H-09 + backlog novo)

Só após Fase 2. Superfícies 2–4 de 04 §4; cada um com teste host novo.

## CI/CD e ambiente Fedora/Bazzite

Build oficial: Ubuntu 26.04 (`Makefile:4`); CI atual só empacota
(`release.yml`), sem testes (R-07). Proposta (não implementada):

1. Container reproduzível (`Containerfile`: `ubuntu:26.04` +
   `tools/ci/ubuntu-packages.txt`) para dev em Fedora/Bazzite via
   Podman — sem tocar no host.
2. Workflow `perf-check.yml`: (a) `python3 tools/perf/test_perf.py`;
   (b) `make test` no container; (c) validação de artefatos.
3. `make test` + `check-*.py` locais por experimento até o CI existir.
4. Pins (`tools/deps.json`, `UPSTREAM.json`) e hashes intactos; nada de
   bump de Eden/Dynarmic/Mesa/SDK durante experimentos (R-06).
5. Licenças: GPL-3.0-or-later + `THIRD_PARTY_NOTICES.md` preservados.

## Contingência sem PS5

Fases 1 (host), 3-parcial (lógica), 4-parcial (código + testes host)
avançam; tudo que precisa de número do console registra
REQUIRES_HARDWARE_VALIDATION em 09. Nunca fabricar FPS (regra mestra).
