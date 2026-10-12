#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep the unmapped-read tracer pinned and gated at the CMake layer only.

The dev-only EDEN_UNMAPPED_TRACE probe is injected into Eden's memory.cpp
by a CMake string patch (headless/CMakeLists.txt). Core compiles WITHOUT
EDEN_DEV_PROFILE (see compile_commands.json: no -D flag on the derived
TU), so an inner #ifdef inside the injected code silently compiles the
probe out -- exactly the 8fd18e4 regression this check guards. The outer
CMake if(EDEN_DEV_PROFILE) is the only gate.

Source-tree only, plain python3:
    python3 -B tools/check-unmapped-tracer.py

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

# 1. Exactly one tracer block, opened by the outer CMake gate.
anchor = "if(EDEN_DEV_PROFILE)\n    # Unmapped low-address read tracer"
assert anchor in cmake, "tracer block missing or gate moved"
block_at = cmake.index("# Unmapped low-address read tracer")

# 2. NO inner #ifdef in the injected snippet (the 8fd18e4 regression):
# between string(REPLACE and write_derived the probe must be unconditional.
replace_at = cmake.index("string(REPLACE \"${unmapped_old}\"", block_at)
write_at = cmake.index("write_derived(\"${PORT_BUILD_DIR}/memory.cpp\"", replace_at)
snippet = cmake[replace_at:write_at]
assert "#ifdef" not in snippet and "#endif" not in snippet, \
    "inner ifdef would compile the probe out of core (8fd18e4)"

# 3. Throttled probe markers, first hits plus periodic totals.
assert snippet.count("EDEN_UNMAPPED_TRACE ") == 1, "first-hit marker"
assert snippet.count("EDEN_UNMAPPED_TOTAL") == 1, "totals marker"
assert "eden_unmapped_low_total" in snippet
assert "% 8192 == 0" in snippet

# 4. The pin names Eden's unmapped-read log; configure still fails on drift.
assert "Pinned unmapped-read log changed" in cmake[block_at:replace_at]

# 5. Against real Eden source when a checkout exists: the pinned commit
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
pin = "GetPointerImpl(addr, [addr]() {"
assert eden.count(pin) == 1, f"pin must match {eden_path} exactly once"
print(f"OK unmapped tracer ({eden_path})")
