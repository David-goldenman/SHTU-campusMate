"""Explicit local paths, without the standalone QJQ configuration."""
from pathlib import Path
from .crypto import NativeError


def local_folder(value: str) -> Path:
    path = Path(value.strip().strip('"')).expanduser()
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or not path.is_dir():
        raise NativeError('wechat_folder_invalid')
    path = path.resolve()
    if str(path).startswith(('\\\\', '//')) or path in (Path(path.anchor), Path.home().resolve()):
        raise NativeError('wechat_folder_invalid')
    return path
