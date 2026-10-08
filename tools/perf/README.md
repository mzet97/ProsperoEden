# tools/perf — benchmark pipeline (collect → analyze → compare)

Stdlib-only helpers for the SDD performance baseline
(`docs/sdd/performance/02-baseline.md`). No dependencies: plain
`python3` on the host, matching every other script in `tools/`.

Modules: `collect.py` (log → JSONL), `analyze.py` (JSONL → stats),
`frame_samples.py` (real-sample distributions, H-01 summaries),
`compare.py` (CLI + reports) over `compare_metrics.py` (verdict
engine) and `computed_metrics.py` (multi-field readers),
`test_perf.py` running `test_collect.py`, `test_analyze.py`
and `test_compare.py`.

## Usage

```bash
# 1. Import PS5 stdout logs into validated JSONL (one record per line).
python3 tools/perf/collect.py session.log > run.jsonl
python3 tools/perf/collect.py --run dev-A a.log b.log > runs.jsonl

# 2. Compute run statistics (deltas, window fps/worst, buckets, headroom).
python3 tools/perf/analyze.py run.jsonl > run.stats.json
python3 tools/perf/analyze.py --warmup-windows 1 run.jsonl > run.stats.json

# 3. Compare baseline vs candidate (Markdown to stdout).
# Exit 0 pass, 1 regression, 3 inconclusive (overflow-blocked), 2 errors.
python3 tools/perf/compare.py base.stats.json cand.stats.json
python3 tools/perf/compare.py base.json cand.json --json report.json
python3 tools/perf/compare.py base.json cand.json --markdown report.md

# Store a validated stats file as a new baseline (needs counted windows).
python3 tools/perf/compare.py --init-baseline run.stats.json baseline.json

# Run the suite (contract of PERF-FR-002).
python3 tools/perf/test_perf.py
```

## Rules the code enforces

- Cumulative markers (`EDEN_DEV_GPU/GUEST`, `EDEN_VULKAN_COST`,
  `EDEN_PERF_PROGRESS/JIT`) enter **only as deltas** between consecutive
  reports; counter resets skip the interval instead of going negative.
- Overlapping series are **never summed** (each Vulkan API keeps its own
  totals; `performance.h` forbids summing wall times as frame time).
- Totals compare **per 5 s window** across runs; startup-skewed counters
  (JIT compilations) report as info, never as gate verdicts.
- Percentiles come **only from real samples**. `EDEN_VULKAN_FRAMES`
  (H-01) yields frame-level p50/p95/p99, budget-relative counts
  (`over_budget`, `over_2x_budget` vs each window's `budget_ms`) and
  absolute thresholds as additional info; without it, fps/worst
  distributions stay window-level and are labelled so.
- Windows that dropped tail samples (`overflow>0`) flag the frame set
  `partial`, and frame-metric verdicts refuse to compare (`nodata`):
  incomplete samples never produce a gate call. The global verdict then
  becomes `inconclusive` (exit 3) instead of `pass` — a proven
  `regression` still wins over `inconclusive`, and valid individual
  metrics are preserved.
- Budget-relative shares (`frame_overbudget_share`, `frame_over2x_share`)
  report as diagnostic INFO until console runs validate the budget
  semantics per title (H-01d); absolute thresholds and p95/p99 keep
  their verdicts.
- Reports state frame-sample provenance (samples, windows, budgets,
  overflow) and the caveat that intervals measure guest production
  cadence, not on-screen present intervals.
- Incomplete records (`complete: false`) are counted and excluded, never
  interpolated. Triage band default ±2%; fps/worst calls whose window
  distributions overlap are capped at `same` with a rerun note.
