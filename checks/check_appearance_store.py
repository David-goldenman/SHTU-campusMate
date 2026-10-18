"""Offline appearance checks: synthetic SQLite values and in-process HTTP only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx
from fastapi import HTTPException

from backend.core.appearance import AppearanceUpdate, DEFAULT, patch_appearance, read_appearance, reset_core
from backend.core.store import Store
from backend.main import create_app


class MemoryVault:
    transaction = staticmethod(nullcontext)

    def __init__(self):
        self.values = {}

    def get(self, key):
        return deepcopy(self.values.get(key, {}))

    def save(self, key, value):
        self.values[key] = deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)

    def delete_prefix(self, prefix):
        self.values = {key: value for key, value in self.values.items() if not key.startswith(prefix)}

    def clear(self):
        self.values.clear()


def application(root):
    store = Store(root / 'state.sqlite3')
    app = create_app(active_port=17666, store=store, vault=MemoryVault(), modules_root=root / 'code-modules', data_dir=root)
    app.state.auth.browser = SimpleNamespace(close=lambda provider: None, forget=lambda provider: None, close_all=lambda: None)
    return app, store


async def check_api(root):
    (root / 'code-modules').mkdir()
    app, store = application(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17666') as client:
            bootstrap = (await client.get('/api/v1/bootstrap')).json()
            assert bootstrap['settings']['appearance'] == {'revision': 0, 'resetRevision': 0, 'value': None}
            first = {'revision': 0, 'patch': {'theme': 'future-theme', 'companions': {'future-theme': 'robot'},
                                            'options': {'future-theme': {'unknown': {'keep': True, 'change': 1}, 'list': [1, 2]},
                                                        'temporarily-missing': {'saved': 'retain'}}}}
            assert (await client.patch('/api/v1/settings/appearance', json=first)).status_code == 403
            client.headers['X-Framework-Token'] = bootstrap['csrf_token']
            saved = await client.patch('/api/v1/settings/appearance', json=first)
            assert saved.status_code == 200, saved.text
            record = saved.json()
            assert record['revision'] == 1 and record['resetRevision'] == 0 and record['value']['theme'] == 'future-theme'
            assert record['value']['reduceMotion'] is False and record['value']['companions']['future-theme'] == 'robot'
            response = await client.put('/api/v1/settings', json={'port': 17667})
            assert response.status_code == 200 and response.json()['appearance'] == record
            assert store.read('settings') == {'port': 17667}
            update = {'revision': 1, 'patch': {'reduceMotion': True, 'options': {'future-theme': {'unknown': {'change': 2}, 'list': [3]}}}}
            response = await client.patch('/api/v1/settings/appearance', json=update)
            assert response.status_code == 200, response.text
            latest = response.json()
            assert latest['revision'] == 2 and latest['resetRevision'] == 0
            assert latest['value']['options']['future-theme'] == {'unknown': {'keep': True, 'change': 2}, 'list': [3]}
            assert latest['value']['options']['temporarily-missing'] == {'saved': 'retain'}
            assert store.read('settings') == {'port': 17667}, 'appearance must not overwrite port'
            assert (await client.patch('/api/v1/settings/appearance', json=first)).status_code == 409
            assert read_appearance(store) == latest, 'stale writes must not mutate appearance'
            deep = 1
            for _ in range(9):
                deep = {'nested': deep}
            bad_patches = [
                {'unknown-top': True}, {'theme': '../bad'}, {'theme': None}, {'reduceMotion': 'false'},
                {'companions': {'future-theme': 3}}, {'options': {'future-theme': []}},
                {'options': {'future-theme': {'__proto__': {'polluted': True}}}},
                {'options': {'future-theme': {'a': [{'constructor': True}]}}},
                {'options': {'future-theme': {'prototype': {}}}}, {'options': {'future-theme': deep}},
                {'options': {'future-theme': {'text': 'x' * 8193}}},
                {'options': {'future-theme': {'text' + str(i): 'x' * 8192 for i in range(9)}}},
                {'options': {'future-theme': {'list': list(range(129))}}},
                {'options': {'future-theme': {'number': 10**400}}},
                {'options': {'future-theme': {'values': {str(i): list(range(128)) for i in range(33)}}}},
            ]
            for patch in bad_patches:
                response = await client.patch('/api/v1/settings/appearance', json={'revision': 2, 'patch': patch})
                assert response.status_code == 422, (patch.keys(), response.status_code, response.text)
            for revision in (True, '2', -1, 2**53):
                response = await client.patch('/api/v1/settings/appearance', json={'revision': revision, 'patch': {}})
                assert response.status_code == 422
            # Separate small patches may collectively exceed the full saved limit.
            large = {'revision': 2, 'patch': {'options': {'large-theme': {str(i): 'a' * 7000 for i in range(8)}}}}
            response = await client.patch('/api/v1/settings/appearance', json=large)
            assert response.status_code == 200, response.text
            latest = response.json()
            too_large = {'revision': 3, 'patch': {'options': {'large-theme': {'extra': 'b' * 8192, 'more': 'c' * 8192}}}}
            response = await client.patch('/api/v1/settings/appearance', json=too_large)
            assert response.status_code == 422 and read_appearance(store) == latest
            response = await client.patch('/api/v1/settings/appearance', json={'revision': latest['revision'], 'resetRevision': 0, 'patch': {}})
            assert response.status_code == 422, 'the reset barrier is response-only'
            fresh = (await client.get('/api/v1/settings')).json()
            assert fresh['appearance'] == latest and fresh['port'] == 17667
    # New Store, new application, same synthetic DB: verify restart persistence.
    app, store = application(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17666') as client:
            settings = (await client.get('/api/v1/bootstrap')).json()['settings']
            assert settings['appearance'] == latest and settings['port'] == 17667
            client.headers['X-Framework-Token'] = (await client.get('/api/v1/bootstrap')).json()['csrf_token']
            store.write('synthetic-core-custom', {'discard': True})
            response = await client.post('/api/v1/data/clear', json={'scope': 'all', 'confirmation': 'CLEAR'})
            assert response.status_code == 200, response.text
            reset = read_appearance(store)
            assert reset == {'revision': latest['revision'] + 1, 'resetRevision': latest['revision'] + 1, 'value': DEFAULT}
            assert store.read('settings') is None and store.read('synthetic-core-custom') is None
            keys = store.db.execute('SELECT key FROM state WHERE namespace=?', (store.namespace,)).fetchall()
            assert keys == [('appearance',)], 'all must not retain old custom core settings'
            fresh = (await client.get('/api/v1/bootstrap')).json()['settings']
            assert fresh['appearance'] == reset and fresh['port'] == 16666
            assert (await client.patch('/api/v1/settings/appearance', json={'revision': latest['revision'], 'patch': {'theme': 'stale-theme'}})).status_code == 409
    app, store = application(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17666') as client:
            fresh = (await client.get('/api/v1/bootstrap')).json()['settings']
            assert fresh['appearance'] == reset, 'restart must keep explicit defaults and block legacy migration'


def check_concurrent(root):
    stores = [Store(root / 'race.sqlite3') for _ in range(2)]
    barrier = threading.Barrier(2)

    def write(index):
        barrier.wait()
        try:
            return patch_appearance(stores[index], AppearanceUpdate(revision=0, patch={'theme': 'choice-' + str(index)}))
        except HTTPException as error:
            return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, range(2)))
        assert sum(isinstance(result, dict) for result in results) == 1
        assert results.count(409) == 1, 'two connections with one revision need exactly one winner'
        assert read_appearance(stores[0]) == read_appearance(stores[1])
        before = read_appearance(stores[0])
        stores[0].write('synthetic-custom', {'discard': True})
        reset = reset_core(stores[1])
        assert reset == {'revision': before['revision'] + 1, 'resetRevision': before['revision'] + 1, 'value': DEFAULT}
        assert stores[0].read('synthetic-custom') is None
        try:
            patch_appearance(stores[0], AppearanceUpdate(revision=before['revision'], patch={'theme': 'stale-theme'}))
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError('A connection holding the pre-reset revision must not overwrite explicit defaults')
        assert read_appearance(stores[0]) == reset
    finally:
        for store in stores:
            store.close()


def check_legacy_record(root):
    store = Store(root / 'legacy.sqlite3')
    try:
        legacy = {**deepcopy(DEFAULT), 'theme': 'legacy-theme'}
        store.write('appearance', {'revision': 7, 'value': legacy})
        assert read_appearance(store) == {'revision': 7, 'resetRevision': 0, 'value': legacy}
        ordinary = patch_appearance(store, AppearanceUpdate(revision=7, patch={'reduceMotion': True}))
        assert ordinary['revision'] == 8 and ordinary['resetRevision'] == 0
        reset = reset_core(store)
        assert reset == {'revision': 9, 'resetRevision': 9, 'value': DEFAULT}
        ordinary = patch_appearance(store, AppearanceUpdate(revision=9, patch={'theme': 'new-theme'}))
        assert ordinary['revision'] == 10 and ordinary['resetRevision'] == 9
        assert read_appearance(store) == ordinary
    finally:
        store.close()


if __name__ == '__main__':
    temporary = PROJECT / '.codex' / 'tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='appearance-store-', dir=temporary) as directory:
        root = Path(directory)
        asyncio.run(check_api(root))
        check_concurrent(root)
        check_legacy_record(root)
    print('appearance store: initial migration, CSRF, port isolation, recursive preservation, validation bounds, restart, all-reset barrier, legacy records and concurrent CAS passed')
