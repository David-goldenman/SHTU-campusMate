import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PACKAGED = os.environ.get('CAMPUS_PACKAGED') == '1'


def data_directory():
    configured = os.environ.get('CAMPUS_DATA_DIR')
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError('CAMPUS_DATA_DIR must be an absolute path')
        # iOS boot compares this path with its configured sandbox path; keep
        # that spelling outside the packaged Windows installation.
        return path.resolve() if PACKAGED else path
    if PACKAGED:
        parent = os.environ.get('LOCALAPPDATA')
        if not parent or not Path(parent).is_absolute():
            raise ValueError('Packaged Windows app requires LOCALAPPDATA or CAMPUS_DATA_DIR')
        return Path(parent) / 'campusMate' / 'data'
    return PROJECT / '.private'


DATA = data_directory()
RUNTIME = DATA / "runtime"
WEB = PROJECT / "web"
MODULES = PROJECT / "modules"
DATA.mkdir(parents=True, exist_ok=True)
