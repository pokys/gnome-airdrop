"""Exercise the real installer against temporary paths and fake OS integrations."""
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.package = self.base/'package'
        shutil.copytree(ROOT/'dist/gnome-airdrop', self.package)
        self.home = self.base/'home'
        self.home.mkdir()
        self.downloads = self.home/'Custom Downloads'
        self.downloads.mkdir()
        (self.downloads/'keep.txt').write_text('user data')
        self.target = self.base/'opt/gnome-airdrop'
        (self.base/'opt').mkdir()
        (self.base/'etc/systemd/system').mkdir(parents=True)
        (self.base/'usr/share/polkit-1/actions').mkdir(parents=True)
        (self.base/'sys/class/net/testwifi').mkdir(parents=True)
        source = (self.package/'install.sh').read_text()
        source = source.replace('if [[ $EUID != 0 ]]; then exec sudo /bin/bash "$PACKAGE/install.sh" "$@"; fi', '')
        for original in ('/opt/', '/etc/systemd/system/', '/usr/share/polkit-1/actions/', '/sys/class/net/'):
            source = source.replace(original, str(self.base)+original)
        (self.package/'install.sh').write_text(source)
        mocks = self.base/'mocks'
        mocks.mkdir()
        mock = '''#!/usr/bin/python3
import os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'getent': print('user:x:1000:1000::'+os.environ['TEST_HOME']+':/bin/bash')
elif name == 'xdg-user-dir': print(os.environ['TEST_DOWNLOADS'])
elif name == 'readlink': print('/fake/iwlwifi')
elif name == 'iw': print('Interface testwifi')
elif name == 'systemctl' and args[:1] == ['is-active']: sys.exit(3)
elif name == 'gnome-extensions' and args[:1] == ['install'] and os.environ.get('TEST_FAIL'): sys.exit(1)
elif name == 'runuser':
    args = args[args.index('--')+1:]
    os.execvp(args[0], args)
'''
        for name in ('getent','xdg-user-dir','readlink','iw','systemctl','gnome-extensions','runuser','restorecon','chown'):
            path = mocks/name
            path.write_text(mock)
            path.chmod(0o755)
        user = pwd.getpwuid(os.getuid())
        self.env = dict(os.environ, PATH=str(mocks)+':'+os.environ['PATH'],
                        SUDO_USER=user.pw_name, SUDO_UID=str(user.pw_uid),
                        TEST_HOME=str(self.home), TEST_DOWNLOADS=str(self.downloads))

    def install(self, fail=False):
        return subprocess.run(['/bin/bash', str(self.package/'install.sh'), 'testwifi'],
            env=dict(self.env, **({'TEST_FAIL':'1'} if fail else {})),
            capture_output=True, text=True)

    def test_standalone_install_uses_user_downloads_and_fixed_backend(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        config = json.loads((self.target/'config.json').read_text())
        self.assertEqual(config['interface'], 'testwifi')
        self.assertEqual(config['download_dir'], str(self.downloads))
        self.assertEqual(config['user_data'], str(self.home/'.local/share/gnome-airdrop'))
        self.assertTrue(os.access(self.target/'uninstall.sh', os.X_OK))
        shutil.rmtree(self.package)
        self.assertTrue((self.target/'lib/radio/owl').is_file())
        self.assertTrue((self.base/'etc/systemd/system/gnome-airdrop.service').is_file())
        self.assertEqual((self.downloads/'keep.txt').read_text(), 'user data')

    def test_failed_gnome_registration_rolls_back_installation(self):
        result = self.install(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.base/'etc/systemd/system/gnome-airdrop.service').exists())
        self.assertFalse((self.base/'usr/share/polkit-1/actions/io.github.pokys.gnome-airdrop.policy').exists())
        self.assertEqual((self.downloads/'keep.txt').read_text(), 'user data')
        self.assertEqual(list((self.base/'opt').iterdir()), [])


if __name__ == '__main__': unittest.main(verbosity=2)
