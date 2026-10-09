#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for collect.py: EDEN_* line parsing. Stdlib only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect


class TestCollectParse(unittest.TestCase):
    def test_frame_line_parses_typed_fields(self) -> None:
        # Given a well-formed Vulkan frame window line,
        line = ("EDEN_VULKAN_FRAME frames=150 seconds=5.001000 fps=29.994 "
                "worst_ms=45.100 total=150 not_shown=0 clock_hz=60.0")
        # When parsed,
        record = collect.parse_line(line)
        # Then every field carries its narrow type and the record is complete.
        assert record is not None
        self.assertEqual(record["_marker"], "EDEN_VULKAN_FRAME")
        self.assertTrue(record["complete"])
        self.assertEqual(record["frames"], 150)
        self.assertAlmostEqual(float(str(record["seconds"])), 5.001)
        self.assertAlmostEqual(float(str(record["fps"])), 29.994)
        self.assertAlmostEqual(float(str(record["worst_ms"])), 45.1)
        self.assertEqual(record["total"], 150)
        self.assertEqual(record["not_shown"], 0)
        self.assertAlmostEqual(float(str(record["clock_hz"])), 60.0)

    def test_non_eden_line_returns_none(self) -> None:
        # Given lines that are not EDEN_* records,
        # When parsed,
        # Then they are skipped silently.
        self.assertIsNone(collect.parse_line(""))
        self.assertIsNone(collect.parse_line("[headless-startup] console_mode=docked"))
        self.assertIsNone(collect.parse_line("some log mentioning EDEN_ mid-line"))

    def test_incomplete_frame_flags_missing_keys(self) -> None:
        # Given a frame line missing required keys,
        record = collect.parse_line("EDEN_VULKAN_FRAME frames=150 fps=30.0")
        # When parsed,
        # Then it is kept but flagged with exactly the missing keys.
        assert record is not None
        self.assertFalse(record["complete"])
        missing = record["_missing"]
        assert isinstance(missing, list)
        self.assertEqual(sorted(missing), ["seconds", "total", "worst_ms"])

    def test_guest_cond_and_idle_parse(self) -> None:
        # Given a guest report with a cond vector and idle triples,
        line = ("EDEN_DEV_GUEST cpu_write_calls=500 cpu_write_ns=4000000 "
                "idle0=10/5/2 cond=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
        # When parsed,
        record = collect.parse_line(line)
        # Then the vector and triple become structured values.
        assert record is not None
        self.assertEqual(record["idle0"], [10, 5, 2])
        cond = record["cond"]
        assert isinstance(cond, list)
        self.assertEqual(cond, list(range(1, 21)))

    def test_hex_keys_parse_as_hex(self) -> None:
        # Given %llx-printed keys (plain hex, no 0x prefix),
        record = collect.parse_line("EDEN_FASTMEM window=1000000000 pages=100 faults=0")
        # When parsed,
        # Then they decode as base 16, while decimal keys stay decimal.
        assert record is not None
        self.assertEqual(record["window"], 0x1000000000)
        self.assertEqual(record["pages"], 100)

    def test_gpu_time_failed_form_is_complete(self) -> None:
        # Given the ring-failure form with no numbers,
        record = collect.parse_line("EDEN_GPU_TIME failed=ring")
        # When parsed,
        # Then it counts as complete (absence of numbers is the signal).
        assert record is not None
        self.assertTrue(record["complete"])
        self.assertEqual(record["failed"], "ring")

    def test_vulkan_cost_keeps_api_name(self) -> None:
        # Given an opt-in API wall-time line,
        record = collect.parse_line("EDEN_VULKAN_COST api=graphics_pipeline calls=12 ns=3456")
        # When parsed,
        # Then the api tag stays a string and counters are ints.
        assert record is not None
        self.assertEqual(record["api"], "graphics_pipeline")
        self.assertEqual(record["calls"], 12)
        self.assertEqual(record["ns"], 3456)

    def test_bare_marker_is_complete(self) -> None:
        # Given a marker with no k=v pairs and no required keys,
        record = collect.parse_line("EDEN_SHADER_CACHE_LOADED")
        # When parsed,
        # Then it is a complete record carrying only the marker.
        assert record is not None
        self.assertTrue(record["complete"])
        self.assertEqual(record["_marker"], "EDEN_SHADER_CACHE_LOADED")

    def test_value_fallback_chain(self) -> None:
        # Given tokens of each shape,
        # When converted,
        # Then int beats float beats string, and bad hex stays a string.
        self.assertEqual(collect.parse_value("frames", "150"), 150)
        self.assertEqual(collect.parse_value("fps", "30.0"), 30.0)
        self.assertEqual(collect.parse_value("api", "submit"), "submit")
        self.assertEqual(collect.parse_value("window", "zz"), "zz")

    def test_non_numeric_required_field_is_incomplete(self) -> None:
        # Given a frame line whose fps is not a number (H-01e),
        line = ("EDEN_VULKAN_FRAME frames=150 seconds=5.0 fps=oops "
                "worst_ms=40.0 total=150 not_shown=0 clock_hz=60.0")
        # When parsed,
        record = collect.parse_line(line)
        # Then presence alone does not pass: the type violation excludes it.
        assert record is not None
        self.assertFalse(record["complete"])
        self.assertIn("fps:bad-type", record["_missing"])

    def test_non_finite_required_field_is_incomplete(self) -> None:
        # Given required fields with inf/nan payloads (H-01e),
        inf = collect.parse_line(
            "EDEN_VULKAN_FRAME frames=150 seconds=5.0 fps=inf worst_ms=40.0 total=150")
        nan = collect.parse_line("EDEN_GPU_TIME wall_ms=nan busy_ms=1.0 submissions=2")
        # When parsed,
        # Then neither counts as complete.
        assert inf is not None and nan is not None
        self.assertFalse(inf["complete"])
        self.assertFalse(nan["complete"])

    def test_int_tolerated_for_float_field(self) -> None:
        # Given whole-number payloads on float fields (H-01e),
        line = ("EDEN_VULKAN_FRAME frames=150 seconds=5 fps=30 "
                "worst_ms=40 total=150")
        # When parsed,
        record = collect.parse_line(line)
        # Then JSON numbers of either shape are accepted.
        assert record is not None
        self.assertTrue(record["complete"])
        self.assertEqual(record["fps"], 30)

    def test_empty_api_name_is_incomplete(self) -> None:
        # Given a Vulkan-cost line with an empty api tag (H-01e),
        record = collect.parse_line("EDEN_VULKAN_COST api= calls=1 ns=2")
        # When parsed,
        # Then the string-typed required key rejects the empty value.
        assert record is not None
        self.assertFalse(record["complete"])

    def test_malformed_idle_triple_stays_string(self) -> None:
        # Given an idle token that is not a triple,
        # When converted,
        # Then the raw text survives instead of raising.
        self.assertEqual(collect.parse_idle_triple("10/5"), "10/5")
        self.assertEqual(collect.parse_idle_triple("10/x/2"), "10/x/2")

    def test_frames_ms_parses_float_list(self) -> None:
        # Given a per-frame interval line (H-01),
        line = "EDEN_VULKAN_FRAMES n=4 overflow=0 budget_ms=16.67 ms=16.7,16.6,33.4,16.7"
        # When parsed,
        record = collect.parse_line(line)
        # Then intervals become floats and the record is complete.
        assert record is not None
        self.assertTrue(record["complete"])
        self.assertEqual(record["n"], 4)
        self.assertEqual(record["overflow"], 0)
        self.assertEqual(record["ms"], [16.7, 16.6, 33.4, 16.7])

    def test_frames_malformed_ms_is_incomplete(self) -> None:
        # Given a frames line with a non-numeric interval,
        line = "EDEN_VULKAN_FRAMES n=2 overflow=0 budget_ms=16.67 ms=16.7,xx"
        # When parsed,
        record = collect.parse_line(line)
        # Then the raw text survives but the record is excluded downstream.
        assert record is not None
        self.assertFalse(record["complete"])
        self.assertEqual(record["ms"], "16.7,xx")

    def test_frames_budget_required(self) -> None:
        # Given frames lines with and without the window budget (H-01c),
        with_budget = collect.parse_line(
            "EDEN_VULKAN_FRAMES n=2 overflow=0 budget_ms=16.67 ms=16.6,16.7")
        without_budget = collect.parse_line(
            "EDEN_VULKAN_FRAMES n=2 overflow=0 ms=16.6,16.7")
        # When parsed,
        # Then the budget is a float, and its absence is incomplete.
        assert with_budget is not None and without_budget is not None
        self.assertTrue(with_budget["complete"])
        self.assertEqual(with_budget["budget_ms"], 16.67)
        self.assertFalse(without_budget["complete"])


if __name__ == "__main__":
    unittest.main()
