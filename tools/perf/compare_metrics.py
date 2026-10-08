#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Baseline-vs-candidate verdict engine for tools/perf (imported by compare.py).

Metric specs, value extraction, per-metric verdicts and the regression
gate. Multi-field readers live in computed_metrics.py. Pure logic, no
I/O. Stdlib only.
"""
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from computed_metrics import COMPUTED, is_partial, number, windows_n


class Outcome(StrEnum):
    BETTER = "better"
    WORSE = "worse"
    SAME = "same"
    NODATA = "nodata"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """One compared metric: JSON path or computed key, direction, gate."""

    key: str
    label: str
    unit: str
    higher_better: bool
    critical: bool
    path: tuple[str, ...] | None
    per_window: bool = False


@dataclass(frozen=True, slots=True)
class MetricResult:
    """Verdict for one metric; change_pct is None when not computable."""

    key: str
    label: str
    unit: str
    base: float | None
    cand: float | None
    change_pct: float | None
    outcome: Outcome
    detail: str
    blocked: bool = False


TRIAGE_BAND_PCT: Final = 2.0

SPECS: Final = (
    MetricSpec("fps_mean", "window fps (mean)", "fps", True, True,
               ("windows", "fps", "mean")),
    MetricSpec("fps_p50", "window fps (p50)", "fps", True, False,
               ("windows", "fps", "p50")),
    MetricSpec("worst_mean", "window worst frametime (mean)", "ms", False, True,
               ("windows", "worst_ms", "mean")),
    MetricSpec("worst_max", "window worst frametime (max)", "ms", False, True,
               ("windows", "worst_ms", "max")),
    MetricSpec("dispatch_ns", "GPU dispatch (per window)", "ns", False, False,
               ("gpu", "totals", "dispatch_ns"), True),
    MetricSpec("drain_ns", "GPU fence drain (per window)", "ns", False, False,
               ("gpu", "totals", "drain_ns"), True),
    MetricSpec("present_ns", "present wait (per window)", "ns", False, False,
               ("gpu", "totals", "present_ns"), True),
    MetricSpec("queue_full_ns", "queue-full wait (per window)", "ns", False, False,
               ("gpu", "totals", "full_ns"), True),
    MetricSpec("cpu_write_ns", "guest CPU write (per window)", "ns", False, False,
               ("guest", "totals", "cpu_write_ns"), True),
    MetricSpec("cpu_read_ns", "guest flush-area read (per window)", "ns", False, False,
               ("guest", "totals", "cpu_read_ns"), True),
    MetricSpec("cache_blocked", "cache-lock sleeps (per window)", "count", False, False,
               ("cache_lock", "blocked"), True),
    MetricSpec("fastmem_faults", "fastmem faults (per window)", "count", False, False,
               ("fastmem", "totals", "faults"), True),
    MetricSpec("fastmem_kernel_ns", "fastmem kernel (per window)", "ns", False, False,
               ("fastmem", "totals", "kernel_ns"), True),
    MetricSpec("largest_free", "min largest free direct block", "bytes", True, True,
               ("direct_memory", "min_largest_free")),
    MetricSpec("gpu_busy_ms", "GPU busy (mean, opt-in)", "ms", False, False,
               ("gpu_time", "busy_ms", "mean")),
    MetricSpec("v1_share", "frames within 1 vsync (share)", "fraction", True, False,
               None),
    MetricSpec("dispatch_per_draw", "dispatch per draw", "ns/draw", False, False,
               None),
    MetricSpec("jit_compilations", "JIT compilations (info)", "count", False, False,
               None),
    MetricSpec("jit_compile_ms", "JIT compile time (info)", "ms", False, False,
               None),
    MetricSpec("frame_p95_ms", "frame interval p95 (H-01)", "ms", False, True,
               ("frame_samples", "ms", "p95")),
    MetricSpec("frame_p99_ms", "frame interval p99 (H-01)", "ms", False, False,
               ("frame_samples", "ms", "p99")),
    MetricSpec("frame_over20_share", "frames over 20 ms (share)", "fraction",
               False, False, None),
    MetricSpec("frame_overbudget_share", "frames over budget (share)", "fraction",
               False, False, None),
    MetricSpec("frame_over2x_share", "frames past 2x budget (share)", "fraction",
               False, False, None),
)

INFO_KEYS: Final = frozenset({"jit_compilations", "jit_compile_ms"})
# Budget-relative shares stay diagnostic until console runs prove that
# game_millihertz tracks each title's target cadence (H-01d review).
BUDGET_DIAGNOSTIC_KEYS: Final = frozenset({"frame_overbudget_share",
                                           "frame_over2x_share"})
NOISE_CAPPED: Final = frozenset({"fps_mean", "worst_mean", "frame_p95_ms"})
FRAME_KEYS: Final = frozenset({"frame_p95_ms", "frame_p99_ms",
                               "frame_over20_share", "frame_overbudget_share",
                               "frame_over2x_share"})


def metric_value(stats: dict, spec: MetricSpec) -> float | None:
    """Extract (and per-window normalize) one metric from a stats report."""
    if spec.path is not None:
        value = number(stats, spec.path)
    else:
        compute = COMPUTED.get(spec.key)
        value = compute(stats) if compute is not None else None
    if value is None:
        return None
    if spec.per_window:
        windows = windows_n(stats)
        if windows <= 0:
            return None
        return value / windows
    return value


def distributions_overlap(base: dict, cand: dict, mean_path: tuple[str, ...],
                           stdev_key: str, base_mean: float,
                           cand_mean: float) -> bool:
    """True when two window distributions overlap (noise, not signal)."""
    section_path = mean_path[:-1]
    base_stdev = number(base, section_path + (stdev_key,))
    cand_stdev = number(cand, section_path + (stdev_key,))
    if base_stdev is None or cand_stdev is None:
        return False
    return abs(base_mean - cand_mean) < (base_stdev + cand_stdev) / 2


def judge(spec: MetricSpec, base: dict, cand: dict,
          band_pct: float) -> MetricResult:
    """Verdict for one metric between two stats reports."""
    base_value = metric_value(base, spec)
    cand_value = metric_value(cand, spec)
    if base_value is None or cand_value is None:
        return MetricResult(spec.key, spec.label, spec.unit, base_value,
                            cand_value, None, Outcome.NODATA, "missing data")
    if spec.key in FRAME_KEYS and (is_partial(base) or is_partial(cand)):
        return MetricResult(spec.key, spec.label, spec.unit, base_value,
                            cand_value, None, Outcome.NODATA,
                            "overflow>0: incomplete window samples",
                            blocked=True)
    if spec.key in INFO_KEYS or spec.key in BUDGET_DIAGNOSTIC_KEYS:
        change = percent_change(base_value, cand_value)
        detail = ("diagnostic until budget semantics validated on console (H-01c)"
                  if spec.key in BUDGET_DIAGNOSTIC_KEYS
                  else "startup-skewed; context only")
        return MetricResult(spec.key, spec.label, spec.unit, base_value,
                            cand_value, change, Outcome.INFO, detail)
    change = percent_change(base_value, cand_value)
    if change is None:
        return MetricResult(spec.key, spec.label, spec.unit, base_value,
                            cand_value, None, Outcome.NODATA, "zero baseline")
    if abs(change) < band_pct:
        return MetricResult(spec.key, spec.label, spec.unit, base_value,
                            cand_value, change, Outcome.SAME,
                            f"within triage band (±{band_pct:g}%)")
    improved = change > 0 if spec.higher_better else change < 0
    outcome = Outcome.BETTER if improved else Outcome.WORSE
    detail = ""
    if spec.key in NOISE_CAPPED and spec.path is not None and \
            distributions_overlap(base, cand, spec.path, "stdev",
                                  base_value, cand_value):
        outcome = Outcome.SAME
        detail = "distributions overlap; rerun with more windows"
    return MetricResult(spec.key, spec.label, spec.unit, base_value,
                        cand_value, change, outcome, detail)


def percent_change(base_value: float, cand_value: float) -> float | None:
    """Relative change in percent; None when the baseline is zero."""
    if base_value == 0:
        return None
    return (cand_value - base_value) / abs(base_value) * 100.0


def compare_reports(base: dict, cand: dict, band_pct: float) -> list[MetricResult]:
    """Verdict for every spec between two stats reports."""
    return [judge(spec, base, cand, band_pct) for spec in SPECS]


def overall(results: list[MetricResult]) -> str:
    """Gate: proven regression wins; blocked frame metrics force inconclusive."""
    critical = {spec.key for spec in SPECS if spec.critical}
    if any(r.key in critical and r.outcome is Outcome.WORSE for r in results):
        return "regression"
    if any(r.key in FRAME_KEYS and r.blocked for r in results):
        return "inconclusive"
    return "pass"
