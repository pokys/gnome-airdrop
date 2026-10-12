#!/usr/bin/env python3
"""Assemble only explicit program sources and the locally built OWL executable."""
from pathlib import Path
import shutil
import json
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / 'dist/gnome-airdrop'
if output.exists():
    shutil.rmtree(output)
shutil.copytree(root / 'app', output / 'backend', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copytree(root / 'vendor/python', output / 'backend/lib/python',
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(root / '.build/owl/daemon/owl', output / 'backend/lib/radio/owl')
shutil.copytree(root / 'licenses', output / 'backend/licenses')
shutil.copy2(root / 'LICENSE', output / 'backend/licenses/PROJECT-LICENSE')
shutil.copytree(root / 'packaging/system', output / 'system')
for name in ('install.sh', 'uninstall.sh'):
    shutil.copy2(root / 'packaging' / name, output / name)
shutil.copy2(root / 'README.md', output / 'README.md')
shutil.copy2(root / 'CHANGELOG.md', output / 'CHANGELOG.md')
with zipfile.ZipFile(output / 'gnome-airdrop@pokys.github.io.shell-extension.zip', 'w',
                     compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / 'extension').glob('*')):
        if path.is_file():
            if path.name == 'metadata.json':
                metadata = json.loads(path.read_text())
                metadata['version-name'] = (root/'app/VERSION').read_text().strip()
                archive.writestr(path.name, json.dumps(metadata, indent=2)+'\n')
            else:
                archive.write(path, path.name)
    archive.write(root / 'LICENSE', 'LICENSE')
(output / 'backend/outputs').mkdir(mode=0o755)
shutil.make_archive(str(root / 'dist/gnome-airdrop'), 'gztar', root / 'dist', 'gnome-airdrop')
print('Built dist/gnome-airdrop.tar.gz and dist/gnome-airdrop/')
