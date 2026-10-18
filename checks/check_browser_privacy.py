"""Navigation tokens are removed while the persistent login profile survives."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.errors import PublicError
from backend.core.paths import PROJECT
from backend.services.auth.browser import VerificationBrowser


def check(directory):
    browser = VerificationBrowser(directory)
    profile = directory / 'coremail'
    preserved = ['Default/Network/Cookies', 'Local State', 'Default/Local Storage/leveldb/keep.ldb']
    navigation = ['Default/History', 'Default/History-wal', 'Default/Favicons',
                  'Default/Sessions/Tabs_1', 'Default/Session Storage/entry',
                  'Default/Sync Data/LevelDB/entry', 'cache/item', 'temp/item']
    for name in preserved + navigation:
        path = profile / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic-token')
    with patch.object(browser, '_run', return_value={'closed': True}) as command:
        browser.close('coremail')
        command.assert_called_once_with('close', 'coremail')
    assert all((profile / name).read_bytes() == b'synthetic-token' for name in preserved)
    assert not any((profile / name).exists() for name in navigation)
    browser.clear_navigation('coremail')
    locked = profile / 'Default/History'
    locked.write_bytes(b'synthetic-token')
    with patch.object(Path, 'unlink', side_effect=PermissionError('synthetic lock')):
        try:
            browser.clear_navigation('coremail')
            raise AssertionError('Cleanup failures must remain visible')
        except PublicError:
            pass
    assert locked.exists() and all((profile / name).exists() for name in preserved)
    print('browser privacy: history/tabs/cache removed, cookies/login storage retained, cleanup errors visible')


if __name__ == '__main__':
    temporary = PROJECT / '.codex/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary, prefix='browser-privacy-') as folder:
        check(Path(folder))
