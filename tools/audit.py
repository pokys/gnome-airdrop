#!/usr/bin/env python3
"""Check the exact tracked publication set; do not scan private runtime folders."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'], check=True,
                        capture_output=True)
files = [Path(name) for name in result.stdout.decode().split('\0') if name]
if not files:
    raise SystemExit('No tracked files. Stage the project first, then audit again.')
private = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|'
                     rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|' +
                     re.escape(str(Path.home()).encode()) + rb'(?:/|\b)|' +
                     re.escape((Path.home().name + '@').encode()) + rb'|192\.168\.254\.')
errors = []
for name in files:
    path = root/name
    if path.is_symlink():
        errors.append(f'{name}: symlink not permitted')
        continue
    if any(part in ('.build', 'dist', 'identity', 'received', '__pycache__') for part in name.parts):
        errors.append(f'{name}: runtime/build directory')
    if name.suffix.lower() in ('.key','.p12','.pfx','.log','.pcap','.pcapng','.pyc') or name.name in (
            'config.json', 'settings.json', 'receipt.json', '.env'):
        errors.append(f'{name}: private/generated file')
    data = subprocess.run(['git', '-C', str(root), 'show', ':' + name.as_posix()],
                          check=True, capture_output=True).stdout
    if data.startswith(b'\x7fELF') or data[:2] in (b'MZ', b'PK'):
        errors.append(f'{name}: compiled/archive artifact')
    if private.search(data):
        errors.append(f'{name}: possible local identity or secret; inspect privately')
    if name.suffix.lower() == '.pem' and name.as_posix() != 'app/lib/receiver/share/certs/apple_root_ca.pem':
        errors.append(f'{name}: unexpected certificate')
if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f'Publication audit passed for {len(files)} tracked source files. No runtime/build files, '
      'known local paths, private key blocks or token patterns found.')
print('Pattern checks cannot prove the absence of every possible secret; review the staged diff too.')
