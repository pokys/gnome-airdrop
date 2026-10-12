"""User-owned preferences; root never creates files in the chosen download path."""
import json
import os
from pathlib import Path
import tempfile


def download_directory(config):
    try:
        settings = json.loads((Path(config['user_data']) / 'settings.json').read_text())
        value = settings['download_dir']
        if isinstance(value, str) and Path(value).is_absolute() and '\0' not in value:
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return config['download_dir']


def save_download_directory(config, value):
    path = Path(value).expanduser()
    if not path.is_absolute() or '\0' in value or not path.is_dir():
        raise ValueError('Vyberte existující složku s úplnou cestou.')
    path = path.resolve()
    if not os.access(path, os.W_OK | os.X_OK):
        raise ValueError('Do zvolené složky nelze zapisovat.')
    data = Path(config['user_data'])
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.settings-', dir=data)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'download_dir': str(path)}, stream, ensure_ascii=False)
            stream.write('\n')
        os.replace(temporary, data / 'settings.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
