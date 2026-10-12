#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the BOW GMMU-gap diagnostic pinned, sane and self-sufficient.

The dev-only EDEN_GMMU_GAP probe is injected into Eden's
core/device_memory_manager.inc by a CMake derived-header patch
(headless/CMakeLists.txt), following the slab_helpers precedent. This check
inspects the committed tree directly, so the structural part runs on any
host with plain python3:

    python3 -B tools/check-gmmu-gap-diag.py

When an Eden checkout is present (.deps/mirror-*/src (as in `make test`
after `make deps`), it also verifies the pin against the real Eden source.
Without one, that part reports SKIP (honest, not green).
"""
import glob
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake_path = root / "headless/CMakeLists.txt"
cmake = cmake_path.read_text()

# 1. Exactly one diagnostic block, anchored on its pin variable.
assert cmake.count("gmmu_old") >= 2, "GMMU gap patch block missing"
block_at = cmake.index("GMMU gap diagnostic (BOW)")
inner_end = cmake.index("endif()", block_at)
block = cmake[block_at:cmake.index("endif()", inner_end + 1)]

# 2. The pin names the device-read fault site; configure still fails on drift.
assert "std::memset(dest_pointer, 0, copy_amount);" in block
assert "Pinned device-read fault site changed" in block

# 3. Throttled probe markers, first events plus periodic totals.
assert block.count("EDEN_GMMU_GAP ") == 1, "first-event marker"
assert block.count("EDEN_GMMU_GAP_TOTAL") == 1, "totals marker"
assert "eden_gmmu_total" in block and "eden_gmmu_events" in block
assert "% 512 == 0" in block

# 4. Only names in scope at the fault lambdas, plus the site tag trick
# (__PRETTY_FUNCTION__ names the enclosing ReadBlock variant; verified on
# the build clang, /tmp/pretty_test.cpp is not kept).
for anchor in ("tracked_entries", "__PRETTY_FUNCTION__", "ReadBlockUnsafe",
               "current_vaddr", "YUZU_PAGESIZE"):
    assert anchor in block, anchor

# 5. Self-sufficient: its own <cstring> for the site tag.
assert "string(PREPEND gmmu_source" in block and "<cstring>" in block

# 6. Derived-header shadowing (slab_helpers precedent): read from src,
# write under PORT_BUILD_DIR/include. (The set() lives above the gate; see 7.)
assert 'set(gmmu_header "core/device_memory_manager.inc")' in cmake
assert '"${PORT_BUILD_DIR}/include/${gmmu_header}"' in block

# 7. No linger into other configs sharing the build dir: without the probe
# the derived header is removed, so the build uses Eden's original. The path
# variable must be set above the gate, or the else() removes an empty path.
assert "file(REMOVE" in block and "${gmmu_header}.in" in block
assert cmake.index('set(gmmu_header "core/device_memory_manager.inc")') < block_at

# 8. The decoded C++ snippet alone (CMake's own syntax is validated at
# configure time) is brace/paren balanced.
decoded = block
for escaped, plain in (("\\n", "\n"), ('\\"', '"')):
    decoded = decoded.replace(escaped, plain)
start = decoded.index("static std::atomic<unsigned> eden_gmmu_total")
start = decoded.rindex("{", 0, start)
end = decoded.index("\n            }", start) + len("\n            }")
snippet = decoded[start:end]
assert snippet.count("{") == snippet.count("}"), "brace balance"
assert snippet.count("(") == snippet.count(")"), "paren balance"

# 9. Against real Eden source when a checkout exists: the pinned commit
# from UPSTREAM.json wins (stale mirrors may linger in .deps). The pin
# matches BOTH read fault sites on purpose (safe + unsafe share the
# snippet; the site tag tells them apart).
mirrors = sorted(glob.glob(str(root / ".deps/mirror-*/src/core/device_memory_manager.inc")))
if not mirrors:
    print("SKIP pin-vs-source: no Eden device_memory_manager.inc "
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
pin = "std::memset(dest_pointer, 0, copy_amount);"
assert eden.count(pin) == 2, f"pin must match {eden_path} exactly twice (safe+unsafe)"
print(f"OK GMMU gap diagnostic ({eden_path})")
