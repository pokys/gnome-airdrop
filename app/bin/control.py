#!/usr/bin/python3
"""Polkit entry point. Only the configured owner can start/stop this service."""
import json
import os
from pathlib import Path
import subprocess
import sys
from settings import download_directory, save_download_directory

BASE = Path(__file__).resolve().parents[1]
UNIT = 'gnome-airdrop.service'


def status(config):
    result = subprocess.run(['/usr/bin/systemctl', 'show', UNIT,
                             '--property=ActiveState', '--property=LoadState'],
                            capture_output=True, text=True, timeout=5)
    properties = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    state = properties.get('ActiveState', 'inactive')
    receipt = None
    try:
        receipt = json.loads((Path(config['user_data']) / 'runtime/receipt.json').read_text())
    except (OSError, ValueError):
        pass
    print(json.dumps({'installed': properties.get('LoadState') == 'loaded',
                      'state': state, 'receiving': state == 'active',
                      'download_dir': download_directory(config), 'receipt': receipt}, ensure_ascii=False))


def main():
    args = sys.argv[1:]
    if not (args in (['start'], ['stop'], ['status']) or
            len(args) == 2 and args[0] == 'set-download-dir'):
        raise SystemExit('Usage: control.py start|stop|status|set-download-dir PATH')
    config = json.loads((BASE / 'config.json').read_text())
    if args[0] == 'set-download-dir':
        if os.geteuid() != config['owner_uid']:
            raise SystemExit('Run settings as the installation owner, without sudo')
        result = subprocess.run(['/usr/bin/systemctl', 'show', UNIT, '--property=ActiveState',
                                 '--value'], capture_output=True, text=True, check=True, timeout=5)
        if result.stdout.strip() not in ('inactive', 'failed'):
            raise SystemExit('Nejprve vypněte příjem AirDrop.')
        save_download_directory(config, args[1])
        return
    if sys.argv[1] == 'status':
        status(config)
        return
    if os.geteuid() != 0:
        raise SystemExit('Authentication is required')
    caller = os.environ.get('PKEXEC_UID', '')
    if not caller.isdecimal() or int(caller) != config['owner_uid']:
        raise SystemExit('Only the installation owner can control AirDrop')
    subprocess.run(['/usr/bin/systemctl', '--no-block', sys.argv[1], UNIT], check=True, timeout=10)


if __name__ == '__main__':
    main()
