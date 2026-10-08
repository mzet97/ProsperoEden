#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for analyze.py: deltas, distributions, report assembly."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
import frame_samples


def window(line: int, fps: float, worst_ms: float) -> dict:
    """One complete 5 s Vulkan frame window record."""
    return {"_marker": "EDEN_VULKAN_FRAME", "_file": "t", "_line": line,
            "_run": "t", "complete": True, "frames": 150, "seconds": 5.0,
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


class TestAnalyzeDistributions(unittest.TestCase):
    def test_percentile_known_series(self) -> None:
        # Given the sorted series 1..100,
        series = list(range(1, 101))
        # When percentiles are taken,
        # Then they match the hand-computed linear interpolation.
        self.assertAlmostEqual(frame_samples.percentile(series, 50.0) or 0.0, 50.5)
        self.assertAlmostEqual(frame_samples.percentile(series, 95.0) or 0.0, 95.05)
        self.assertAlmostEqual(frame_samples.percentile(series, 99.0) or 0.0, 99.01)

    def test_percentile_edges(self) -> None:
        # Given empty and single-element series,
        # When percentiles are taken,
        # Then empty is None and single echoes the value.
        self.assertIsNone(frame_samples.percentile([], 50.0))
        self.assertEqual(frame_samples.percentile([7.5], 99.0), 7.5)

    def test_distribution_single_value(self) -> None:
        # Given one sample,
        result = frame_samples.distribution([30.0])
        # When summarized,
        # Then spread is zero and every rank echoes the sample.
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["stdev"], 0.0)
        self.assertEqual(result["p50"], 30.0)
        self.assertEqual(result["min"], 30.0)
        self.assertEqual(result["max"], 30.0)

    def test_distribution_empty(self) -> None:
        # Given no samples,
        # When summarized,
        # Then only the zero count exists (no invented spread).
        self.assertEqual(frame_samples.distribution([]), {"n": 0})


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

    def test_frames_summarize_real_percentiles(self) -> None:
        # Given two per-frame windows (5 + 3 intervals, one overflow),
        reports = [
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "n": 5, "overflow": 1,
             "ms": [16.7, 16.6, 16.8, 33.4, 16.7]},
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 2,
             "_run": "t", "complete": True, "n": 3, "overflow": 0,
             "ms": [16.7, 50.1, 16.6]},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then percentiles come from the 8 real samples with budgets counted.
        frames = stats["frame_samples"]
        self.assertEqual(frames["windows"], 2)
        self.assertEqual(frames["samples"], 8)
        self.assertEqual(frames["overflow"], 1)
        self.assertEqual(frames["mismatched"], 0)
        self.assertAlmostEqual(frames["ms"]["p50"], 16.7)
        self.assertEqual(frames["over_20ms"], 2)
        self.assertEqual(frames["over_33ms"], 1)
        self.assertEqual(frames["over_50ms"], 1)
        self.assertIn("frame-level", stats["windows"]["level"])

    def test_frames_length_mismatch_excluded(self) -> None:
        # Given a frames record whose list disagrees with n,
        reports = [
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "n": 5, "overflow": 0,
             "ms": [16.7, 16.6]},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then it counts as mismatched and contributes no samples.
        frames = stats["frame_samples"]
        self.assertEqual(frames["mismatched"], 1)
        self.assertEqual(frames["samples"], 0)
        self.assertEqual(frames["ms"], {"n": 0})

    def test_frames_overflow_marks_partial(self) -> None:
        # Given a window that dropped tail samples (H-01a),
        reports = [
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "n": 2, "overflow": 3,
             "budget_ms": 16.67, "ms": [16.6, 16.7]},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then the samples stay but the set is flagged partial.
        frames = stats["frame_samples"]
        self.assertEqual(frames["samples"], 2)
        self.assertEqual(frames["overflow"], 3)
        self.assertTrue(frames["partial"])

    def test_frames_budget_relative_counts(self) -> None:
        # Given a 30 FPS window plus an unknown-budget one (H-01c),
        reports = [
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 1,
             "_run": "t", "complete": True, "n": 4, "overflow": 0,
             "budget_ms": 33.33, "ms": [33.3, 33.4, 50.0, 16.7]},
            {"_marker": "EDEN_VULKAN_FRAMES", "_file": "t", "_line": 2,
             "_run": "t", "complete": True, "n": 2, "overflow": 0,
             "budget_ms": 0.0, "ms": [16.7, 50.0]},
        ]
        # When analyzed,
        stats = analyze.analyze(reports)
        # Then budget-relative counts cover only budgeted samples,
        # while absolute thresholds still cover everything.
        frames = stats["frame_samples"]
        self.assertEqual(frames["samples"], 6)
        self.assertEqual(frames["budgeted_samples"], 4)
        self.assertEqual(frames["budgets"], [33.33])
        self.assertEqual(frames["over_budget"], 2)
        self.assertEqual(frames["over_2x_budget"], 0)
        self.assertEqual(frames["over_20ms"], 4)


if __name__ == "__main__":
    unittest.main()
