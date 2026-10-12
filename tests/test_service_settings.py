import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch
import service
import session
import settings


class ServiceSettingsTests(unittest.TestCase):
    def test_service_snapshots_settings_and_passes_name_and_folder_without_a_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            cfg={'user_data':str(root/'data'),'download_dir':str(root), 'interface':'testwifi'}
            settings.save_preferences(cfg,{'receiver_name':'Custom Receiver','duration_seconds':600})
            user=pwd.getpwuid(os.getuid())
            path=root/'session.json'
            original_prepare=session.prepare
            with patch.object(service,'configuration',return_value=(cfg,user)), \
                    patch('os.geteuid',return_value=0), patch('sys.argv',['service','run']), \
                    patch.object(service.subprocess,'run') as mkdir, \
                    patch.object(session,'prepare',side_effect=lambda prefs: original_prepare(prefs,path)), \
                    patch.object(service.os,'execve',side_effect=RuntimeError('exec intercepted')) as launch:
                with self.assertRaisesRegex(RuntimeError,'exec intercepted'): service.main()
            args=launch.call_args.args
            self.assertEqual(args[0],'/bin/bash')
            self.assertEqual(args[2]['AIR_DROP_RECEIVER_NAME'],'Custom Receiver')
            self.assertEqual(args[2]['AIR_DROP_RECEIVED_DIR'],str(root))
            self.assertEqual(args[2]['AIR_DROP_INTERFACE'],'testwifi')
            self.assertIn('/usr/sbin/runuser',mkdir.call_args.args[0])
            settings.save_preferences(cfg,{'receiver_name':'Next Session','duration_seconds':300})
            session.ready(path)
            self.assertEqual(session.read_json(path)['receiver_name'],'Custom Receiver')
            self.assertEqual(session.read_json(path)['duration_seconds'],600)
            self.assertEqual(settings.preferences(cfg)['receiver_name'],'Next Session')


if __name__=='__main__': unittest.main(verbosity=2)
