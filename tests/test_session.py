"""Timers and receiver activity tested without systemd, radio or real login sessions."""
import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
import session
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app/lib/receiver'))
from transfer_state import TransferState


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'runtime').mkdir()
        self.path = self.root/'session.json'
        self.prefs = {'duration_seconds':300, 'receiver_name':'Receiver', 'download_dir':'/tmp'}
        session.prepare(self.prefs, self.path)
        with patch('time.monotonic', return_value=100), patch('time.time', return_value=1000):
            session.ready(self.path)
        self.state = TransferState(self.root/'runtime/transfer.json', self.path)
        if self.state.activity_fd is not None:
            self.addCleanup(os.close, self.state.activity_fd)

    def test_timer_starts_only_after_ready(self):
        session.prepare(self.prefs, self.path)
        self.assertFalse(session.expired(self.root, self.path, now=999999))
        with patch('time.monotonic', return_value=200), patch('time.time', return_value=5000):
            session.ready(self.path)
        snapshot = session.read_json(self.path)
        self.assertEqual(snapshot['ends_monotonic'], 500)
        self.assertEqual(snapshot['ends_at'], 5300)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)

    def test_last_result_survives_a_new_receiving_session(self):
        with patch('time.monotonic', return_value=399): token = self.state.begin('file',1)
        self.state.finish(token,'timeout')
        restarted=TransferState(self.root/'runtime/transfer.json',self.path)
        self.addCleanup(os.close,restarted.activity_fd)
        restarted.idle()
        result=session.read_json(self.root/'runtime/transfer.json')
        self.assertEqual(result['phase'],'error')
        self.assertEqual(result['last_result']['id'],token)
        self.assertEqual(result['error'],'timeout')
        self.assertEqual(result['active_transfers'],0)

    def test_indefinite_session_never_expires(self):
        session.prepare(dict(self.prefs, duration_seconds=0), self.path)
        session.ready(self.path)
        self.assertFalse(session.expired(self.root, self.path, now=10**12))

    def test_expiry_waits_for_transfer_then_stops(self):
        with patch('time.monotonic', return_value=399):
            token = self.state.begin('photo.jpg', 1)
        self.assertIsNotNone(token)
        self.assertFalse(session.expired(self.root, self.path, now=400))
        self.state.update(token, 'verifying', wire_bytes=1024)
        self.assertFalse(session.expired(self.root, self.path, now=500))
        with patch('time.monotonic', return_value=401):
            self.assertIsNone(self.state.begin('late.jpg', 1))
        self.state.finish(token)
        self.assertTrue(session.expired(self.root, self.path, now=500))
        snapshot = session.read_json(self.root/'runtime/transfer.json')
        self.assertEqual(snapshot['last_result']['phase'], 'completed')
        self.assertEqual(snapshot['active_transfers'], 0)

    def test_expiry_waits_for_both_existing_transfers(self):
        with patch('time.monotonic', return_value=399):
            a = self.state.begin('first',1); b = self.state.begin('second',1)
        self.state.finish(a)
        self.assertFalse(session.expired(self.root,self.path,now=500))
        self.state.finish(b,'timeout')
        self.assertTrue(session.expired(self.root,self.path,now=500))

    def test_sender_timeout_and_disconnect_release_activity(self):
        for error in ('timeout','interrupted'):
            with patch('time.monotonic',return_value=399): token = self.state.begin('file',1)
            self.state.finish(token,error)
            self.assertTrue(session.expired(self.root,self.path,now=500))

    def test_timer_does_not_depend_on_editable_ui_status(self):
        with patch('time.monotonic',return_value=399): token = self.state.begin('file',1)
        (self.root/'runtime/transfer.json').write_text('{"active_transfers":0}')
        self.assertFalse(session.expired(self.root,self.path,now=500))
        self.state.finish(token)
        (self.root/'runtime/transfer.json').write_text('{"active_transfers":999}')
        self.assertTrue(session.expired(self.root,self.path,now=500))

    def test_missing_session_rejects_new_transfers(self):
        self.path.unlink()
        self.assertIsNone(self.state.begin())
        with self.assertRaises(RuntimeError): session.expired(self.root,self.path)

    def test_symlink_and_fifo_runtime_reads_are_rejected(self):
        file=self.root/'link';file.symlink_to(self.path)
        self.assertIsNone(session.read_json(file))
        pipe=self.root/'fifo';os.mkfifo(pipe)
        self.assertIsNone(session.read_json(pipe))
        large=self.root/'large';large.write_text('{"value":"'+'a'*65536+'"}')
        self.assertIsNone(session.read_json(large))


if __name__=='__main__': unittest.main(verbosity=2)
