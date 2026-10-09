#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for compare verdicts and report rendering."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare
import compare_metrics


def stats(windows: int, fps_mean: float, fps_stdev: float,
          worst_mean: float, worst_stdev: float, **extra: object) -> dict:
    """Minimal stats report with window fps/worst distributions."""
    report = {
        "windows": {
            "n": windows,
            "fps": {"n": windows, "mean": fps_mean, "stdev": fps_stdev,
                    "min": fps_mean, "max": fps_mean, "p50": fps_mean,
                    "p95": fps_mean, "p99": fps_mean},
            "worst_ms": {"n": windows, "mean": worst_mean,
                         "stdev": worst_stdev, "min": worst_mean,
                         "max": worst_mean, "p50": worst_mean,
                         "p95": worst_mean, "p99": worst_mean},
        },
        "incomplete_excluded": 0,
    }
    report.update(extra)
    return report


def spec_for(key: str) -> compare_metrics.MetricSpec:
    """The registered spec for key (tests fail loudly on typos)."""
    for spec in compare_metrics.SPECS:
        if spec.key == key:
            return spec
    raise AssertionError(f"unknown metric {key}")


class TestCompareVerdicts(unittest.TestCase):
    def test_change_within_band_is_same(self) -> None:
        # Given a +1.67% fps move under the 2% triage band,
        base = stats(6, 30.0, 0.1, 40.0, 0.1)
        cand = stats(6, 30.5, 0.1, 40.0, 0.1)
        # When judged,
        result = compare_metrics.judge(spec_for("fps_mean"), base, cand, 2.0)
        # Then the verdict is same, not better.
        self.assertIs(result.outcome, compare_metrics.Outcome.SAME)
        self.assertAlmostEqual(result.change_pct or 0.0, 1.6667, places=3)

    def test_improvement_beyond_band_is_better(self) -> None:
        # Given a +5% fps move with tight distributions,
        base = stats(6, 30.0, 0.1, 40.0, 0.1)
        cand = stats(6, 31.5, 0.1, 40.0, 0.1)
        # When judged,
        result = compare_metrics.judge(spec_for("fps_mean"), base, cand, 2.0)
        # Then higher-better wins.
        self.assertIs(result.outcome, compare_metrics.Outcome.BETTER)

    def test_regression_beyond_band_is_worse(self) -> None:
        # Given a +5% worst-frametime move (lower is better),
        base = stats(6, 30.0, 0.1, 40.0, 0.1)
        cand = stats(6, 30.0, 0.1, 42.0, 0.1)
        # When judged,
        result = compare_metrics.judge(spec_for("worst_mean"), base, cand, 2.0)
        # Then the verdict is worse.
        self.assertIs(result.outcome, compare_metrics.Outcome.WORSE)

    def test_missing_data_is_nodata(self) -> None:
        # Given reports without the metric path,
        result = compare_metrics.judge(spec_for("fps_mean"), {}, {}, 2.0)
        # When judged,
        # Then the verdict admits the gap instead of inventing zero.
        self.assertIs(result.outcome, compare_metrics.Outcome.NODATA)
        self.assertIsNone(result.change_pct)

    def test_zero_baseline_is_nodata(self) -> None:
        # Given a zero baseline (relative change undefined),
        base = stats(6, 0.0, 0.0, 40.0, 0.1)
        cand = stats(6, 30.0, 0.1, 40.0, 0.1)
        # When judged,
        result = compare_metrics.judge(spec_for("fps_mean"), base, cand, 2.0)
        # Then no percent is fabricated.
        self.assertIs(result.outcome, compare_metrics.Outcome.NODATA)
        self.assertIsNone(compare_metrics.percent_change(0.0, 30.0))

    def test_overlapping_distributions_cap_to_same(self) -> None:
        # Given a +3% fps move inside the combined spread,
        base = stats(6, 30.0, 2.0, 40.0, 0.1)
        cand = stats(6, 30.9, 2.0, 40.0, 0.1)
        # When judged,
        result = compare_metrics.judge(spec_for("fps_mean"), base, cand, 2.0)
        # Then noise caps the call at same with a rerun note.
        self.assertIs(result.outcome, compare_metrics.Outcome.SAME)
        self.assertIn("overlap", result.detail)

    def test_per_interval_normalizes_run_length(self) -> None:
        # Given equal per-interval dispatch where intervals trail windows (H-01e:
        # delta totals cover measured intervals, not counted windows),
        base = stats(3, 30.0, 0.1, 40.0, 0.1,
                     gpu={"intervals": 2, "totals": {"dispatch_ns": 1000}})
        cand = stats(4, 30.0, 0.1, 40.0, 0.1,
                     gpu={"intervals": 4, "totals": {"dispatch_ns": 2000}})
        # When judged,
        result = compare_metrics.judge(spec_for("dispatch_ns"), base, cand, 2.0)
        # Then raw totals never compare; the normalized move is zero.
        self.assertIs(result.outcome, compare_metrics.Outcome.SAME)
        self.assertAlmostEqual(result.base or -1.0, 500.0)
        self.assertAlmostEqual(result.cand or -1.0, 500.0)

    def test_within_vsync_share_counts_fast_bucket(self) -> None:
        # Given buckets split between the fast and one-vsync ranges (H-01e),
        buckets: dict[str, object] = {"v1": 80, "half": 10, "v2": 10,
                                      "v3": 0, "v4plus": 0}
        base = stats(6, 30.0, 0.1, 40.0, 0.1, intervals={"buckets": buckets})
        cand = stats(6, 30.0, 0.1, 40.0, 0.1, intervals={"buckets": dict(buckets)})
        # When judged,
        result = compare_metrics.judge(spec_for("within_vsync_share"), base, cand, 2.0)
        # Then both favorable buckets feed the higher-is-better share.
        self.assertIs(result.outcome, compare_metrics.Outcome.SAME)
        self.assertAlmostEqual(result.base or 0.0, 0.9)

    def test_frame_p95_regression_is_critical(self) -> None:
        # Given frame p95 rising +10% (lower is better),
        base = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"ms": {"n": 900, "mean": 17.0, "stdev": 1.0,
                                           "min": 16.0, "max": 40.0, "p50": 16.7,
                                           "p95": 20.0, "p99": 30.0}})
        cand = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"ms": {"n": 900, "mean": 17.5, "stdev": 1.0,
                                           "min": 16.0, "max": 42.0, "p50": 16.8,
                                           "p95": 22.0, "p99": 32.0}})
        # When judged,
        result = compare_metrics.judge(spec_for("frame_p95_ms"), base, cand, 2.0)
        # Then the verdict is worse on a critical stutter metric.
        self.assertIs(result.outcome, compare_metrics.Outcome.WORSE)
        self.assertTrue(spec_for("frame_p95_ms").critical)

    def test_frame_over20_share_compares_length_free(self) -> None:
        # Given equal over-budget shares over different sample counts,
        base = stats(2, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"samples": 1000, "over_20ms": 50})
        cand = stats(3, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"samples": 2000, "over_20ms": 100})
        # When judged,
        result = compare_metrics.judge(spec_for("frame_over20_share"), base, cand, 2.0)
        # Then the 5% share compares equal despite different run lengths.
        self.assertIs(result.outcome, compare_metrics.Outcome.SAME)
        self.assertAlmostEqual(result.base or 0.0, 0.05)

    def test_partial_frames_block_verdicts(self) -> None:
        # Given frame samples flagged partial by overflow (H-01a),
        base = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": True, "ms": {
                         "n": 900, "mean": 17.0, "stdev": 1.0, "min": 16.0,
                         "max": 40.0, "p50": 16.7, "p95": 20.0, "p99": 30.0}})
        cand = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": False, "ms": {
                         "n": 900, "mean": 17.5, "stdev": 1.0, "min": 16.0,
                         "max": 42.0, "p50": 16.8, "p95": 30.0, "p99": 32.0}})
        # When judged,
        result = compare_metrics.judge(spec_for("frame_p95_ms"), base, cand, 2.0)
        # Then no verdict is issued on incomplete window samples.
        self.assertIs(result.outcome, compare_metrics.Outcome.NODATA)
        self.assertIn("overflow", result.detail)

    def test_frame_overbudget_share_is_diagnostic(self) -> None:
        # Given equal over-budget shares over different sample counts (H-01d:
        # budget semantics unvalidated, so no verdict may issue),
        base = stats(2, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": False, "budgeted_samples": 1000,
                                    "over_budget": 50})
        cand = stats(3, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": False, "budgeted_samples": 2000,
                                    "over_budget": 100})
        # When judged,
        result = compare_metrics.judge(spec_for("frame_overbudget_share"), base, cand, 2.0)
        # Then numbers report as diagnostic context, never as a verdict.
        self.assertIs(result.outcome, compare_metrics.Outcome.INFO)
        self.assertAlmostEqual(result.base or 0.0, 0.05)
        self.assertIn("diagnostic", result.detail)

    def test_frame_over2x_share_is_diagnostic(self) -> None:
        # Given equal far-over-budget shares (H-01d),
        base = stats(2, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": False, "budgeted_samples": 1000,
                                    "over_2x_budget": 10})
        cand = stats(3, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"partial": False, "budgeted_samples": 2000,
                                    "over_2x_budget": 20})
        # When judged,
        result = compare_metrics.judge(spec_for("frame_over2x_share"), base, cand, 2.0)
        # Then it reports the 1% share as diagnostic context.
        self.assertIs(result.outcome, compare_metrics.Outcome.INFO)
        self.assertAlmostEqual(result.base or 0.0, 0.01)

    def test_info_metrics_never_gate(self) -> None:
        # Given a doubled JIT compilation count (startup-skewed),
        base = stats(6, 30.0, 0.1, 40.0, 0.1,
                     jit={"0": {"EDEN_PERF_JIT": {"totals": {"compilations": 100}}}})
        cand = stats(6, 30.0, 0.1, 40.0, 0.1,
                     jit={"0": {"EDEN_PERF_JIT": {"totals": {"compilations": 200}}}})
        # When judged,
        result = compare_metrics.judge(spec_for("jit_compilations"), base, cand, 2.0)
        # Then it reports context, not a verdict.
        self.assertIs(result.outcome, compare_metrics.Outcome.INFO)
        self.assertAlmostEqual(result.change_pct or 0.0, 100.0)

    def test_overall_regression_only_on_critical(self) -> None:
        # Given single-metric result sets,
        worse_critical = compare_metrics.MetricResult("fps_mean", "fps", "fps", 30.0,
                                              27.0, -10.0, compare_metrics.Outcome.WORSE, "")
        worse_trivia = compare_metrics.MetricResult("fps_p50", "p50", "fps", 30.0,
                                            27.0, -10.0, compare_metrics.Outcome.WORSE, "")
        # When gated,
        # Then only a critical worse flips the gate.
        self.assertEqual(compare_metrics.overall([worse_critical]), "regression")
        self.assertEqual(compare_metrics.overall([worse_trivia]), "inconclusive")
        self.assertEqual(compare_metrics.overall([]), "inconclusive")

    def test_overall_needs_critical_evidence(self) -> None:
        # Given verdicts with no usable critical measurement (H-01e),
        nodata = compare_metrics.MetricResult("fps_mean", "fps", "fps", None,
                                              None, None, compare_metrics.Outcome.NODATA,
                                              "missing data")
        same_trivia = compare_metrics.MetricResult("fps_p50", "p50", "fps", 30.0,
                                                   30.0, 0.0, compare_metrics.Outcome.SAME, "")
        # When gated,
        # Then the gate refuses to pass on empty evidence.
        self.assertEqual(compare_metrics.overall([nodata]), "inconclusive")
        self.assertEqual(compare_metrics.overall([same_trivia]), "inconclusive")

    def test_overall_inconclusive_when_frames_blocked(self) -> None:
        # Given a frame verdict blocked by overflow (H-01d),
        blocked = compare_metrics.MetricResult(
            "frame_p95_ms", "p95", "ms", 20.0, 22.0, None,
            compare_metrics.Outcome.NODATA, "overflow>0: incomplete window samples",
            blocked=True)
        worse_critical = compare_metrics.MetricResult(
            "fps_mean", "fps", "fps", 30.0, 27.0, -10.0,
            compare_metrics.Outcome.WORSE, "")
        blocked_trivia = compare_metrics.MetricResult(
            "fps_mean", "fps", "fps", 30.0, 30.0, 0.0,
            compare_metrics.Outcome.SAME, "", blocked=True)
        # When gated,
        # Then blocked frames force inconclusive, a proven regression wins,
        # and the block flag on non-frame keys is ignored.
        self.assertEqual(compare_metrics.overall([blocked]), "inconclusive")
        self.assertEqual(compare_metrics.overall([worse_critical, blocked]), "regression")
        self.assertEqual(compare_metrics.overall([blocked_trivia]), "pass")

    def test_triage_band_validation(self) -> None:
        # Given --triage-band payloads (H-01e),
        # When parsed,
        # Then finite non-negative values pass and the rest exit 2.
        self.assertEqual(compare.triage_band_or_exit("2.5"), 2.5)
        self.assertEqual(compare.triage_band_or_exit("0"), 0.0)
        for raw in ("-1", "nan", "inf", "-inf", "xx"):
            with self.subTest(raw=raw):
                with self.assertRaises(SystemExit) as raised:
                    compare.triage_band_or_exit(raw)
                self.assertEqual(raised.exception.code, 2)

    def test_report_states_frame_provenance_and_cadence(self) -> None:
        # Given two reports with frame samples (H-01d),
        base = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"windows": 2, "samples": 600,
                                    "budgets": [16.67], "overflow": 0,
                                    "partial": False})
        cand = stats(6, 30.0, 0.1, 40.0, 0.1,
                     frame_samples={"windows": 2, "samples": 590,
                                    "budgets": [16.67], "overflow": 0,
                                    "partial": False})
        # When rendered,
        results = compare_metrics.compare_reports(base, cand, 2.0)
        markdown = compare.render_markdown("b", "c", base, cand, results, 2.0)
        # Then sample provenance and the production-cadence caveat show.
        self.assertIn("600 samples", markdown)
        self.assertIn("590 samples", markdown)
        self.assertIn("guest production cadence", markdown)


if __name__ == "__main__":
    unittest.main()
