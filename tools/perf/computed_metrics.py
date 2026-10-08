#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-field readers over analyze.py stats reports (imported by compare_metrics).

Plain path navigation plus computed metrics that need two or more
fields. Pure logic, no I/O. Stdlib only.
"""
from typing import Callable, Final


def number(stats: dict, path: tuple[str, ...]) -> float | None:
    """Navigate path through nested dicts; None unless a number is found."""
    node = stats
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, bool):
        return None
    return float(node) if isinstance(node, (int, float)) else None


def windows_n(stats: dict) -> int:
    """Counted 5 s windows; 0 when the report has none."""
    value = number(stats, ("windows", "n"))
    return int(value) if value is not None else 0


def is_partial(stats: dict) -> bool:
    """True when frame samples dropped window tails (H-01a overflow)."""
    frames = stats.get("frame_samples")
    return isinstance(frames, dict) and frames.get("partial") is True


def dispatch_ns_per_draw(stats: dict) -> float | None:
    """Mean dispatch ns per draw across GPU report deltas."""
    dispatch = number(stats, ("gpu", "totals", "dispatch_ns"))
    draws = number(stats, ("gpu", "totals", "draws"))
    if dispatch is None or draws is None or draws <= 0:
        return None
    return dispatch / draws


def v1_share(stats: dict) -> float | None:
    """Share of bucketed frames that landed within one vsync."""
    buckets = stats.get("intervals", {}).get("buckets", {})
    if not isinstance(buckets, dict):
        return None
    counts = [v for v in buckets.values() if isinstance(v, (int, float))]
    total = sum(counts)
    v1 = buckets.get("v1")
    if total <= 0 or not isinstance(v1, (int, float)):
        return None
    return float(v1) / float(total)


def jit_compilations(stats: dict) -> float | None:
    """Total JIT compilations across cores (startup-skewed: info only)."""
    jit = stats.get("jit")
    if not isinstance(jit, dict):
        return None
    total = 0.0
    found = False
    for per_core in jit.values():
        if not isinstance(per_core, dict):
            continue
        for marker in ("EDEN_PERF_PROGRESS", "EDEN_PERF_JIT"):
            entry = per_core.get(marker)
            if isinstance(entry, dict):
                value = entry.get("totals", {}).get("compilations") \
                    if isinstance(entry.get("totals"), dict) else None
                if isinstance(value, (int, float)):
                    total += float(value)
                    found = True
                    break
    return total if found else None


def jit_compile_ms(stats: dict) -> float | None:
    """Total JIT compile ns across cores, in ms (info only)."""
    jit = stats.get("jit")
    if not isinstance(jit, dict):
        return None
    total = 0.0
    found = False
    for per_core in jit.values():
        if not isinstance(per_core, dict):
            continue
        for marker in ("EDEN_PERF_PROGRESS", "EDEN_PERF_JIT"):
            entry = per_core.get(marker)
            if isinstance(entry, dict) and isinstance(entry.get("totals"), dict):
                value = entry["totals"].get("compile_ns")
                if isinstance(value, (int, float)):
                    total += float(value)
                    found = True
                    break
    return total / 1e6 if found else None


def frame_over20_share(stats: dict) -> float | None:
    """Share of frame samples past the 20 ms budget (length-free)."""
    over = number(stats, ("frame_samples", "over_20ms"))
    total = number(stats, ("frame_samples", "samples"))
    if over is None or total is None or total <= 0:
        return None
    return over / total


def frame_overbudget_share(stats: dict) -> float | None:
    """Share of budgeted samples past their window budget (H-01c)."""
    over = number(stats, ("frame_samples", "over_budget"))
    total = number(stats, ("frame_samples", "budgeted_samples"))
    if over is None or total is None or total <= 0:
        return None
    return over / total


def frame_over2x_share(stats: dict) -> float | None:
    """Share of budgeted samples past twice their window budget (H-01d)."""
    over = number(stats, ("frame_samples", "over_2x_budget"))
    total = number(stats, ("frame_samples", "budgeted_samples"))
    if over is None or total is None or total <= 0:
        return None
    return over / total


COMPUTED: Final[dict[str, Callable[[dict], float | None]]] = {
    "v1_share": v1_share,
    "dispatch_per_draw": dispatch_ns_per_draw,
    "jit_compilations": jit_compilations,
    "jit_compile_ms": jit_compile_ms,
    "frame_over20_share": frame_over20_share,
    "frame_overbudget_share": frame_overbudget_share,
    "frame_over2x_share": frame_over2x_share,
}
