import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import settings
import control
import os
import subprocess


class DestinationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / 'chosen folder'
        self.folder.mkdir()
        self.config = {'user_data': str(self.root / 'data'), 'download_dir': '/tmp/default',
                       'owner_uid': os.getuid()}

    def test_default_then_atomic_user_preference(self):
        self.assertEqual(settings.download_directory(self.config), '/tmp/default')
        settings.save_download_directory(self.config, str(self.folder))
        self.assertEqual(settings.download_directory(self.config), str(self.folder))
        self.assertEqual((self.root/'data/settings.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list((self.root/'data').iterdir())), 1)

    def test_relative_and_missing_destinations_are_rejected(self):
        for value in ['relative', str(self.root/'missing')]:
            with self.assertRaises(ValueError):
                settings.save_download_directory(self.config, value)
        self.assertFalse((self.root/'data').exists())

    def test_invalid_preferences_use_default(self):
        (self.root/'data').mkdir()
        for content in ['invalid json', '{"download_dir":"relative"}', 'null']:
            (self.root/'data/settings.json').write_text(content)
            self.assertEqual(settings.download_directory(self.config), '/tmp/default')

    def test_change_during_transfer_is_rejected(self):
        (self.root/'config.json').write_text(json.dumps(self.config))
        with patch.object(control, 'BASE', self.root), \
                patch('sys.argv', ['control', 'set-download-dir', str(self.folder)]), \
                patch.object(control.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'active\n')):
            with self.assertRaises(SystemExit): control.main()
        self.assertFalse((self.root/'data').exists())

    def test_inactive_user_can_change_without_root(self):
        (self.root/'config.json').write_text(json.dumps(self.config))
        with patch.object(control, 'BASE', self.root), \
                patch('sys.argv', ['control', 'set-download-dir', str(self.folder)]), \
                patch.object(control.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'inactive\n')):
            control.main()
        self.assertEqual(settings.download_directory(self.config), str(self.folder))

    def test_other_user_cannot_set_destination(self):
        (self.root/'config.json').write_text(json.dumps(self.config))
        with patch.object(control, 'BASE', self.root), \
                patch('os.geteuid', return_value=os.getuid()+1), \
                patch('sys.argv', ['control', 'set-download-dir', str(self.folder)]), \
                patch.object(control.subprocess, 'run') as commands:
            with self.assertRaises(SystemExit): control.main()
        commands.assert_not_called()


class PreferencesTests(unittest.TestCase):
    setUp = DestinationTests.setUp

    def test_short_reception_windows_are_saved(self):
        settings.save_preferences(self.config, {'download_dir': str(self.folder)})
        for seconds in (60, 120):
            settings.save_preferences(self.config, {'duration_seconds': seconds})
            self.assertEqual(settings.preferences(self.config)['duration_seconds'], seconds)

    def test_all_preferences_share_one_file_and_preserve_each_other(self):
        settings.save_preferences(self.config, {'download_dir': str(self.folder),
            'receiver_name': 'My Laptop', 'duration_seconds': 600})
        settings.save_preferences(self.config, {'duration_seconds': 300})
        prefs = settings.preferences(self.config)
        self.assertEqual(prefs, {'download_dir': str(self.folder), 'receiver_name': 'My Laptop',
                               'duration_seconds': 300})
        self.assertEqual(list((self.root/'data').iterdir()), [self.root/'data/settings.json'])

    def test_invalid_values_do_not_replace_saved_preferences(self):
        settings.save_preferences(self.config, {'download_dir':str(self.folder)})
        before = (self.root/'data/settings.json').read_bytes()
        for changes in [{'receiver_name':''}, {'receiver_name':'a'*64},
                        {'receiver_name':'bad\nname'}, {'receiver_name':'bad/dir'},
                        {'receiver_name':'a\u202eb'}, {'duration_seconds':True},
                        {'duration_seconds':301}, {'unknown':'value'}]:
            with self.assertRaises(ValueError): settings.save_preferences(self.config, changes)
            self.assertEqual(before,(self.root/'data/settings.json').read_bytes())

    def test_preferences_can_change_during_receiving_without_restarting_service(self):
        settings.save_preferences(self.config, {'download_dir':str(self.folder)})
        (self.root/'config.json').write_text(json.dumps(self.config))
        with patch.object(control,'BASE',self.root), \
                patch('sys.argv',['control','set-preferences','{"receiver_name":"New Name","duration_seconds":600}']), \
                patch.object(control.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'active\n')) as commands:
            control.main()
        self.assertEqual(settings.preferences(self.config)['receiver_name'],'New Name')
        self.assertEqual(commands.call_count,1)
        self.assertNotIn('start',commands.call_args.args[0])


if __name__ == '__main__': unittest.main(verbosity=2)
