#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local dev packages must stay playable (controller, not timed replay).

A dev build boots EDEN_DEV_PROFILE_TITLE with EDEN_DEV_ROM_ID set to the same
title, so main.cpp runs the timed input replay - and never polls the pad -
unless dev-settings.txt contains replay=off. CI -noreplay bakes that file;
local packages must too, or the controller silently dies:

    python3 -B tools/check-dev-playable.py
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
script = (root / "tools/build-package.sh").read_text()

# Baked after packaging (post-freeze, like CI), dev mode only, honoring
# REPLAY (dev-ps5.yml: on = deterministic benchmarks, no file).
assert '[[ $mode == dev ]]' in script, "dev-only gate"
assert '[[ ${REPLAY:-off} == off ]]' in script, "honor REPLAY"
assert 'printf \'replay=off\\n\' > "$EDEN_PACKAGE_DIR/dev-settings.txt"' in script, \
    "bake replay=off when playable"
assert 'rm -f "$EDEN_PACKAGE_DIR/dev-settings.txt"' in script, "no stale file when on"
print("OK dev package playable (replay=off baked, REPLAY honored)")
