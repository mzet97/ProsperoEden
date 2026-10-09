#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the whole tools/perf suite (stdlib only): python3 tools/perf/test_perf.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_analyze
import test_collect
import test_compare
import test_frames
import test_pipeline


def suite() -> unittest.TestSuite:
    """Every test case of the five perf test modules."""
    loader = unittest.TestLoader()
    combined = unittest.TestSuite()
    for module in (test_collect, test_analyze, test_compare, test_frames,
                   test_pipeline):
        combined.addTests(loader.loadTestsFromModule(module))
    return combined


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)
