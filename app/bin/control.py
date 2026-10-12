#!/usr/bin/python3
"""Polkit entry point. Only the configured owner can start/stop this service."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from settings import preferences, save_download_directory, save_preferences
import session

BASE = Path(__file__).resolve().parents[1]
UNIT = 'gnome-airdrop.service'


def get_status(config):
    result = subprocess.run(['/usr/bin/systemctl', 'show', UNIT,
                             '--property=ActiveState', '--property=LoadState'],
                            capture_output=True, text=True, timeout=5)
    properties = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    state = properties.get('ActiveState', 'inactive')
    receipt = session.read_json(Path(config['user_data']) / 'runtime/receipt.json', limit=1024*1024)
    transfer = session.read_json(Path(config['user_data']) / 'runtime/transfer.json')
    if transfer:
        try:
            if time.time() - transfer.get('updated_at', 0) > 4:
                transfer['bytes_per_second'] = 0
        except TypeError:
            transfer = None
    prefs = preferences(config)
    active_session = session.read_json(session.SESSION) if state in ('active', 'activating', 'deactivating') else None
    return {'installed': properties.get('LoadState') == 'loaded',
                      'state': state, 'receiving': state == 'active',
                      'download_dir': (active_session or prefs)['download_dir'], 'receipt': receipt,
                      'transfer': transfer, 'preferences': prefs, 'session': active_session}


def main():
    args = sys.argv[1:]
    if not (args in (['start'], ['stop'], ['status'], ['diagnostics']) or
            len(args) == 2 and args[0] in ('set-download-dir', 'set-preferences')):
        raise SystemExit('Usage: control.py start|stop|status|diagnostics|set-download-dir PATH|set-preferences JSON')
    config = json.loads((BASE / 'config.json').read_text())
    if args[0] in ('set-download-dir', 'set-preferences'):
        if os.geteuid() != config['owner_uid']:
            raise SystemExit('Run settings as the installation owner, without sudo')
        result = subprocess.run(['/usr/bin/systemctl', 'show', UNIT, '--property=ActiveState',
                                 '--value'], capture_output=True, text=True, check=True, timeout=5)
        if args[0] == 'set-download-dir' and result.stdout.strip() not in ('inactive', 'failed'):
            raise SystemExit('Nejprve vypněte příjem AirDrop.')
        if args[0] == 'set-download-dir':
            save_download_directory(config, args[1])
        else:
            save_preferences(config, json.loads(args[1]))
        return
    if sys.argv[1] == 'status':
        print(json.dumps(get_status(config), ensure_ascii=False))
        return
    if args[0] == 'diagnostics':
        from diagnostics import report
        print(json.dumps(report(get_status(config)), indent=2))
        return
    if os.geteuid() != 0:
        raise SystemExit('Authentication is required')
    caller = os.environ.get('PKEXEC_UID', '')
    if not caller.isdecimal() or int(caller) != config['owner_uid']:
        raise SystemExit('Only the installation owner can control AirDrop')
    subprocess.run(['/usr/bin/systemctl', '--no-block', sys.argv[1], UNIT], check=True, timeout=10)


if __name__ == '__main__':
    main()
