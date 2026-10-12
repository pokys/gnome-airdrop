"""Diagnostic export is an allowlist, never a filtered receiver log."""
import platform
from pathlib import Path
import re

VERSION = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
PHASES = {'idle', 'waiting', 'receiving', 'verifying', 'completed', 'error'}
ERRORS = {'timeout', 'interrupted', 'storage', 'limit', 'invalid_archive', 'unsupported_type', 'busy'}
STATES = {'active', 'activating', 'deactivating', 'inactive', 'failed'}


def bounded_number(value, maximum):
    return value if type(value) in (int, float) and 0 <= value <= maximum else None


def known(value, options, fallback=None):
    return value if isinstance(value, str) and value in options else fallback


def report(status):
    transfer = status.get('transfer')
    transfer = transfer if isinstance(transfer, dict) else {}
    window = status.get('session')
    window = window if isinstance(window, dict) else {}
    try:
        distro = platform.freedesktop_os_release()
    except OSError:
        distro = {}
    distro_id = distro.get('ID')
    version = distro.get('VERSION_ID', '')
    # Version strings only; PRETTY_NAME, hostname and machine identifiers are
    # never exported. Unknown distro identifiers are intentionally not echoed.
    os_id = distro_id if distro_id in {'fedora', 'ubuntu', 'debian', 'arch', 'opensuse', 'rhel'} else 'other'
    match = re.match(r'^[0-9]+\.[0-9]+(?:\.[0-9]+)?', platform.release())
    kernel = match.group(0) if match else None
    return {
        'schema': 1, 'application_version': VERSION,
        'system': {'os_id': os_id, 'os_version': version if re.fullmatch(r'[0-9.]{1,20}', version) else None,
                   'kernel': kernel},
        'service': {'installed': status.get('installed') is True,
                    'state': known(status.get('state'), STATES, 'unknown'),
                    'receiving': status.get('receiving') is True,
                    'duration_seconds': window.get('duration_seconds') if type(window.get('duration_seconds')) is int
                        and window['duration_seconds'] in (0, 300, 600) else None},
        'transfer': {'phase': known(transfer.get('phase'), PHASES, 'unknown'),
                     'error': known(transfer.get('error'), ERRORS),
                     'file_count': bounded_number(transfer.get('file_count'), 512),
                     'wire_bytes': bounded_number(transfer.get('wire_bytes'), 2**63-1),
                     'bytes_per_second': bounded_number(transfer.get('bytes_per_second'), 10**12)},
    }
