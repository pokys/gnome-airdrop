"""One user-owned settings file; changes apply on the next receiving session."""
import json
import os
from pathlib import Path
import tempfile
import unicodedata
from session import read_json

DURATIONS = (0, 300, 600)
DEFAULT_NAME = 'GNOME-AirDrop'


def valid_name(value):
    return (isinstance(value, str) and 1 <= len(value.strip()) <= 63
            and value == value.strip()
            and not any(c in '/\\' or unicodedata.category(c).startswith('C') for c in value))


def preferences(config):
    values = {'download_dir': config['download_dir'], 'receiver_name': DEFAULT_NAME,
              'duration_seconds': 0}
    saved = read_json(Path(config['user_data']) / 'settings.json', limit=16384)
    if saved is None:
        return values
    folder = saved.get('download_dir')
    if isinstance(folder, str) and Path(folder).is_absolute() and '\0' not in folder:
        values['download_dir'] = folder
    if valid_name(saved.get('receiver_name')):
        values['receiver_name'] = saved['receiver_name']
    duration = saved.get('duration_seconds')
    if type(duration) is int and duration in DURATIONS:
        values['duration_seconds'] = duration
    return values


def download_directory(config):
    return preferences(config)['download_dir']


def save_preferences(config, changes):
    if not isinstance(changes, dict) or set(changes) - {'download_dir', 'receiver_name', 'duration_seconds'}:
        raise ValueError('Neznámé nastavení.')
    values = dict(preferences(config), **changes)
    if not valid_name(values['receiver_name']):
        raise ValueError('Jméno musí mít 1 až 63 znaků, bez lomítek a řídicích znaků.')
    if type(values['duration_seconds']) is not int or values['duration_seconds'] not in DURATIONS:
        raise ValueError('Délka příjmu musí být do vypnutí, 5 nebo 10 minut.')
    folder = values['download_dir']
    if not isinstance(folder, str) or '\0' in folder:
        raise ValueError('Vyberte existující složku.')
    path = Path(folder).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('Vyberte existující složku s úplnou cestou.')
    path = path.resolve()
    if path.stat().st_uid != os.getuid() or not os.access(path, os.W_OK | os.X_OK):
        raise ValueError('Složka vám musí patřit a musí do ní jít zapisovat.')
    values['download_dir'] = str(path)
    data = Path(config['user_data'])
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.settings-', dir=data)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(values, stream, ensure_ascii=False)
            stream.write('\n')
        os.replace(temporary, data / 'settings.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_download_directory(config, value):
    save_preferences(config, {'download_dir': value})
