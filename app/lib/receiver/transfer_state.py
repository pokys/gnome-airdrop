"""Latest transfer for the UI; no queue, persistent history or raw sender data."""
import json
import fcntl
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid


class TransferState:
    def __init__(self, path=None, session_path=None):
        self.path = Path(path) if path else None
        self.session_path = Path(session_path) if session_path else None
        self.lock = threading.Lock()
        self.active = {}
        self.latest = {'phase': 'idle', 'active_transfers': 0}
        self.last_result = None
        self.destination = None
        self.activity_fd = None
        if self.path:
            try:
                self.activity_fd = os.open(self.path.with_name('transfer.lock'),
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            except OSError:
                pass

    def accepting(self):
        if self.session_path is None:
            return True
        try:
            with self.session_path.open() as stream:
                session = json.loads(stream.read(8192))
            end = session.get('ends_monotonic')
            return end is None or time.monotonic() < end
        except (OSError, ValueError, TypeError):
            # A configured service session must be readable; do not accept new
            # files when its deadline cannot be established.
            return False

    def _save(self, value):
        self.latest = dict(value, active_transfers=len(self.active), updated_at=time.time(), last_result=self.last_result)
        if self.path is None:
            return
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix='.transfer-', dir=self.path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.latest, stream, ensure_ascii=False)
            os.replace(temporary, self.path)
        except OSError:
            # A UI-state write must never fail an otherwise valid transfer.
            pass
        finally:
            try:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
            except OSError:
                pass

    def begin(self, filename='', file_count=0):
        with self.lock:
            if not self.active and self.activity_fd is not None:
                fcntl.flock(self.activity_fd, fcntl.LOCK_SH)
            if not self.accepting() or (self.session_path and self.activity_fd is None):
                if not self.active and self.activity_fd is not None:
                    fcntl.flock(self.activity_fd, fcntl.LOCK_UN)
                return None
            token = uuid.uuid4().hex
            value = {'id': token, 'phase': 'waiting', 'filename': filename[:200],
                     'file_count': file_count, 'wire_bytes': 0, 'total_wire_bytes': None,
                     'bytes_per_second': 0, 'error': None}
            self.active[token] = value
            self._save(value)
            return token

    def update(self, token, phase, wire_bytes=None, elapsed=None, total_wire_bytes=None):
        with self.lock:
            value = self.active.get(token)
            if value is None:
                return
            value['phase'] = phase
            if wire_bytes is not None:
                value['wire_bytes'] = wire_bytes
            if elapsed is not None:
                value['bytes_per_second'] = value['wire_bytes'] / max(elapsed, 0.001)
            if total_wire_bytes is not None:
                value['total_wire_bytes'] = total_wire_bytes
            self._save(value)

    def finish(self, token, error=None, filename=None, file_count=None):
        with self.lock:
            value = self.active.pop(token, None)
            if value is None:
                return
            value.update(phase='error' if error else 'completed', error=error,
                         bytes_per_second=0)
            if filename is not None:
                value['filename'] = filename[:200]
            if file_count is not None:
                value['file_count'] = file_count
            if self.destination:
                value['download_dir'] = self.destination
            self.last_result = dict(value)
            # Keep showing any ongoing transfer rather than a finished sibling.
            self._save(next(reversed(self.active.values())) if self.active else value)
            if not self.active and self.activity_fd is not None:
                fcntl.flock(self.activity_fd, fcntl.LOCK_UN)

    def idle(self):
        with self.lock:
            self._save({'phase': 'idle'})
