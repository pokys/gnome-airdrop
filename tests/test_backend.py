import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
PACKAGE = TASK / 'app'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


control = module('control', PACKAGE / 'bin/control.py')
service = module('service', PACKAGE / 'bin/service.py')
protocol = module('protocol', TASK / 'tests/test_receiver_protocol.py')
protocol.SERVE = PACKAGE / 'lib/receiver/airdrop-serve.py'
limits = module('limits', TASK / 'tests/test_receiver_limits.py')
limits.SERVE = protocol.SERVE


class FramingDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.ns = limits.receiver_namespace()

    def test_missing_final_chunk_is_reported_as_early_close(self):
        with self.assertRaisesRegex(self.ns['RequestBodyError'], 'sender closed.*terminating chunk'):
            self.ns['read_request_body'](io.BytesIO(b'2\r\nab\r\n'),
                {'Transfer-Encoding': 'chunked'}, io.BytesIO(), 1024)

    def test_overlong_header_is_distinct_from_early_close(self):
        with self.assertRaisesRegex(self.ns['RequestBodyError'], 'header exceeds 128'):
            self.ns['read_request_body'](io.BytesIO(b'1;' + b'x' * 128 + b'\r\na\r\n0\r\n\r\n'),
                {'Transfer-Encoding': 'chunked'}, io.BytesIO(), 1024)

    def test_fragmented_reads_preserve_chunk_boundaries(self):
        class Fragmented(io.BytesIO):
            def read1(self, size=-1):
                return super().read1(min(size, 3))
        result = io.BytesIO()
        size = self.ns['read_request_body'](Fragmented(b'9\r\nabcdefghi\r\n0\r\n\r\n'),
            {'Transfer-Encoding': 'chunked'}, result, 1024)
        self.assertEqual((size, result.getvalue()), (9, b'abcdefghi'))


class CompleteArchiveTests(unittest.TestCase):
    def setUp(self):
        self.ns = limits.receiver_namespace()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def verify(self, raw, expected=None, total='7'):
        return self.ns['verify_complete_archive'](io.BytesIO(raw), self.tmp.name,
            20 * 1024 * 1024, expected or [{'FileName': 'proof.txt', 'FileSize': 7}], total)

    def test_complete_archive_matches_manifest(self):
        self.verify(protocol.dvzip([('proof.txt', b'content')]))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_truncated_compressed_archive_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(protocol.dvzip([('proof.txt', b'content')])[:-5])

    def test_wrong_declared_file_size_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'length differs'):
            self.verify(protocol.dvzip([('proof.txt', b'content')]),
                        [{'FileName': 'proof.txt', 'FileSize': 8}], total='8')

    def test_missing_manifest_file_is_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(protocol.dvzip([('proof.txt', b'content')]),
                [{'FileName': 'proof.txt', 'FileSize': 7}, {'FileName': 'absent', 'FileSize': 1}], '8')

    def test_mismatched_totalbytes_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'TotalBytes'):
            self.verify(protocol.dvzip([('proof.txt', b'content')]), total='9')

    def test_missing_cpio_trailer_is_rejected(self):
        import zlib
        archive = protocol.dvzip([('proof.txt', b'content')])
        cpio = zlib.decompress(archive[4:])
        trailer_name = cpio.index(b'TRAILER!!!\0')
        without_trailer = cpio[:trailer_name - 76]
        compressed = zlib.compress(without_trailer)
        with self.assertRaisesRegex(ValueError, 'terminating trailer'):
            self.verify(len(compressed).to_bytes(4, 'big') + compressed)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / 'config.json').write_text(json.dumps({'owner_uid': 1000,
            'download_dir': str(self.base / 'out'), 'user_data': str(self.base)}))

    def test_other_user_cannot_start_service(self):
        with patch.object(control, 'BASE', self.base), patch('sys.argv', ['control', 'start']), \
                patch('os.geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': '1001'}), \
                patch.object(control.subprocess, 'run') as commands:
            with self.assertRaises(SystemExit):
                control.main()
            commands.assert_not_called()

    def test_authorized_start_has_fixed_service_and_no_shell(self):
        with patch.object(control, 'BASE', self.base), patch('sys.argv', ['control', 'start']), \
                patch('os.geteuid', return_value=0), patch.dict(os.environ, {'PKEXEC_UID': '1000'}), \
                patch.object(control.subprocess, 'run') as commands:
            control.main()
            self.assertEqual(commands.call_args.args[0],
                ['/usr/bin/systemctl', '--no-block', 'start', 'gnome-airdrop.service'])

    def test_extra_arguments_are_rejected(self):
        with patch('sys.argv', ['control', 'start', 'anything']), \
                patch.object(control.subprocess, 'run') as commands:
            with self.assertRaises(SystemExit):
                control.main()
            commands.assert_not_called()

    def test_recovery_rejects_external_script(self):
        (self.base / 'current').write_text('/tmp/another-script')
        with patch.object(service, 'RUNTIME', self.base), \
                patch.object(service.subprocess, 'run') as commands:
            with self.assertRaises(RuntimeError):
                service.recover()
            commands.assert_not_called()

    def test_recovery_rejects_symlink_script(self):
        state = self.base / 'session.ABCDEF'
        state.mkdir()
        (self.base / 'current').write_text(str(state))
        (state / 'recover.sh').symlink_to('/bin/true')
        with patch.object(service, 'RUNTIME', self.base), \
                patch.object(service.subprocess, 'run') as commands:
            with self.assertRaises(RuntimeError):
                service.recover()
            commands.assert_not_called()


class ReceiptTests(protocol.ReceiverFixture):
    @classmethod
    def setUpClass(cls):
        cls.event_tmp = tempfile.TemporaryDirectory()
        cls.event = Path(cls.event_tmp.name) / 'receipt.json'
        with patch.dict(os.environ, {'GNOME_AIRDROP_EVENT_FILE': str(cls.event)}):
            super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.event_tmp.cleanup()

    def setUp(self):
        self.event.unlink(missing_ok=True)

    def ask(self, conn):
        return self.post(conn, '/Ask', plistlib.dumps({
            'SenderComputerName': 'Test', 'TransferType': {'files': 1},
            'Files': [{'FileName': 'receipt.txt', 'FileSize': 7}],
        }, fmt=plistlib.FMT_BINARY))

    def test_complete_upload_has_receipt_and_exact_content(self):
        conn = self.connection()
        self.assertEqual(self.ask(conn)[0], 200)
        result = self.post(conn, '/Upload', protocol.dvzip([('receipt.txt', b'content')]),
            {'Content-Type': 'application/x-dvzip', 'TransferID': 'complete'})
        self.assertEqual(result[0], 200)
        self.assertEqual((self.out / 'receipt.txt').read_bytes(), b'content')
        self.assertEqual(json.loads(self.event.read_text())['files'], ['receipt.txt'])
        self.assertEqual(json.loads(self.event.read_text())['id'], 'complete')

    def test_invalid_upload_does_not_publish_receipt(self):
        conn = self.connection()
        self.assertEqual(self.ask(conn)[0], 200)
        result = self.post(conn, '/Upload', b'not-a-valid-archive',
            {'Content-Type': 'application/x-dvzip', 'TransferID': 'invalid'})
        self.assertGreaterEqual(result[0], 400)
        self.assertFalse(self.event.exists())

    def test_six_megabyte_upload_completes_with_exact_bytes(self):
        data = os.urandom(6 * 1024 * 1024)
        conn = self.connection()
        self.assertEqual(self.ask(conn)[0], 200)
        result = self.post(conn, '/Upload', protocol.dvzip([('large.bin', data)]),
            {'Content-Type': 'application/x-dvzip', 'TransferID': 'large'})
        self.assertEqual(result[0], 200)
        self.assertEqual((self.out / 'large.bin').read_bytes(), data)
        self.assertEqual(json.loads(self.event.read_text())['files'], ['large.bin'])



class MissingEndingTests(protocol.ReceiverFixture):
    @classmethod
    def setUpClass(cls):
        import shutil
        cls.copy_tmp = tempfile.TemporaryDirectory()
        clone = Path(cls.copy_tmp.name)
        shutil.copytree(PACKAGE / 'lib/receiver', clone / 'plugin/bin')
        shutil.copytree(PACKAGE / 'lib/receiver/share', clone / 'plugin/share')
        source = clone / 'plugin/bin/airdrop-serve.py'
        source.write_text(source.read_text().replace('READ_IDLE_TIMEOUT_SECONDS = 30',
                                                     'READ_IDLE_TIMEOUT_SECONDS = 1'))
        old = protocol.SERVE
        protocol.SERVE = source
        try:
            super().setUpClass()
        finally:
            protocol.SERVE = old

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.copy_tmp.cleanup()

    def upload_missing_ending(self, name, wire, size):
        conn = self.connection()
        status, _ = self.post(conn, '/Ask', plistlib.dumps({
            'SenderComputerName': 'Test', 'TransferType': {'files': 1},
            'Files': [{'FileName': name, 'FileSize': size}],
        }, fmt=plistlib.FMT_BINARY))
        self.assertEqual(status, 200)
        conn.putrequest('POST', '/Upload')
        conn.putheader('Transfer-Encoding', 'chunked')
        conn.putheader('Content-Type', 'application/x-dvzip')
        conn.putheader('TotalBytes', str(size))
        conn.putheader('TransferID', name)
        conn.endheaders()
        # Keep the TLS connection open but omit HTTP's 0\r\n\r\n terminator.
        conn.send(f'{len(wire):X}\r\n'.encode() + wire + b'\r\n')
        response = conn.getresponse()
        result = response.status, response.getheader('Connection'), response.read()
        return result

    def test_complete_six_megabyte_archive_survives_missing_http_ending(self):
        data = os.urandom(6 * 1024 * 1024)
        result = self.upload_missing_ending('complete.bin', protocol.dvzip([('complete.bin', data)]), len(data))
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1], 'close')
        self.assertEqual((self.out / 'complete.bin').read_bytes(), data)

    def test_truncated_archive_still_fails_without_leaving_a_file(self):
        wire = protocol.dvzip([('incomplete.bin', b'content')])[:-5]
        result = self.upload_missing_ending('incomplete.bin', wire, 7)
        self.assertEqual(result[0], 408)
        self.assertFalse((self.out / 'incomplete.bin').exists())

    def test_wrong_ask_size_still_fails(self):
        wire = protocol.dvzip([('mismatch.bin', b'content')])
        result = self.upload_missing_ending('mismatch.bin', wire, 8)
        self.assertEqual(result[0], 408)
        self.assertFalse((self.out / 'mismatch.bin').exists())


if __name__ == '__main__':
    suite = unittest.TestSuite()
    for case in (AuthorizationTests, FramingDiagnosisTests, CompleteArchiveTests, protocol.ExistingIdentityTests,
                 protocol.FirstStartTests, protocol.ContactsOnlyTests,
                 protocol.StalledHandshakeTests, ReceiptTests, MissingEndingTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
