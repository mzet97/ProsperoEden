#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real-sample distributions and per-frame interval summaries (H-01/FR-003).

Percentiles come only from real samples, never from aggregates.
Imported by analyze.py. Stdlib only.
"""
import math
import statistics
from typing import TypedDict

RecordValue = int | float | str | bool | list[int] | list[float] | list[str]
Record = dict[str, RecordValue]
Distribution = dict[str, int | float | None]


class FrameSummary(TypedDict):
    windows: int
    samples: int
    overflow: int
    partial: bool
    mismatched: int
    ms: Distribution
    budgets: list[float]
    budgeted_samples: int
    over_budget: int
    over_2x_budget: int
    over_20ms: int
    over_33ms: int
    over_50ms: int


def percentile(sorted_values: list[int | float], pct: float) -> float | None:
    """Linear-interpolated percentile of a sorted list (None when empty)."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * pct / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(sorted_values[int(rank)])
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def distribution(values: list[int | float]) -> Distribution:
    """Summary of a real sample series (all values must be numeric)."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    mean = statistics.fmean(values)
    return {
        "n": len(values),
        "mean": mean,
        "stdev": statistics.pstdev(values, mean) if len(values) > 1 else 0.0,
        "min": ordered[0],
        "max": ordered[-1],
        "p50": percentile(ordered, 50),
        "p95": percentile(ordered, 95),
        "p99": percentile(ordered, 99),
        "p99_9": percentile(ordered, 99.9),
    }


def summarize_frames(records: list[Record]) -> FrameSummary:
    """Frame-level summary of EDEN_VULKAN_FRAMES records (H-01).

    Only records whose ms list length matches n contribute; the rest
    count as mismatched and are excluded, never interpolated. Windows
    that dropped tail samples (H-01a) flag the whole set partial.
    Budget-relative counts (H-01c) judge each sample against its own
    window budget; unknown budgets (<=0) feed absolute thresholds only.
    """
    samples: list[float] = []
    overflow_total = 0
    mismatched = 0
    windows = 0
    budgets: list[float] = []
    budgeted = 0
    over_budget = 0
    over_2x = 0
    for report in records:
        ms = report.get("ms")
        if not isinstance(ms, list):
            mismatched += 1
            continue
        numbers = [float(v) for v in ms
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(numbers) != report.get("n"):
            mismatched += 1
            continue
        samples.extend(numbers)
        windows += 1
        extra = report.get("overflow")
        if isinstance(extra, int) and not isinstance(extra, bool):
            overflow_total += extra
        budget = report.get("budget_ms")
        if isinstance(budget, (int, float)) and not isinstance(budget, bool) \
                and budget > 0:
            if budget not in budgets:
                budgets.append(float(budget))
            budgeted += len(numbers)
            over_budget += sum(1 for v in numbers if v > budget)
            over_2x += sum(1 for v in numbers if v > 2 * budget)
    return {
        "windows": windows,
        "samples": len(samples),
        "overflow": overflow_total,
        "partial": overflow_total > 0,
        "mismatched": mismatched,
        "ms": distribution(samples),
        "budgets": sorted(budgets),
        "budgeted_samples": budgeted,
        "over_budget": over_budget,
        "over_2x_budget": over_2x,
        "over_20ms": sum(1 for v in samples if v > 20.0),
        "over_33ms": sum(1 for v in samples if v > 33.4),
        "over_50ms": sum(1 for v in samples if v > 50.0),
    }
