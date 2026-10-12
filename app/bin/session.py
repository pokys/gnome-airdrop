"""Fixed root-owned session snapshot and a file lock for graceful expiry."""
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
import time

SESSION = Path('/run/gnome-airdrop/session.json')


def read_json(path, limit=65536):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return None
            text = stream.read(limit + 1)
            if len(text) > limit:
                return None
            value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def write_session(value, path=SESSION):
    fd, temporary = tempfile.mkstemp(prefix='.session-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare(prefs, path=SESSION):
    write_session(dict(prefs, started_at=None, ends_at=None, ends_monotonic=None), path)


def ready(path=SESSION):
    value = read_json(path)
    if value is None:
        raise RuntimeError('Session settings unavailable')
    now = time.time()
    duration = value['duration_seconds']
    value.update(started_at=now, ends_at=now + duration if duration else None,
                 ends_monotonic=time.monotonic() + duration if duration else None)
    write_session(value, path)


def expired(data, path=SESSION, now=None):
    value = read_json(path)
    if value is None:
        raise RuntimeError('Session settings unavailable')
    end = value.get('ends_monotonic')
    if end is None or (time.monotonic() if now is None else now) < end:
        return False
    try:
        fd = os.open(Path(data) / 'runtime/transfer.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return True
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return True
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True
    finally:
        os.close(fd)
