#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/app/bin:$ROOT/vendor/python"
python3 "$ROOT/tests/test_backend.py"
python3 "$ROOT/tests/test_settings.py"
if [[ -d $ROOT/dist/gnome-airdrop ]]; then
  python3 "$ROOT/tests/test_installation.py"
fi
gjs "$ROOT/tests/check_frontend.js"
python3 - "$ROOT" <<'PY'
from pathlib import Path
import ast, json, sys, xml.etree.ElementTree as ET
root = Path(sys.argv[1])
for directory in ('app', 'tests', 'tools'):
    for source in (root/directory).rglob('*.py'):
        ast.parse(source.read_text(), filename=str(source))
metadata = json.loads((root/'extension/metadata.json').read_text())
assert metadata['uuid'] == 'gnome-airdrop@pokys.github.io'
ET.parse(root/'packaging/system/io.github.pokys.gnome-airdrop.policy')
print('Python, extension metadata and polkit syntax OK')
PY
for script in "$ROOT"/tools/*.sh "$ROOT"/packaging/*.sh "$ROOT"/app/bin/listen.sh; do bash -n "$script"; done
bash -n "$ROOT/app/lib/radio/omdrop-discoverable"
