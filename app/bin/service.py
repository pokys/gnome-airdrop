#!/usr/bin/python3
"""Start the fixed, root-owned backend; recover even after SIGKILL."""
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
RUNTIME = Path('/run/gnome-airdrop')


def configuration():
    config = json.loads((BASE / 'config.json').read_text())
    user = pwd.getpwuid(config['owner_uid'])
    if user.pw_uid == 0 or user.pw_name != config['owner_name']:
        raise RuntimeError('Invalid installation owner')
    return config, user


def recover():
    pointer = RUNTIME / 'current'
    if not pointer.exists():
        return 0
    state = Path(pointer.read_text().strip())
    if state.parent != RUNTIME or not re.fullmatch(r'session\.[A-Za-z0-9]+', state.name):
        raise RuntimeError('Invalid recovery state path')
    if not state.exists():
        return 0
    script = state / 'recover.sh'
    if script.is_symlink() or not script.is_file() or script.stat().st_uid != 0:
        raise RuntimeError('Invalid recovery script')
    if script.stat().st_mode & 0o022:
        raise RuntimeError('Recovery script must be root-owned and not writable by others')
    config, _ = configuration()
    result = subprocess.run(['/bin/bash', str(script), str(state),
                             str(BASE / 'lib/radio/omdrop-discoverable'),
                             config['interface']], timeout=90)
    if result.returncode:
        return result.returncode
    guard_file = state / 'guard'
    if guard_file.exists():
        guard = guard_file.read_text().strip()
        if re.fullmatch(r'gnome-airdrop-guard-\d+', guard):
            subprocess.run(['systemctl', 'stop', guard + '.timer', guard + '.service'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    return 0


def main():
    if os.geteuid() != 0 or sys.argv[1:] not in (['run'], ['recover'], ['ready'], ['expired']):
        raise SystemExit('Run through gnome-airdrop.service')
    if sys.argv[1] == 'recover':
        raise SystemExit(recover())
    config, user = configuration()
    import session
    from settings import preferences
    if sys.argv[1] == 'ready':
        session.ready()
        return
    if sys.argv[1] == 'expired':
        try:
            should_stop = session.expired(config['user_data'])
        except (RuntimeError, TypeError, ValueError):
            raise SystemExit(2)
        raise SystemExit(0 if should_stop else 1)
    prefs = preferences(config)
    config['download_dir'] = prefs['download_dir']
    data = Path(config['user_data'])
    subprocess.run(['/usr/sbin/runuser', '-u', user.pw_name, '--', '/usr/bin/mkdir', '-p',
                    config['download_dir'], str(data / 'config'), str(data / 'runtime'),
                    str(data / 'identity')], check=True)
    session.prepare(prefs)
    env = dict(os.environ, SUDO_USER=user.pw_name, SUDO_UID=str(user.pw_uid),
               AIR_DROP_RECEIVED_DIR=config['download_dir'], AIR_DROP_USER_DATA=str(data),
               AIR_DROP_INTERFACE=config['interface'], AIR_DROP_RECEIVER_NAME=prefs['receiver_name'],
               PYTHONDONTWRITEBYTECODE='1',
               PATH='/usr/sbin:/usr/bin:/sbin:/bin')
    os.execve('/bin/bash', ['/bin/bash', str(BASE / 'bin/listen.sh'), '--listen'], env)


if __name__ == '__main__':
    main()
