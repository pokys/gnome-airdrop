#!/usr/bin/env python3
"""Export only the two intended downloads and their checksums."""
import hashlib
import os
from pathlib import Path
import re
import shutil

root = Path(__file__).resolve().parents[1]
ref = os.environ.get('BUILD_REF', '')
if ref.startswith('refs/tags/'):
    version = ref.removeprefix('refs/tags/')
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?', version):
        raise SystemExit('Release tags must look like v0.1.0 or v0.1.0-beta.1')
else:
    revision = os.environ.get('BUILD_SHA', '')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise SystemExit('BUILD_SHA must be a full Git commit SHA')
    version = 'dev-' + revision[:12]

output = root / 'dist/release'
if output.exists():
    shutil.rmtree(output)
output.mkdir()
assets = {
    root / 'dist/gnome-airdrop/gnome-airdrop@pokys.github.io.shell-extension.zip':
        f'gnome-airdrop-extension-{version}.zip',
    root / 'dist/gnome-airdrop.tar.gz':
        f'gnome-airdrop-{version}-fedora44-x86_64.tar.gz',
}
checksums = []
for source, name in assets.items():
    shutil.copy2(source, output / name)
    checksums.append(f'{hashlib.sha256(source.read_bytes()).hexdigest()}  {name}\n')
(output / 'SHA256SUMS').write_text(''.join(checksums))
(output / 'RELEASE-NOTES.md').write_text(f'''Experimental GNOME AirDrop {version}

- Tested target: Fedora 44, GNOME 50, Intel AX211, x86_64.
- The tar.gz is the complete installer bundle, including receiver, extension
  and uninstaller. Extract it and run `./gnome-airdrop/install.sh`.
- The extension ZIP contains only the GNOME UI; it requires the matching backend.
- Receiving temporarily disconnects normal Wi-Fi. Transfers can be slow or
  require retrying. Hardware behavior is not verified by CI.
- SHA256SUMS verifies downloaded file contents; it is not a digital signature.

See the bundled README for runtime dependencies, removal and limitations.
''')
print('Release assets: ' + ', '.join(path.name for path in output.iterdir()))
