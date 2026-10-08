#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end tests: the tools/perf CLI pipeline on fixture logs."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

HERE = Path(__file__).resolve().parent


def stats(windows: int) -> dict:
    """Minimal stats report with a bare window section."""
    return {"windows": {"n": windows}, "incomplete_excluded": 0}


LOG_FIXTURE = """\
[headless-startup] console_mode=docked
EDEN_DEV_SETTINGS dma_accuracy=0 gpu_accuracy=1 null_descriptor=1 descriptor_buffer=1 robustness2=0 vertex_input_dynamic=1 dyna_state=0 sparse=1 multirange=1 custom_border=0 submit_sync=0 fastmem=0
EDEN_LOADING_DONE frames=60 seconds=2.00
EDEN_GAME_VISIBLE guest_frames=8 stabilization_ms=100 smooth_frames=8
EDEN_VULKAN_FRAME frames=150 seconds=5.001000 fps=30.000 worst_ms=40.000 total=150 not_shown=0 clock_hz=60.0
EDEN_VULKAN_INTERVALS v1=140 v2=8 v3=2 v4plus=0 half=0
EDEN_DEV_GPU frame=150 mono_ns=10000000000 cpu_ns=8000000000 idle_ns=1000000 dispatch_calls=200 dispatch_ns=3000000 drain_calls=1 drain_ns=5000 present_calls=150 present_ns=150000 full_calls=0 full_ns=0 draws=1200
EDEN_DEV_GUEST cpu_write_calls=500 cpu_write_ns=4000000 cpu_read_calls=100 cpu_read_ns=500000 sync_calls=10 sync_ns=2000000 dequeue_calls=150 dequeue_ns=300000 ipc_calls=1000 ipc_ns=8000000 cache_lock_contended=5 cache_lock_blocked=1 fs_file_calls=20 fs_file_ns=100000 fs_file_bytes=4096 fs_storage_calls=5 fs_storage_ns=50000 fs_storage_bytes=8192 idle0=10/5/2 cond=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20
EDEN_FASTMEM window=1000000000 pages=100 chunks=25 direct_reads=1000 direct_writes=2000 faults=3 maps=10 unmaps=2 protects=5 kernel_calls=17 kernel_ns=9000 failures=0
EDEN_PERF_DIRECT total=12884901888 largest_free=9663676416 free=9663676416 regions=42 short=0
EDEN_VULKAN_FRAME frames=145 seconds=5.002000 fps=29.000 worst_ms=45.000 total=295 not_shown=0 clock_hz=60.0
EDEN_VULKAN_INTERVALS v1=130 v2=12 v3=3 v4plus=0 half=0
EDEN_DEV_GPU frame=295 mono_ns=15000000000 cpu_ns=12000000000 idle_ns=1800000 dispatch_calls=350 dispatch_ns=5200000 drain_calls=2 drain_ns=9000 present_calls=300 present_ns=280000 full_calls=1 full_ns=4000 draws=2100
EDEN_VULKAN_FRAME frames=155 seconds=5.000500 fps=31.000 worst_ms=50.000 total=450 not_shown=0 clock_hz=60.0
EDEN_VULKAN_INTERVALS v1=145 v2=8 v3=2 v4plus=0 half=0
EDEN_DEV_GPU frame=450 mono_ns=20000000000 cpu_ns=16000000000 idle_ns=2600000 dispatch_calls=500 dispatch_ns=7400000 drain_calls=3 drain_ns=13000 present_calls=450 present_ns=410000 full_calls=1 full_ns=4000 draws=3000
EDEN_SHADER_CACHE_LOADED
"""


def run_cli(script: str, *args: str, stdin_text: str | None = None,
            cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one tools/perf script through its real CLI surface."""
    return subprocess.run(
        [sys.executable, str(HERE / script), *args],
        input=stdin_text, capture_output=True, text=True, cwd=cwd,
        timeout=60, check=False)


class TestPerfPipeline(unittest.TestCase):
    def test_pipeline_pass_reports_pass(self) -> None:
        # Given a realistic PS5 stdout fixture,
        with tempfile.TemporaryDirectory(prefix="eden-perf-") as tmp:
            root = Path(tmp)
            (root / "session.log").write_text(LOG_FIXTURE)
            # When it flows collect -> analyze -> compare-against-itself,
            collected = run_cli("collect.py", "session.log", cwd=root)
            self.assertEqual(collected.returncode, 0, collected.stderr)
            (root / "run.jsonl").write_text(collected.stdout)
            analyzed = run_cli("analyze.py", "run.jsonl", cwd=root)
            self.assertEqual(analyzed.returncode, 0, analyzed.stderr)
            (root / "run.stats.json").write_text(analyzed.stdout)
            compared = run_cli("compare.py", "run.stats.json",
                               "run.stats.json", cwd=root)
            # Then the gate passes and the report marks it.
            self.assertEqual(compared.returncode, 0, compared.stderr)
            self.assertIn("overall: **pass**", compared.stdout)
            stats = json.loads(analyzed.stdout)
            self.assertEqual(stats["windows"]["n"], 3)
            self.assertAlmostEqual(stats["windows"]["fps"]["mean"], 30.0)
            self.assertEqual(stats["gpu"]["intervals"], 2)
            self.assertEqual(stats["loading"]["EDEN_SHADER_CACHE_LOADED"], 1)

    def test_pipeline_regression_exits_nonzero(self) -> None:
        # Given analyzed stats and a degraded copy (-10% fps, +20% worst),
        with tempfile.TemporaryDirectory(prefix="eden-perf-") as tmp:
            root = Path(tmp)
            (root / "session.log").write_text(LOG_FIXTURE)
            collected = run_cli("collect.py", "session.log", cwd=root)
            (root / "run.jsonl").write_text(collected.stdout)
            analyzed = run_cli("analyze.py", "run.jsonl", cwd=root)
            (root / "base.stats.json").write_text(analyzed.stdout)
            degraded = json.loads(analyzed.stdout)
            for key in ("mean", "p50", "min", "max"):
                degraded["windows"]["fps"][key] *= 0.9
            for key in ("mean", "p50", "min", "max"):
                degraded["windows"]["worst_ms"][key] *= 1.2
            (root / "cand.stats.json").write_text(json.dumps(degraded))
            # When compared,
            compared = run_cli("compare.py", "base.stats.json",
                               "cand.stats.json", "--json", "report.json",
                               cwd=root)
            # Then the gate fails and both reports agree.
            self.assertEqual(compared.returncode, 1, compared.stdout)
            self.assertIn("overall: **regression**", compared.stdout)
            payload = json.loads((root / "report.json").read_text())
            self.assertEqual(payload["overall"], "regression")

    def test_pipeline_partial_exits_inconclusive(self) -> None:
        # Given a session whose frame window dropped tail samples (H-01d),
        log = ("EDEN_VULKAN_FRAME frames=150 seconds=5.0 fps=30.0 worst_ms=40.0 "
               "total=150 not_shown=0 clock_hz=60.0\n"
               "EDEN_VULKAN_FRAMES n=3 overflow=3 budget_ms=16.67 ms=16.6,16.7,16.8\n")
        with tempfile.TemporaryDirectory(prefix="eden-perf-") as tmp:
            root = Path(tmp)
            (root / "session.log").write_text(log)
            collected = run_cli("collect.py", "session.log", cwd=root)
            (root / "run.jsonl").write_text(collected.stdout)
            analyzed = run_cli("analyze.py", "run.jsonl", cwd=root)
            (root / "run.stats.json").write_text(analyzed.stdout)
            # When compared against itself,
            compared = run_cli("compare.py", "run.stats.json",
                               "run.stats.json", cwd=root)
            # Then the gate is inconclusive, never a pass on partial data.
            self.assertEqual(compared.returncode, 3, compared.stdout)
            self.assertIn("overall: **inconclusive**", compared.stdout)
            self.assertIn("guest production cadence", compared.stdout)

    def test_init_baseline_validates_windows(self) -> None:
        # Given a stats file with and without counted windows,
        with tempfile.TemporaryDirectory(prefix="eden-perf-") as tmp:
            root = Path(tmp)
            (root / "good.stats.json").write_text(json.dumps(stats(3)))
            (root / "empty.stats.json").write_text(json.dumps(stats(0)))
            # When stored as baselines,
            accepted = run_cli("compare.py", "--init-baseline",
                               "good.stats.json", "baseline.json", cwd=root)
            rejected = run_cli("compare.py", "--init-baseline",
                               "empty.stats.json", "bad.json", cwd=root)
            # Then only the counted one lands.
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertTrue((root / "baseline.json").exists())
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse((root / "bad.json").exists())


if __name__ == "__main__":
    unittest.main()
