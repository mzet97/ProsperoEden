#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze validated JSONL (from collect.py) into run statistics (JSON).

Usage:
    python3 tools/perf/analyze.py session.jsonl > session.stats.json
    python3 tools/perf/analyze.py --warmup-windows 1 a.jsonl b.jsonl > merged.stats.json

Rules (docs/sdd/performance/02-baseline.md):
- Cumulative markers (EDEN_DEV_GPU/GUEST, EDEN_VULKAN_COST,
  EDEN_PERF_PROGRESS, EDEN_PERF_JIT) enter only as deltas between
  consecutive complete reports of the same input execution; run/file
  boundaries reset the chain. Overlapping series are never summed.
- Percentiles come only from real samples: EDEN_VULKAN_FRAMES yields
  frame-level p50/p95/p99/p99.9, while fps/worst stay window-level.
- --warmup-windows N drops the first N windows of EACH input execution
  from windows, frame samples, buckets and every delta numerator.
- Incomplete records (complete=false) are counted and excluded.
Stdlib only.
"""
import json
import sys
from typing import Final, TypedDict

from frame_samples import distribution, summarize_frames

# JSONL record shapes (see collect.py): heterogeneous marker fields.
RecordValue = int | float | str | bool | list[int] | list[float] | list[str]
Record = dict[str, RecordValue]
Distribution = dict[str, int | float | None]
DeltaTotals = dict[str, int | float]


class DeltaResult(TypedDict):
    intervals: int
    totals: DeltaTotals


# Top-level report: a heterogeneous JSON document. Its exact shape is pinned
# by test_perf.py fixtures (parse-don't-validate at the CLI boundary).
StatsReport = dict  # noqa: DICT_OK -- JSON report document, shape tested

FRAME_MARKERS: Final = ("EDEN_VULKAN_FRAME", "EDEN_DEV_FRAME", "EDEN_GAME_FRAME")

# Cumulative numeric fields differenced between consecutive reports.
GPU_DELTA_FIELDS: Final = (
    "idle_ns", "dispatch_calls", "dispatch_ns", "drain_calls", "drain_ns",
    "present_calls", "present_ns", "full_calls", "full_ns", "draws",
)
GUEST_DELTA_FIELDS: Final = (
    "cpu_write_calls", "cpu_write_ns", "cpu_read_calls", "cpu_read_ns",
    "sync_calls", "sync_ns", "dequeue_calls", "dequeue_ns",
    "ipc_calls", "ipc_ns", "cache_lock_contended", "cache_lock_blocked",
    "fs_file_calls", "fs_file_ns", "fs_file_bytes",
    "fs_storage_calls", "fs_storage_ns", "fs_storage_bytes",
)
JIT_DELTA_FIELDS: Final = ("compilations", "compile_ns", "evacuations")


def drop_warmup(records: list[Record], windows: int) -> list[Record]:
    """Drop the first N records of each input execution, order-preserving."""
    if windows <= 0:
        return list(records)
    skipped: dict[tuple[str | None, str | None], int] = {}
    kept: list[Record] = []
    for record in records:
        key = (record.get("_file"), record.get("_run"))
        seen = skipped.get(key, 0)
        if seen < windows:
            skipped[key] = seen + 1
        else:
            kept.append(record)
    return kept


def deltas(reports: list[Record], fields: tuple[str, ...]) -> DeltaResult:
    """Per-interval deltas of cumulative fields.

    Counter resets emit no delta, and the chain restarts at every input
    file/run boundary so merged executions never fabricate intervals.
    """
    totals: DeltaTotals = {name: 0 for name in fields}
    intervals = 0
    previous: Record | None = None
    prev_key: tuple[str | None, str | None] | None = None
    for report in reports:
        key = (report.get("_file"), report.get("_run"))
        if previous is not None and key == prev_key:
            step: DeltaTotals = {}
            for name in fields:
                now, before = report.get(name), previous.get(name)
                if isinstance(now, (int, float)) and isinstance(before, (int, float)):
                    if now < before:  # counter reset: skip this interval
                        step = {}
                        break
                    step[name] = now - before
            if step:
                for name, value in step.items():
                    totals[name] += value
                intervals += 1
        previous, prev_key = report, key
    return {"intervals": intervals, "totals": totals}


def analyze(records: list[Record], warmup_windows: int = 0) -> StatsReport:
    by_marker = {}
    incomplete = 0
    for record in records:
        if not record.get("complete", True):
            incomplete += 1
            continue
        by_marker.setdefault(record["_marker"], []).append(record)

    stats = {
        "runs": sorted({r.get("_run", "?") for r in records}),
        "records": len(records),
        "incomplete_excluded": incomplete,
    }

    # Frame windows (5 s each): window-level fps/worst distributions.
    windows = []
    for marker in FRAME_MARKERS:
        windows.extend(by_marker.get(marker, []))
    windows.sort(key=lambda r: (r.get("_file", ""), r.get("_line", 0)))
    kept_windows = drop_warmup(windows, warmup_windows)
    stats["windows"] = {
        "n": len(kept_windows),
        "warmup_excluded": len(windows) - len(kept_windows),
        "markers": sorted({w["_marker"] for w in kept_windows}),
        "fps": distribution([w["fps"] for w in kept_windows
                             if isinstance(w.get("fps"), (int, float))]),
        "worst_ms": distribution([w["worst_ms"] for w in kept_windows
                                  if isinstance(w.get("worst_ms"), (int, float))]),
        "level": "window (5 s each); frame-level percentiles need PERF-FR-003",
    }
    total_frames = sum(w.get("frames", 0) for w in kept_windows
                       if isinstance(w.get("frames"), int))

    # Vsync-bucket histogram (dev Vulkan only).
    buckets = {"v1": 0, "v2": 0, "v3": 0, "v4plus": 0, "half": 0}
    n_bucket_reports = 0
    bucket_reports = drop_warmup(by_marker.get("EDEN_VULKAN_INTERVALS", []),
                                 warmup_windows)
    for report in bucket_reports:
        if all(isinstance(report.get(k), int) for k in buckets):
            for key in buckets:
                buckets[key] += report[key]
            n_bucket_reports += 1
    stats["intervals"] = {"reports": n_bucket_reports, "buckets": buckets}

    # Per-frame intervals (H-01): true frame-level percentiles when present.
    frames = summarize_frames(drop_warmup(by_marker.get("EDEN_VULKAN_FRAMES", []),
                                          warmup_windows))
    stats["frame_samples"] = frames
    if frames["samples"]:
        stats["windows"]["level"] = (
            f"frame-level ({frames['samples']} EDEN_VULKAN_FRAMES samples); "
            "window fps/worst kept for cross-log comparability")

    # GPU / guest cumulative deltas (never summed across overlapping series).
    stats["gpu"] = deltas(drop_warmup(by_marker.get("EDEN_DEV_GPU", []), warmup_windows),
                          GPU_DELTA_FIELDS)
    stats["guest"] = deltas(drop_warmup(by_marker.get("EDEN_DEV_GUEST", []),
                                        warmup_windows),
                            GUEST_DELTA_FIELDS)

    # Cache-lock contention (interval deltas, like every cumulative series).
    guest_totals = stats["guest"]["totals"]
    stats["cache_lock"] = {
        "contended": guest_totals.get("cache_lock_contended"),
        "blocked": guest_totals.get("cache_lock_blocked"),
    }

    # Vulkan API wall times (opt-in; overlapping calls -- no totals across apis).
    per_api = {}
    for report in by_marker.get("EDEN_VULKAN_COST", []):
        per_api.setdefault(report.get("api", "?"), []).append(report)
    vulkan = {}
    for api, reports in sorted(per_api.items()):
        reports.sort(key=lambda r: (r.get("_file", ""), r.get("_line", 0)))
        vulkan[api] = deltas(drop_warmup(reports, warmup_windows), ("calls", "ns"))
    stats["vulkan_cost"] = vulkan

    # JIT compilations per core (deltas across progress reports).
    jit = {}
    for marker in ("EDEN_PERF_PROGRESS", "EDEN_PERF_JIT"):
        per_core = {}
        for report in by_marker.get(marker, []):
            per_core.setdefault(report.get("core"), []).append(report)
        for core, reports in per_core.items():
            reports.sort(key=lambda r: (r.get("_file", ""), r.get("_line", 0)))
            kept = drop_warmup(reports, warmup_windows)
            fields = JIT_DELTA_FIELDS
            if marker == "EDEN_PERF_PROGRESS" and any(
                    "translate_ns" in r for r in kept):
                fields = fields + ("translate_ns", "optimize_ns",
                                   "emit_ns", "ranges_ns")
            jit.setdefault(str(core), {})[marker] = deltas(kept, fields)
    stats["jit"] = jit

    # GPU execution time of scheduler submissions (opt-in EDEN_GPU_TIME).
    gpu_time_reports = drop_warmup(by_marker.get("EDEN_GPU_TIME", []), warmup_windows)
    gpu_time = [r for r in gpu_time_reports if "failed" not in r]
    stats["gpu_time"] = {
        "reports": len(gpu_time),
        "failed": sum(1 for r in gpu_time_reports if "failed" in r),
        "busy_ms": distribution([r["busy_ms"] for r in gpu_time
                                 if isinstance(r.get("busy_ms"), (int, float))]),
        "submissions": sum(r.get("submissions", 0) for r in gpu_time
                           if isinstance(r.get("submissions"), int)),
    }

    # Fastmem cumulative deltas.
    stats["fastmem"] = deltas(drop_warmup(by_marker.get("EDEN_FASTMEM", []),
                                          warmup_windows),
                              ("direct_reads", "direct_writes", "faults",
                               "maps", "unmaps", "protects",
                               "kernel_calls", "kernel_ns", "failures"))

    # Direct-memory headroom: worst (min) largest free block observed.
    direct_reports = drop_warmup(by_marker.get("EDEN_PERF_DIRECT", []), warmup_windows)
    direct = [r for r in direct_reports
              if isinstance(r.get("largest_free"), (int, float))]
    stats["direct_memory"] = {
        "reports": len(direct),
        "min_largest_free": min((r["largest_free"] for r in direct), default=None),
        "short_reports": sum(1 for r in direct_reports if r.get("short") == 1),
    }

    # Loading / visibility milestones.
    stats["loading"] = {
        "EDEN_LOADING_DONE": len(by_marker.get("EDEN_LOADING_DONE", [])),
        "EDEN_GAME_VISIBLE": len(by_marker.get("EDEN_GAME_VISIBLE", [])),
        "EDEN_SHADER_CACHE_LOADED": len(by_marker.get("EDEN_SHADER_CACHE_LOADED", [])),
    }
    stats["total_window_frames"] = total_frames

    # Settings echo + topology (provenance, not metrics).
    stats["settings"] = [r for r in by_marker.get("EDEN_DEV_SETTINGS", [])
                         if "unknown" not in r][:1]
    stats["topology"] = by_marker.get("EDEN_WORKER_TOPOLOGY", [])[:1]

    # Clock-read overhead calibration (100k reads per report).
    clocks = [r for r in by_marker.get("EDEN_PERF_CLOCK_READ", [])
              if isinstance(r.get("elapsed_ns"), (int, float))
              and isinstance(r.get("calls"), (int, float)) and r["calls"] > 0]
    if clocks:
        ns_per_read = [r["elapsed_ns"] / r["calls"] for r in clocks]
        stats["clock_overhead_ns_per_read"] = distribution(ns_per_read)

    # HLE commands >= 1 ms (last cumulative report per service/cmd).
    hle = {}
    for report in drop_warmup(by_marker.get("EDEN_DEV_HLE", []), warmup_windows):
        hle[(report.get("service"), report.get("cmd"))] = {
            "calls": report.get("calls"), "ns": report.get("ns")}
    stats["hle_commands_over_1ms"] = len(hle)
    stats["hle_top_by_ns"] = sorted(
        ({"service": s, "cmd": c, **v} for (s, c), v in hle.items()
         if isinstance(v.get("ns"), (int, float))),
        key=lambda e: e["ns"], reverse=True)[:10]
    return stats


def main(argv: list[str]) -> int:
    paths: list[str] = []
    warmup = 0
    args = iter(argv[1:])
    for arg in args:
        if arg == "--warmup-windows":
            try:
                warmup = int(next(args))
            except (StopIteration, ValueError):
                print("analyze.py: --warmup-windows needs an integer",
                      file=sys.stderr)
                return 2
        elif arg in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            paths.append(arg)
    records: list[Record] = []
    for path in paths or ["-"]:
        stream = sys.stdin if path == "-" else open(path, encoding="utf-8")
        with stream:
            for lineno, line in enumerate(stream, 1):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        print(f"{path}:{lineno}: bad JSON: {exc}", file=sys.stderr)
    print(json.dumps(analyze(records, warmup), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
