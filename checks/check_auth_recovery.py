"""Account ownership and passwordless recovery use synthetic identities only."""
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import HTTPException
from backend.core.store import Store
from backend.core.vault import Vault
from backend.services.auth import AuthService, LoginRequired, VerificationRequired
from backend.services.auth import protocols
from backend.services.auth.device import DeviceCredential, BASE
from backend.services.campus.accounts import AccountCache
from checks.check_auth import MemoryVault, cookie


def check_identity(directory):
    vault, store = MemoryVault(), Store(directory / 'identity.sqlite3')
    auth = AuthService(vault, store, runtime_dir=directory / 'runtime')
    auth.browser = SimpleNamespace(state=lambda provider: {'cookies': [cookie()]}, close=lambda provider: None, forget=lambda provider: None)
    vault.save('auth:session:gradescope', {'cookies': [cookie()]})
    context = SimpleNamespace(auth=auth, store=store, data_dir=directory)
    cache = AccountCache(context, 'gradescope')
    with patch.object(protocols, 'validate', return_value='user:a'), patch.object(protocols, 'login') as login:
        auth.refresh('gradescope')
        first = auth.get_status('gradescope')['account_revision']
        with patch.object(protocols, 'validate', side_effect=httpx.ConnectError('Synthetic network interruption')):
            try:
                auth.refresh('gradescope')
                raise AssertionError('Network failures must remain network failures')
            except httpx.ConnectError:
                pass
        assert auth.get_status('gradescope')['status'] == 'ready'
        assert auth.get_status('gradescope')['has_session']
        assert login.call_count == 0
        old = cache.capture()
        old.store.write('courses', ['account-a'])
        auth.import_session('gradescope')
        assert auth.get_status('gradescope')['account_revision'] == first
        assert cache.capture().store.read('courses') == ['account-a']
        auth.save_credentials('gradescope', 'synthetic@example.edu', 'synthetic-password')
        auth.login('gradescope')
        assert auth.get_status('gradescope')['account_revision'] == first
        calls = []
        def reading(client):
            calls.append(True)
            if len(calls) == 1:
                raise LoginRequired('Synthetic expiry during pagination')
            return 'recovered'
        login.reset_mock()
        assert auth.read_with_recovery('gradescope', reading) == 'recovered'
        assert len(calls) == 2 and login.call_count == 1
        assert auth.get_status('gradescope')['account_revision'] == first
        login.reset_mock()
        try:
            auth.read_with_recovery('gradescope', lambda client: (_ for _ in ()).throw(VerificationRequired('Synthetic MFA')))
            raise AssertionError('MFA must require user action')
        except VerificationRequired:
            pass
        assert login.call_count == 0
    with patch.object(protocols, 'validate', return_value='user:b'):
        auth.import_session('gradescope')
    assert cache.capture().store.read('courses', []) == []
    assert cache.capture().data_dir != old.data_dir
    try:
        cache.check(old)
        raise AssertionError('An in-flight old account must not return data')
    except HTTPException as error:
        assert error.status_code == 409
    cache.capture().store.write('courses', ['account-b'])
    with patch.object(protocols, 'validate', return_value='user:a'):
        auth.import_session('gradescope')
    assert cache.capture().store.read('courses') == ['account-a']
    assert auth.get_status('gradescope')['account_revision'] == first
    # A device for A must never silently replace a manually imported B account.
    vault.save('auth:device:ids', {'username': 'school-a'})
    auth._adopt_identity('ids', 'school-b')
    assert auth.get_status('ids')['device']['enabled'] is False
    # Unknown ownership of an expired legacy session must not migrate to a new login.
    vault.save('auth:session:piazza', {'cookies': []})
    vault.save('auth:credentials:piazza', {'username': 'new', 'password': 'synthetic'})
    unknown = auth.get_status('piazza')['account_revision']
    with patch.object(protocols, 'validate', side_effect=[LoginRequired('expired'), 'new']), patch.object(protocols, 'login'):
        auth.login('piazza')
    assert auth.get_status('piazza')['account_revision'] != unknown
    store.close()


def check_device(directory):
    path = directory / 'counter.dpapi'
    vault = Vault(path)
    second = Vault(path)
    vault.save('first', {'value': 1})
    second.save('second', {'value': 2})
    assert vault.get('second') == {'value': 2} and second.get('first') == {'value': 1}
    key = {'username':'school-a','anon_biometrics_id':'synthetic','device_name':'Synthetic device','base_url':BASE,
           'credential_id':'synthetic','rp_id':'ids.shanghaitech.edu.cn','user_id':'synthetic','alg':-7,
           'private_key_pem':'synthetic-private-key','sign_count':0,'created_at':'2026-10-16T00:00:00Z'}
    vault.save('auth:device:ids', key)
    def failed_client(credential, **kwargs):
        def login():
            credential.sign_count += 1
            raise RuntimeError('synthetic-private-response')
        return SimpleNamespace(login=login)
    with patch('backend.services.auth.device.IDSClient', side_effect=failed_client), httpx.Client() as client:
        for current in (vault, second):
            try:
                DeviceCredential(current).renew(client)
                raise AssertionError('Synthetic login must fail')
            except VerificationRequired as error:
                assert 'synthetic-private-response' not in str(error)
    assert vault.get('auth:device:ids')['sign_count'] == 2
    DeviceCredential(vault).forget()
    device = DeviceCredential(vault)
    metadata = {name: value for name, value in key.items() if name not in {'username','anon_biometrics_id','device_name','base_url'}}
    def response(client, method, url, **kwargs):
        if url.endswith('isUserRecheckNecessary'):
            return {'code':'0'}
        if url.endswith('startRegister'):
            return {'code':'0','datas':{'request':{'username':'school-a','requestId':'synthetic','publicKeyCredentialCreationOptions':{'rp':{'id':'ids.shanghaitech.edu.cn'}}}}}
        assert vault.get('auth:device-pending:ids')['private_key_pem'] == 'synthetic-private-key'
        raise VerificationRequired('Synthetic uncertain registration response')
    with patch.object(device, '_json', side_effect=response), patch('backend.services.auth.device.create_registration_response', return_value=({},metadata)):
        try:
            device.enroll(None)
            raise AssertionError('An uncertain response must not be declared successful')
        except VerificationRequired:
            pass
    assert device.status()['pending'] and not device.status()['configured']
    with patch('backend.services.auth.device.IDSClient', return_value=SimpleNamespace(login=lambda: None)):
        device.recover_pending()
    assert device.status()['configured'] and not device.status()['pending']


def check_setup(directory):
    vault, store = MemoryVault(), Store(directory / 'setup.sqlite3')
    auth = AuthService(vault, store, runtime_dir=directory / 'runtime')
    opened = []
    auth.browser = SimpleNamespace(open=lambda *args, **kwargs: opened.append((args,kwargs)),
        state=lambda provider: {'cookies': []}, close_all=lambda: None)
    with patch.object(auth.device, 'ready_to_enroll', side_effect=[False,True]), patch.object(auth, 'bind_device') as bind, patch.object(auth.setup_cancelled, 'wait', return_value=False):
        auth.start_device_setup()
        auth.setup_future.result(timeout=5)
        assert bind.call_count == 1
        assert opened[0][1] == {'device_setup':True}
        assert opened[0][0][1].endswith('#/accountsecurity')
        assert auth.get_status('ids')['device']['setup']['status'] == 'ready'
    auth.close()
    store.close()


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / '.codex'
    with tempfile.TemporaryDirectory(prefix='recovery-check-', dir=root) as temporary:
        directory = Path(temporary)
        check_identity(directory)
        check_device(directory)
        check_setup(directory)
    print(json.dumps({'auth_recovery':'passed','account_isolation':'passed','counter_persistence':'passed','pending_registration':'passed','data':'synthetic'}))
