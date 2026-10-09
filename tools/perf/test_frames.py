#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for frame_samples.py: distributions and frame summaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze
import frame_samples


class TestFrameDistributions(unittest.TestCase):
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

    def test_percentile_p99_9_known_series(self) -> None:
        # Given the sorted series 1..100 (H-01e: FR-003 requires P99.9),
        series = list(range(1, 101))
        # When summarized,
        result = frame_samples.distribution(series)
        # Then p99.9 matches the hand-computed interpolation.
        self.assertAlmostEqual(result["p99_9"] or 0.0, 99.901)
        self.assertEqual(frame_samples.distribution([30.0])["p99_9"], 30.0)

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


class TestFrameSummaries(unittest.TestCase):
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
