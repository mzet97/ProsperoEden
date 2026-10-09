#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for analyze.py: deltas and report assembly."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
import frame_samples


def window(line: int, fps: float, worst_ms: float, run: str = "t") -> dict:
    """One complete 5 s Vulkan frame window record."""
    return {"_marker": "EDEN_VULKAN_FRAME", "_file": "t", "_line": line,
            "_run": run, "complete": True, "frames": 150, "seconds": 5.0,
            "fps": fps, "worst_ms": worst_ms, "total": 150 * line,
            "not_shown": 0, "clock_hz": 60.0}


def gpu(line: int, **fields: int) -> dict:
    """One complete cumulative GPU-thread report."""
    record = {"_marker": "EDEN_DEV_GPU", "_file": "t", "_line": line,
              "_run": "t", "complete": True, "frame": line, "mono_ns": line,
              "idle_ns": 0, "dispatch_calls": 0, "dispatch_ns": 0,
              "drain_calls": 0, "drain_ns": 0, "present_calls": 0,
              "present_ns": 0, "full_calls": 0, "full_ns": 0, "draws": 0}
    record.update(fields)
    return record


class TestAnalyzeDeltas(unittest.TestCase):
    def test_deltas_subtract_consecutive_reports(self) -> None:
        # Given two cumulative GPU reports,
        first = gpu(1, dispatch_calls=200, dispatch_ns=3000000, draws=1200,
                    idle_ns=1000000, drain_calls=1, drain_ns=5000,
                    present_calls=150, present_ns=150000,
                    full_calls=0, full_ns=0)
        second = gpu(2, dispatch_calls=350, dispatch_ns=5200000, draws=2100,
                     idle_ns=1800000, drain_calls=2, drain_ns=9000,
                     present_calls=300, present_ns=280000,
                     full_calls=1, full_ns=4000)
        # When differenced,
        result = analyze.deltas([first, second], analyze.GPU_DELTA_FIELDS)
        # Then every total is the hand-computed difference over one interval.
        self.assertEqual(result["intervals"], 1)
        self.assertEqual(result["totals"]["dispatch_calls"], 150)
        self.assertEqual(result["totals"]["dispatch_ns"], 2200000)
        self.assertEqual(result["totals"]["draws"], 900)
        self.assertEqual(result["totals"]["idle_ns"], 800000)
        self.assertEqual(result["totals"]["drain_calls"], 1)
        self.assertEqual(result["totals"]["drain_ns"], 4000)
        self.assertEqual(result["totals"]["present_calls"], 150)
        self.assertEqual(result["totals"]["present_ns"], 130000)
        self.assertEqual(result["totals"]["full_calls"], 1)
        self.assertEqual(result["totals"]["full_ns"], 4000)

    def test_deltas_skip_reset_interval(self) -> None:
        # Given a counter that wraps (100 -> 50 -> 80),
        reports = [gpu(1, draws=100), gpu(2, draws=50), gpu(3, draws=80)]
        # When differenced,
        result = analyze.deltas(reports, ("draws",))
        # Then the reset interval contributes nothing and counting resumes.
        self.assertEqual(result["intervals"], 1)
        self.assertEqual(result["totals"]["draws"], 30)

    def test_deltas_single_report_is_zero(self) -> None:
        # Given a lone report with no predecessor,
        result = analyze.deltas([gpu(1, draws=100)], ("draws",))
        # When differenced,
        # Then there are no intervals and every total is zero.
        self.assertEqual(result["intervals"], 0)
        self.assertEqual(result["totals"]["draws"], 0)

    def test_deltas_reset_at_run_boundary(self) -> None:
        # Given rising counters from two different input runs,
        first = gpu(1, draws=100)
        second = gpu(2, draws=200)
        second["_run"] = "other"
        # When differenced,
        result = analyze.deltas([first, second], ("draws",))
        # Then no fabricated cross-run interval is accepted.
        self.assertEqual(result["intervals"], 0)
        self.assertEqual(result["totals"]["draws"], 0)


class TestAnalyzeReport(unittest.TestCase):
    def test_incomplete_records_excluded_and_counted(self) -> None:
        # Given two complete windows and one incomplete,
        broken = window(2, 29.0, 45.0)
        broken["complete"] = False
        records = [window(1, 30.0, 40.0), broken, window(3, 31.0, 50.0)]
        # When analyzed,
        stats = analyze.analyze(records)
        # Then only complete windows feed the distributions.
        self.assertEqual(stats["windows"]["n"], 2)
        self.assertEqual(stats["incomplete_excluded"], 1)
        self.assertAlmostEqual(stats["windows"]["fps"]["mean"], 30.5)

    def test_warmup_skips_first_windows(self) -> None:
        # Given three windows and one warmup window,
        records = [window(1, 20.0, 90.0), window(2, 30.0, 40.0),
                   window(3, 31.0, 41.0)]
        # When analyzed with warmup_windows=1,
        stats = analyze.analyze(records, warmup_windows=1)
        # Then the cold window leaves the distributions.
        self.assertEqual(stats["windows"]["n"], 2)
        self.assertEqual(stats["windows"]["warmup_excluded"], 1)
        self.assertAlmostEqual(stats["windows"]["fps"]["mean"], 30.5)

    def test_warmup_drops_first_window_per_run(self) -> None:
        # Given two runs of three windows each (H-01e),
        records = [window(1, 20.0, 90.0, "a"), window(2, 30.0, 40.0, "a"),
                   window(3, 31.0, 41.0, "a"), window(4, 21.0, 91.0, "b"),
                   window(5, 32.0, 42.0, "b"), window(6, 33.0, 43.0, "b")]
        # When analyzed with warmup_windows=1,
        stats = analyze.analyze(records, warmup_windows=1)
        # Then each run loses its own cold window, not just the first overall.
        self.assertEqual(stats["windows"]["n"], 4)
        self.assertEqual(stats["windows"]["warmup_excluded"], 2)
        self.assertAlmostEqual(stats["windows"]["fps"]["mean"], 31.5)

    def test_warmup_drops_frames_and_deltas_per_run(self) -> None:
        # Given two runs each with two frame windows and GPU reports (H-01e),
        frames = [
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 1,
             "_run": "a", "complete": True, "n": 2, "overflow": 0,
             "budget_ms": 16.67, "ms": [90.0, 91.0]},
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 2,
             "_run": "a", "complete": True, "n": 2, "overflow": 0,
             "budget_ms": 16.67, "ms": [16.6, 16.7]},
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 3,
             "_run": "b", "complete": True, "n": 2, "overflow": 0,
             "budget_ms": 16.67, "ms": [92.0, 93.0]},
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 4,
             "_run": "b", "complete": True, "n": 2, "overflow": 0,
             "budget_ms": 16.67, "ms": [16.8, 16.9]},
        ]
        first_a = gpu(5, draws=100)
        first_a["_run"] = "a"
        second_a = gpu(6, draws=200)
        second_a["_run"] = "a"
        first_b = gpu(7, draws=300)
        first_b["_run"] = "b"
        second_b = gpu(8, draws=400)
        second_b["_run"] = "b"
        # When analyzed with warmup_windows=1,
        stats = analyze.analyze(frames + [first_a, second_a, first_b, second_b],
                                warmup_windows=1)
        # Then warmup leaves frame samples and delta numerators too.
        self.assertEqual(stats["frame_samples"]["samples"], 4)
        self.assertEqual(stats["frame_samples"]["ms"]["max"], 16.9)
        self.assertEqual(stats["gpu"]["intervals"], 0)
        self.assertEqual(stats["gpu"]["totals"]["draws"], 0)

    def test_cache_lock_comes_from_deltas(self) -> None:
        # Given two guest reports with lifetime lock counters (H-01e),
        before = {"_marker": "EDEN_DEV_GUEST", "_file": "t", "_line": 1,
                  "_run": "t", "complete": True, "cpu_write_calls": 10,
                  "cpu_write_ns": 100, "cache_lock_contended": 5,
                  "cache_lock_blocked": 5}
        after = {"_marker": "EDEN_DEV_GUEST", "_file": "t", "_line": 2,
                 "_run": "t", "complete": True, "cpu_write_calls": 20,
                 "cpu_write_ns": 200, "cache_lock_contended": 8,
                 "cache_lock_blocked": 9}
        # When analyzed,
        stats = analyze.analyze([before, after])
        # Then lock stats are interval deltas, not lifetime totals.
        self.assertEqual(stats["cache_lock"]["blocked"], 4)
        self.assertEqual(stats["cache_lock"]["contended"], 3)

    def test_vulkan_cost_apis_stay_separate(self) -> None:
        # Given two reports each for two overlapping-timed APIs,
        reports = [
            {"_marker": "EDEN_VULKAN_COST", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "api": "submit",
             "calls": 10, "ns": 1000},
            {"_marker": "EDEN_VULKAN_COST", "_file": "t", "_line": 2,
             "_run": "t", "complete": True, "api": "fence_wait",
             "calls": 5, "ns": 5000},
            {"_marker": "EDEN_VULKAN_COST", "_file": "t", "_line": 3,
             "_run": "t", "complete": True, "api": "submit",
             "calls": 30, "ns": 3000},
            {"_marker": "EDEN_VULKAN_COST", "_file": "t", "_line": 4,
             "_run": "t", "complete": True, "api": "fence_wait",
             "calls": 8, "ns": 9000},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then each API keeps its own delta (overlapping series never sum).
        self.assertEqual(stats["vulkan_cost"]["submit"]["totals"]["ns"], 2000)
        self.assertEqual(stats["vulkan_cost"]["submit"]["totals"]["calls"], 20)
        self.assertEqual(stats["vulkan_cost"]["fence_wait"]["totals"]["ns"], 4000)
        self.assertNotIn("totals", stats["vulkan_cost"])

    def test_direct_memory_reports_min_and_short(self) -> None:
        # Given two headroom reports, one short,
        reports = [
            {"_marker": "EDEN_PERF_DIRECT", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "total": 100, "largest_free": 60,
             "free": 70, "regions": 4, "short": 0},
            {"_marker": "EDEN_PERF_DIRECT", "_file": "t", "_line": 2,
             "_run": "t", "complete": True, "total": 100, "largest_free": 40,
             "free": 45, "regions": 6, "short": 1},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then the worst headroom and the short count survive.
        self.assertEqual(stats["direct_memory"]["min_largest_free"], 40)
        self.assertEqual(stats["direct_memory"]["short_reports"], 1)

    def test_gpu_time_failed_counted_apart(self) -> None:
        # Given one failed and one good GPU-time report,
        reports = [
            {"_marker": "EDEN_GPU_TIME", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "failed": "ring"},
            {"_marker": "EDEN_GPU_TIME", "_file": "t", "_line": 2,
             "_run": "t", "complete": True, "wall_ms": 5000.0,
             "busy_ms": 4200.0, "submissions": 150, "max_ms": 33.5},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then failures count apart and never enter the distribution.
        self.assertEqual(stats["gpu_time"]["failed"], 1)
        self.assertEqual(stats["gpu_time"]["reports"], 1)
        self.assertEqual(stats["gpu_time"]["submissions"], 150)

if __name__ == "__main__":
    unittest.main()
