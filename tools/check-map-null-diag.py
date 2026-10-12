#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the H3 null-mapping diagnostic pinned, sane and self-sufficient.

The dev-only EDEN_MAP_NULL probe is injected into Eden's memory.cpp by a
CMake string patch (headless/CMakeLists.txt), like the unmapped tracer.
This check inspects the committed tree directly, so the structural part
runs on any host with plain python3:

    python3 -B tools/check-map-null-diag.py

When an Eden checkout is present (.deps/mirror-*/src/core/memory.cpp, as in
`make test` after `make deps`), it also verifies the pin against the real
Eden source. Without one, that part reports SKIP (honest, not green).
"""
import glob
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake_path = root / "headless/CMakeLists.txt"
cmake = cmake_path.read_text()

# 1. Exactly one diagnostic block, anchored on its pin variable.
assert cmake.count("mapnull_old") >= 2, "map-null patch block missing"
block_at = cmake.index("Null-mapping diagnostic (H3)")
inner_end = cmake.index("endif()", block_at)
block = cmake[block_at:cmake.index("endif()", inner_end + 1)]

# 2. The pin names Eden's mapping assert; configure still fails on drift.
assert "memory mapping base yield a nullptr within the table" in block
assert "Pinned mapping assert changed" in block

# 3. Throttled probe markers, first hits plus periodic totals.
assert block.count("EDEN_MAP_NULL ") == 1, "first-hit marker"
assert block.count("EDEN_MAP_NULL_TOTAL") == 1, "totals marker"
assert "eden_mapnull_total" in block and "eden_mapnull_traced" in block
assert "% 1024 == 0" in block

# 4. Only names in scope at the assert site (MapPages loop body).
for anchor in ("entries[base].Pointer()", "GetInteger(target)", "host_ptr",
               "base << YUZU_PAGEBITS", "system.DeviceMemory()"):
    assert anchor in block, anchor

# 5. Self-sufficient: its own <atomic> for the throttle, no block-order
# dependency on the tracer's prepended includes.
assert '#include <atomic>\\n${mapnull_source}' in block

# 6. The decoded C++ snippet alone (CMake's own syntax is validated at
# configure time) is brace/paren balanced.
decoded = block
for escaped, plain in (("\\n", "\n"), ('\\"', '"')):
    decoded = decoded.replace(escaped, plain)
start = decoded.index("if (!page_table.entries[base].Pointer()) {")
end = decoded.index("\n            }", start) + len("\n            }")
snippet = decoded[start:end]
assert snippet.count("{") == snippet.count("}"), "brace balance"
assert snippet.count("(") == snippet.count(")"), "paren balance"

# 7. The H3 log fix (same assert, all builds): the proven-benign assert
# becomes a throttled warning. Unconditional by design (no EDEN_DEV_PROFILE
# anywhere in the block): the spam hits every build, the store is identical.
fix_at = cmake.index("MapPages null-pointer assert (H3 fix)")
fix_tail = 'list(APPEND core_sources "${PORT_BUILD_DIR}/memory.cpp")'
fix_end = cmake.index(fix_tail, fix_at) + len(fix_tail)
fix = cmake[fix_at:fix_end]
assert "EDEN_DEV_PROFILE" not in fix, "H3 fix must be unconditional"
assert "known benign edge" in fix and "eden_mapnull_assert_shown" in fix
assert "<atomic>" in fix
assert "H3 log fix needs EDEN_A32_FASTMEM" in fix, "clear guard, not a cryptic READ failure"

# 8. Against real Eden source when a checkout exists: the pinned commit
# from UPSTREAM.json wins (stale mirrors may linger in .deps).
mirrors = sorted(glob.glob(str(root / ".deps/mirror-*/src/core/memory.cpp")))
if not mirrors:
    print("SKIP pin-vs-source: no .deps/mirror-*/src/core/memory.cpp "
          "(structural checks passed)")
    sys.exit(0)
eden_commit = ""
try:
    manifest = json.loads((root / "UPSTREAM.json").read_text())
    eden_commit = str(manifest.get("eden_commit", ""))
except (OSError, ValueError):
    eden_commit = ""
pinned = [m for m in mirrors if eden_commit and eden_commit in m]
eden_path = Path(pinned[0] if pinned else mirrors[0])
eden = eden_path.read_text()
pin = "memory mapping base yield a nullptr within the table"
assert eden.count(pin) == 1, f"pin must match {eden_path} exactly once"
print(f"OK map-null diagnostic ({eden_path})")
