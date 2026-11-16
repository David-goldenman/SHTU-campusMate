"""Shared recovery and stale results; no campus requests or real credentials."""
import sys
import tempfile
import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from fastapi import HTTPException
from backend.core.store import Store
from backend.services.auth import AuthService, LoginRequired, VerificationRequired
from backend.services.auth import protocols
from checks.check_framework import MemoryVault


def make(directory, name):
    store, vault = Store(directory / (name + '.sqlite3')), MemoryVault()
    auth = AuthService(vault, store, runtime_dir=directory / name)
    vault.save('auth:credentials:gradescope', {'username': 'synthetic', 'password': 'synthetic-password'})
    vault.save('auth:session:gradescope', {'cookies': []})
    auth._adopt_identity('gradescope', 'synthetic')
    return auth, store, vault


def validate(client, *_):
    if client.cookies.get('session') != 'fresh':
        raise LoginRequired('Synthetic expired session')
    return 'synthetic'


def concurrent(directory):
    auth, store, _ = make(directory, 'concurrent')
    entered, release = threading.Event(), threading.Event()
    calls = []

    def login(client, *_):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        client.cookies.set('session', 'fresh', domain='gradescope.com')

    try:
        with patch.object(protocols, 'validate', side_effect=validate), patch.object(protocols, 'login', side_effect=login):
            with ThreadPoolExecutor(max_workers=3) as pool:
                readers = [pool.submit(auth.read_with_recovery, 'gradescope', lambda client: client.cookies.get('session')) for _ in range(3)]
                assert entered.wait(5)
                try:
                    recovery = auth.get_status('gradescope').get('recovery')
                    assert recovery and recovery['status'] == 'running', 'Pending recovery must be observable without blocking on the provider lock'
                    assert recovery['operation_id'] and recovery['automatic']
                finally:
                    release.set()
                assert [future.result(5) for future in readers] == ['fresh'] * 3
                assert len(calls) == 1, 'Concurrent expiry must reuse one renewed session'
                assert auth.get_status('gradescope')['recovery']['status'] == 'available'
    finally:
        release.set()
        auth.close();store.close()


def rejected_then_updated(directory):
    auth, store, vault = make(directory, 'paused')
    try:
        with patch.object(protocols, 'validate', side_effect=validate), patch.object(protocols, 'login', side_effect=LoginRequired('Synthetic credential rejection')) as login:
            for _ in range(2):
                try:
                    auth.read_with_recovery('gradescope', lambda _: 'must not run')
                    raise AssertionError('Rejected credentials must not succeed')
                except LoginRequired:
                    pass
            assert login.call_count == 1
            assert auth.get_status('gradescope')['recovery']['status'] == 'paused'
        auth.close()
        auth = AuthService(vault, store, runtime_dir=directory / 'paused')
        assert auth.get_status('gradescope')['recovery']['status'] == 'paused'
        original_owner = auth.get_account_revision('gradescope')
        auth.save_credentials('gradescope', 'synthetic', 'replacement-password')
        assert auth.get_account_revision('gradescope') == original_owner
        assert auth.get_status('gradescope')['recovery']['status'] == 'available', 'Explicit credential update clears the old rejection pause'
        def login(client, *_):
            client.cookies.set('session', 'fresh', domain='gradescope.com')
        with patch.object(protocols, 'validate', side_effect=validate), patch.object(protocols, 'login', side_effect=login):
            assert auth.read_with_recovery('gradescope', lambda _: 'recovered') == 'recovered'
    finally:
        auth.close();store.close()


def stale_after_renewal(directory):
    auth, store, _ = make(directory, 'renewed')
    calls = []
    def login(client, *_):
        calls.append(1)
        client.cookies.set('session', 'fresh', domain='gradescope.com')
    attempts = []
    def read(client):
        attempts.append(1)
        if len(attempts) == 1:
            # A different caller has renewed before this old response arrives.
            auth.login('gradescope', force=True)
            raise LoginRequired('Synthetic late expiry response')
        return client.cookies.get('session')
    try:
        with patch.object(protocols, 'validate', return_value='synthetic'), patch.object(protocols, 'login', side_effect=login):
            assert auth.read_with_recovery('gradescope', read) == 'fresh'
            assert len(calls) == 1, 'A late expiry cannot force another login or overwrite the renewed cookies'
    finally:
        auth.close();store.close()


def changed_account_and_verification(directory):
    auth, store, vault = make(directory, 'changed')
    try:
        def read(_):
            store.write('auth:revision:gradescope', 'another-synthetic-account')
            vault.save('auth:session:gradescope', {'cookies': [], 'synthetic_new_account': True})
            return 'old-account-result'
        with patch.object(protocols, 'validate', return_value='synthetic'), patch.object(protocols, 'login') as login:
            try:
                auth.read_with_recovery('gradescope', read)
                raise AssertionError('A result from the previous account must be rejected')
            except HTTPException as error:
                assert error.status_code == 409
            assert vault.get('auth:session:gradescope').get('synthetic_new_account')
            assert login.call_count == 0
            try:
                auth.read_with_recovery('gradescope', lambda _: (_ for _ in ()).throw(VerificationRequired('Synthetic verification')))
                raise AssertionError('Verification must remain user-owned')
            except VerificationRequired:
                pass
            assert auth.get_status('gradescope')['recovery']['status'] == 'manual_required'
            assert login.call_count == 0
    finally:
        auth.close();store.close()


def switched_between_attempts(directory):
    auth, store, vault = make(directory, 'between-attempts')
    original = auth._client_lock
    locks = 0
    attempted = []
    @contextmanager
    def switch_after_recovery(provider, cancelled):
        nonlocal locks
        locks += 1
        number = locks
        with original(provider, cancelled):
            yield
        if number == 2:
            auth.save_credentials('gradescope', 'next-account', 'replacement-password')
            auth._adopt_identity('gradescope', 'next-account')
    def read(_):
        attempted.append(vault.get('auth:credentials:gradescope')['username'])
        if len(attempted) == 1:
            raise LoginRequired('Synthetic first-attempt expiry')
        return attempted[-1]
    try:
        with patch.object(auth, '_client_lock', switch_after_recovery), patch.object(protocols, 'validate', side_effect=lambda *_: vault.get('auth:credentials:gradescope')['username']), patch.object(protocols, 'login'):
            try:
                auth.read_with_recovery('gradescope', read)
                raise AssertionError('An original read must not retry under the next account')
            except HTTPException as error:
                assert error.status_code == 409
            assert attempted == ['synthetic']
    finally:
        auth.close();store.close()


def main():
    with tempfile.TemporaryDirectory(prefix='auth-coordination-', dir=PROJECT / '.codex' / 'tmp') as temporary:
        directory = Path(temporary)
        concurrent(directory)
        rejected_then_updated(directory)
        stale_after_renewal(directory)
        changed_account_and_verification(directory)
        switched_between_attempts(directory)
    print('auth coordination: observable single recovery, persistent pause, credential updates, late expiry, account races and verification passed')


if __name__ == '__main__':
    main()
