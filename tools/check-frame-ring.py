#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the H-01 per-frame ring dev-only, bounded and parser-compatible.

Unlike most check-*.py this needs no build cache: it inspects the source
tree directly, so it runs on any host with plain python3. Usage:
    python3 -B tools/check-frame-ring.py [path/to/graphics.cpp]
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "headless/graphics.cpp"
source = source_path.read_text()

# 1. Static ring storage: no allocation, ever.
assert "static std::array<float, 1024> frame_ms{};" in source
assert "static unsigned frame_ms_count = 0, frame_ms_overflow = 0;" in source
# 2. Report marker with sample count, overflow, window budget and CSV intervals.
assert "EDEN_VULKAN_FRAMES n=%u overflow=%u budget_ms=%.2f ms=" in source
# 3. Bounded store (saturate + count, never wrap) and per-window reset.
assert "frame_ms_count < frame_ms.size()" in source
assert "frame_ms_count = 0;" in source
assert "frame_ms_overflow = 0;" in source
# 3b. The reset runs after the emission inside the same report block,
# so every 5 s window starts empty (H-01a: no cross-window bleed).
emit = source.index("EDEN_VULKAN_FRAMES n=")
reset_count = source.index("frame_ms_count = 0;", emit)
reset_over = source.index("frame_ms_overflow = 0;", emit)
end = source.index("#endif", emit)
assert emit < reset_count < end and emit < reset_over < end

# 3c. A fresh window is a fresh session (one GraphicsWindow per launcher
# iteration): the first-frame branch must clear the previous title's
# unflushed samples and buckets (H-01e).
first = source.index("if (frame_sample_start < 0) {")
els = source.index("} else {", first)
for anchor in ("frame_ms_count = 0;", "frame_ms_overflow = 0;",
               "interval_hist = {};"):
    hits = [m.start() for m in re.finditer(re.escape(anchor), source)]
    assert any(first < h < els for h in hits), anchor


def dev_gated(anchor):
    """Anchor must sit between EDEN_DEV_PROFILE guard and its #endif."""
    at = source.index(anchor)
    guard = source.rfind("#ifdef EDEN_DEV_PROFILE", 0, at)
    end = source.index("#endif", at)
    assert 0 <= guard < at < end, anchor


# 4. Both the per-frame store and the report are dev-profile-only.
dev_gated("frame_ms[frame_ms_count++]")
dev_gated("EDEN_VULKAN_FRAMES n=")

# 5. No heap or growing containers on the ring's lines.
for line in source.splitlines():
    if "frame_ms" in line:
        for banned in ("new ", "malloc", "push_back", "emplace_back"):
            assert banned not in line, line.strip()

# 6. The exact emitted format feeds the maintained pipeline correctly.
sys.path.insert(0, str(root / "tools" / "perf"))
import analyze
import collect

record = collect.parse_line(
    "EDEN_VULKAN_FRAMES n=3 overflow=0 budget_ms=16.67 ms=16.7,33.4,16.6")
assert record is not None and record["complete"]
assert record["ms"] == [16.7, 33.4, 16.6]
assert record["budget_ms"] == 16.67
stats = analyze.analyze([record])
frames = stats["frame_samples"]
assert frames["samples"] == 3 and frames["mismatched"] == 0
assert frames["partial"] is False
assert abs(float(str(frames["ms"]["p50"])) - 16.7) < 1e-9
assert frames["budgeted_samples"] == 3 and frames["over_budget"] == 2
assert frames["over_20ms"] == 1 and "frame-level" in stats["windows"]["level"]

print("H-01 frame ring dev-gated, bounded and pipeline-compatible PASS")
