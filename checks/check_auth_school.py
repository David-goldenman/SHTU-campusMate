"""Unified school login: synthetic sessions only, no remote requests."""
import json
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.core.store import Store
from backend.services.auth import AuthService, LoginRequired, VerificationRequired
from backend.services.auth import protocols
from checks.check_auth import MemoryVault, cookie


@contextmanager
def fixture(directory):
    store = Store(directory / 'store.sqlite3')
    auth = AuthService(MemoryVault(), store, runtime_dir=directory / 'runtime')
    auth.browser = SimpleNamespace(state=lambda _: {'cookies': [cookie(domain='ids.shanghaitech.edu.cn')]},
                                   open=lambda *_: None, close=lambda _: None, close_all=lambda: None, forget=lambda _: None)
    auth.vault.save('auth:session:ids', {'cookies': [cookie(domain='ids.shanghaitech.edu.cn')]})
    auth._adopt_identity('ids', 'school-a')
    try:
        yield auth
    finally:
        auth.close()
        store.close()


def finish(auth):
    # Browser import may replace the watcher future with a queued connection job.
    for _ in range(3):
        current = auth.school.future
        current.result(timeout=20)
        if auth.school.future is current:
            return
    raise AssertionError('Connection did not settle')


def check_partial(auth):
    def validate(client, provider, target, state):
        if target == 'ecourse':
            raise VerificationRequired('Synthetic service verification')
        return 'school-a'
    with patch.object(protocols, 'validate', side_effect=validate), patch.object(protocols, 'login') as login:
        auth.connect_school();finish(auth)
        status = auth.get_status('ids')
        states = {row['id']: row['status'] for row in status['services']}
        assert states == {key: 'login_required' if key == 'ecourse' else 'ready' for key in protocols.SERVICES}
        assert status['status'] == 'ready' and status['connection']['completed'] == 4
        assert login.call_count == 0
        assert not auth.store.read('auth:recovery:ids')
        auth.school.resume();finish(auth)
        assert auth.get_status('ids')['connection']['status'] == 'complete'
    # Returned identity must never silently replace the connected school account.
    owner = auth.get_account_revision('ids')
    with patch.object(protocols, 'validate', return_value='school-b'):
        try:
            with auth.authenticated_client('ids', 'blackboard'):
                raise AssertionError('Mismatched identity was accepted')
        except VerificationRequired:
            pass
    assert auth.get_account_revision('ids') == owner


def check_recovery(auth):
    auth.vault.save('auth:device:ids', {'username': 'school-a'})
    calls = []
    def renew(client):
        calls.append(True)
        client.cookies.set('renewed', 'synthetic', domain='ids.shanghaitech.edu.cn')
        return 'school-a'
    def validate(client, provider, target, state):
        if target == 'ecourse' or not client.cookies.get('renewed'):
            raise LoginRequired('Synthetic expiry')
        return 'school-a'
    with patch.object(auth.device, 'renew', side_effect=renew), patch.object(protocols, 'validate', side_effect=validate):
        auth.connect_school();finish(auth)
    assert len(calls) == 1, 'Other services must reuse the refreshed school SSO cookie'
    assert auth.get_status('ids')['status'] == 'ready'
    assert any(row['name'] == 'renewed' for row in auth.vault.get('auth:session:ids')['cookies'])
    with patch.object(protocols, 'validate', side_effect=LoginRequired('Synthetic expiry')), \
         patch.object(auth.device, 'renew', side_effect=VerificationRequired('Synthetic IDS MFA')) as renew:
        auth.connect_school();finish(auth)
        assert renew.call_count == 1, 'Global school recovery must pause after one rejected credential attempt'
        auth.school.resume();finish(auth)
        assert renew.call_count == 1, 'Restart must preserve the MFA pause'


def check_browser_and_account(auth):
    with patch.object(protocols, 'validate', return_value='school-a'):
        auth.open_browser('ids', 'blackboard');finish(auth)
        assert auth.get_status('ids')['connection']['status'] == 'complete'
        assert all(row['status'] == 'ready' for row in auth.get_status('ids')['services'])
        assert auth.get_status('ids')['browser_target'] is None
    # A deliberate browser account switch clears the old service statuses.
    old_owner = auth.get_account_revision('ids')
    with patch.object(protocols, 'validate', return_value='school-b'):
        auth.import_session('ids', 'elrc');finish(auth)
    assert auth.get_account_revision('ids') != old_owner
    assert all(row['status'] == 'ready' for row in auth.get_status('ids')['services'])
    auth.forget('ids')
    assert not auth.store.read('auth:school:auto_connect', False)
    assert all(row['status'] == 'not_connected' for row in auth.get_status('ids')['services'])


def check_cancel_and_duplicate(auth):
    entered, release = threading.Event(), threading.Event()
    original = auth.school._run
    def delayed(*args):
        entered.set();assert release.wait(10)
        return original(*args)
    with patch.object(auth.school, '_run', side_effect=delayed), patch.object(protocols, 'validate') as validate:
        auth.connect_school();assert entered.wait(2)
        future = auth.school.future
        auth.connect_school()
        assert auth.school.future is future, 'Duplicate connect must share one job'
        auth.forget('ids');release.set();future.result(timeout=5)
        assert validate.call_count == 0 and auth.school.snapshot()['status'] == 'idle'
        assert not auth.get_status('ids')['has_session']


def main():
    temporary = Path(__file__).resolve().parents[1] / '.codex' / 'tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    real_client = httpx.Client
    def synthetic_client(**kwargs):
        kwargs.pop('mounts', None)
        def unexpected(request):
            raise AssertionError('Synthetic checks must never contact a remote service')
        return real_client(transport=httpx.MockTransport(unexpected), trust_env=False, **kwargs)
    with patch.object(protocols.httpx, 'Client', side_effect=synthetic_client):
        for check in (check_partial, check_recovery, check_browser_and_account, check_cancel_and_duplicate):
            with tempfile.TemporaryDirectory(dir=temporary) as directory, fixture(Path(directory)) as auth:
                check(auth)
    print(json.dumps({'unified_school_login':'passed','partial_failure':'isolated','recovery':'bounded','data':'synthetic'}))


if __name__ == '__main__':
    main()
