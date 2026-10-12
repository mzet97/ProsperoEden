#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The dev package carries its git identity and the boot trace prints it.

make-dev-dist.py writes build-id.txt (sha + clean/dirty, no timestamp so
equal trees still zip equal bytes); main.cpp reads it once the app folder
is known and logs "build id: ...". __DATE__/__TIME__ go stale on
incremental rebuilds, so this file is what names the running build.

Source-tree only, plain python3:
    python3 -B tools/check-build-id.py [make-dev-dist.py] [main.cpp]
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
packager = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "tools/ci/make-dev-dist.py"
main = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "headless/main.cpp"
packager_text = packager.read_text()
main_text = main.read_text()

# 1. Producer/consumer contract: the same file name on both sides.
assert "build-id.txt" in packager_text, "packager writes build-id.txt"
assert 'Eden::AppFile("build-id.txt")' in main_text, "main.cpp reads build-id.txt"

# 2. Identity without a timestamp (deterministic zips) and a fallback
# outside a checkout.
assert "rev-parse" in packager_text and "dirty" in packager_text
assert "return 'unknown\\n'" in packager_text

# 3. The trace line, guarded against absurd input.
assert '"build id: %s"' in main_text
assert "id_line.size() < 100" in main_text

print("OK build-id wiring")
