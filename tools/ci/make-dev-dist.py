#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test files from a development PPSA99008 folder (make dev).

  tools/ci/make-dev-dist.py APP_DIR NAME

dist-dev/ProsperoEden-dev-NAME.zip (the folder; fixed timestamps, so equal inputs
give equal bytes) and SHA256SUMS (of the ZIP). Every entry is stored as 0777, like
make-dist.py: the console only starts an app whose files are open to all.
"""
import hashlib
import pathlib
import shutil
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parents[2]
args = sys.argv[1:]
if len(args) != 2:
    sys.exit(__doc__.strip())
app = pathlib.Path(args[0]).resolve()
name = args[1]
if not (app / 'eboot.bin').is_file():
    sys.exit(f'{app} is not a built PPSA99008 folder')
dist = root / 'dist-dev'
shutil.rmtree(dist, ignore_errors=True)
dist.mkdir()
archive = dist / f'ProsperoEden-dev-{name}.zip'
files = [('PPSA99008/' + p.relative_to(app).as_posix(), p) for p in sorted(app.rglob('*')) if p.is_file()]
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
    for entry, path in files:
        info = zipfile.ZipInfo(entry, (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3  # Unix: the high half of external_attr is the mode
        info.external_attr = 0o100777 << 16
        zip_file.writestr(info, path.read_bytes())
with zipfile.ZipFile(archive) as check:
    closed = [i.filename for i in check.infolist() if (i.external_attr >> 16) & 0o777 != 0o777]
    if closed:
        sys.exit(f'ZIP entries not stored as 0777: {closed[:3]}')
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(dist / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n')
# The unstripped executable of this build, to name the functions in a crash report
# later (tools/symbolize-crash.py). Kept out of dist-dev/: it is not a test file.
unstripped = root / 'build/headless-native/llvm-pie.elf'
if unstripped.exists():
    symbols = root / 'build/symbols' / f'ProsperoEden-dev-{name}.elf'
    symbols.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(unstripped, symbols)
    print(f'{symbols} (keep it with the test build: crash reports are read with it)')
print(f'{archive} {digest}')
