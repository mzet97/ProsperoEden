#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""The release ZIP must not ship dev-only probes.

Dev and release builds share one scratch dir locally, and a dev-configure's
derived header can linger into a release eboot (found pre-v1.000.120 with
EDEN_GMMU_GAP: the CMake else() removes it, this looks once more):

    python3 -B tools/check-release-clean.py

Needs dist/ProsperoEden-v*.zip (make release); without one it reports
SKIP (honest, not green).
"""
import glob
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
zips = sorted(glob.glob(str(root / "dist/ProsperoEden-v*.zip")))
if not zips:
    print("SKIP release-clean: no dist/ProsperoEden-v*.zip (structural checks passed)")
    sys.exit(0)
for archive in zips:
    with zipfile.ZipFile(archive) as z:
        eboot = z.read("PPSA99008/eboot.bin")
    for marker in ("EDEN_MAP_NULL", "EDEN_GMMU_GAP", "EDEN_UNMAPPED_TRACE",
                   "EDEN_JIT_GROUPS"):
        assert marker.encode() not in eboot, f"dev probe leaked into release: {marker}"
    assert b"MapPages: stored host pointer reads back null" in eboot, "H3 log fix missing"
    print(f"OK release clean ({Path(archive).name}: no dev probes, H3 fix present)")
