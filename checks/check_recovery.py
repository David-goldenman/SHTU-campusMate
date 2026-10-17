"""Structured failures, truthful runtime status and reversible local module data."""
import asyncio
import io
import json
import logging
import sqlite3
import sys
import tempfile
import threading
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from backend.core.store import Store
from backend.core.errors import PublicError
from backend.main import create_app
from checks.check_framework import MemoryVault, fixture


async def check(root):
    modules, data = root / 'modules', root / 'data'
    modules.mkdir(); data.mkdir()
    fixture(modules, 'alpha', 'one'); fixture(modules, 'beta', 'two')
    fixture(modules, 'gamma', 'broken')
    (modules / 'gamma/server/__init__.py').write_text("def create_router(context):\n    raise ValueError('synthetic-private-startup')\n")
    store, vault = Store(data / 'state.sqlite3'), MemoryVault()
    store.write('auth:synthetic', {'private': 'synthetic-core-secret'})
    vault.save('synthetic', {'private': 'synthetic-vault-secret'})
    app = create_app(active_port=17668, store=store, vault=vault, modules_root=modules, data_dir=data)
    manager, backups = app.state.modules, app.state.backups
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17668') as client:
            bootstrap = await client.get('/api/v1/bootstrap')
            assert 'synthetic-private-startup' not in bootstrap.text
            assert next(item for item in bootstrap.json()['modules'] if item['id'] == 'gamma')['status'] == 'error'
            client.headers['X-Framework-Token'] = bootstrap.json()['csrf_token']
            alpha = manager.entries['alpha']
            @alpha.app.get('/failure')
            def failure():
                raise KeyError('synthetic-private-exception')
            @alpha.app.get('/storage-failure')
            def storage_failure():
                raise sqlite3.OperationalError('synthetic-private-database-path')
            @alpha.app.get('/runtime-failure')
            def runtime_failure():
                raise RuntimeError('synthetic-private-environment')
            @alpha.app.get('/public-failure')
            def public_failure():
                raise PublicError('请重新打开验证窗口。')
            @app.get('/host-failure')
            def host_failure():
                raise KeyError('synthetic-private-exception')

            log = io.StringIO()
            handler = logging.StreamHandler(log)
            logging.getLogger('campus.errors').addHandler(handler)
            try:
                for path, code in [('/api/v1/modules/alpha/failure', 'internal_error'), ('/api/v1/modules/alpha/storage-failure', 'storage_error'), ('/host-failure', 'internal_error')]:
                    response = await client.get(path)
                    assert response.status_code == 500
                    error = response.json()
                    assert error['code'] == code and error['action'] and len(error['request_id']) == 12
                    assert response.headers['x-request-id'] == error['request_id']
                    assert 'synthetic-private' not in response.text
                assert 'synthetic-private' not in log.getvalue() and 'type=KeyError' in log.getvalue()
            finally:
                logging.getLogger('campus.errors').removeHandler(handler)
            response = await client.get('/api/v1/modules/alpha/runtime-failure')
            assert response.status_code == 400 and 'synthetic-private' not in response.text
            response = await client.get('/api/v1/modules/alpha/public-failure')
            assert response.status_code == 400 and response.json()['detail'] == '请重新打开验证窗口。'
            await client.get('/api/v1/modules/alpha/storage-failure')
            await client.get('/api/v1/modules/alpha/state')
            info = (await client.get('/api/v1/modules')).json()['modules'][0]['runtime']
            assert info['last_success_at'] and info['last_request']['status'] == 200 and info['last_error']['code'] == 'storage_error'
            assert info['active_requests'] == info['pending_calls'] == 0

            release = threading.Event()
            thread = threading.Thread(target=release.wait)
            thread.start()
            pending = Future()
            alpha.context.runtime.watch('worker', thread)
            alpha.context.runtime.watch('task', pending)
            try:
                assert [worker['status'] for worker in alpha.runtime.snapshot()['workers']] == ['running', 'running']
                pending.set_exception(ValueError('synthetic-private-worker'))
            finally:
                release.set(); thread.join()
            assert [worker['status'] for worker in alpha.runtime.snapshot()['workers']] == ['stopped', 'error']

            def current():
                return manager.entries['alpha'].context
            current().store.write('record', {'text': 'version one'})
            (current().data_dir / 'note.txt').write_text('file one', encoding='utf-8')
            response = await client.post('/api/v1/data/backups')
            assert response.status_code == 200, response.text
            original = response.json()['backup']['id']
            rows = json.loads((backups.root / original / 'state.json').read_text(encoding='utf-8'))
            assert rows and all(row[0].startswith('module:') for row in rows)
            assert 'synthetic-core-secret' not in json.dumps(rows) and 'synthetic-vault-secret' not in json.dumps(rows)
            assert set(path.name for path in (backups.root / original).iterdir()) == {'metadata.json','state.json','modules'}
            current().store.write('record', {'text': 'version two'})
            (current().data_dir / 'note.txt').write_text('file two', encoding='utf-8')
            (current().data_dir / 'extra.txt').write_text('new file', encoding='utf-8')
            response = await client.post(f'/api/v1/data/backups/{original}/restore', json={'confirmation':'RESTORE'})
            assert response.status_code == 200, response.text
            before_restore = response.json()['backup']['id']
            assert current().store.read('record') == {'text':'version one'}
            assert (current().data_dir / 'note.txt').read_text() == 'file one' and not (current().data_dir / 'extra.txt').exists()
            assert store.read('auth:synthetic') == {'private':'synthetic-core-secret'} and vault.get('synthetic')['private'] == 'synthetic-vault-secret'
            await client.post(f'/api/v1/data/backups/{before_restore}/restore', json={'confirmation':'RESTORE'})
            assert current().store.read('record') == {'text':'version two'} and (current().data_dir / 'extra.txt').exists()

            with patch.object(store, 'restore_modules', side_effect=sqlite3.OperationalError('synthetic write failure')):
                response = await client.post(f'/api/v1/data/backups/{original}/restore', json={'confirmation':'RESTORE'})
            assert response.status_code == 500 and current().store.read('record')['text'] == 'version two'
            assert (current().data_dir / 'note.txt').read_text() == 'file two' and (current().data_dir / 'extra.txt').exists()
            assert not list(data.glob('.restore-*'))
            with patch.object(backups, 'create', side_effect=OSError('synthetic disk full')):
                response = await client.post('/api/v1/data/clear', json={'scope':'modules','confirmation':'CLEAR'})
            assert response.status_code == 500 and current().store.read('record')['text'] == 'version two'
            assert (current().data_dir / 'note.txt').exists()

            corrupt = (await client.post('/api/v1/data/backups')).json()['backup']['id']
            (backups.root / corrupt / 'state.json').write_text('{}')
            before = manager.entries['alpha']
            response = await client.post(f'/api/v1/data/backups/{corrupt}/restore', json={'confirmation':'RESTORE'})
            assert response.status_code == 409 and manager.entries['alpha'] is before
            assert not next(item for item in (await client.get('/api/v1/data/backups')).json()['backups'] if item['id'] == corrupt)['valid']
            (backups.root / corrupt / 'state.json').write_text('[]')
            assert (await client.post(f'/api/v1/data/backups/{corrupt}/restore', json={'confirmation':'RESTORE'})).status_code == 409
            assert (await client.request('DELETE', f'/api/v1/data/backups/{corrupt}', json={'confirmation':'DELETE_BACKUP'})).status_code == 200
            for invalid in ['missing', '..', '20261017T000000Z-not-valid']:
                try:
                    backups.folder(invalid)
                except Exception as error:
                    assert error.status_code == 404
                else:
                    raise AssertionError('Invalid backup ID accepted')

            # An active request must block snapshots without losing its live store.
            entered, release = threading.Event(), threading.Event()
            alpha = manager.entries['alpha']
            @alpha.app.get('/slow')
            def slow():
                entered.set(); assert release.wait(4)
                return {'record': alpha.context.store.read('record')}
            task = asyncio.create_task(client.get('/api/v1/modules/alpha/slow'))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert alpha.runtime.snapshot()['last_error'] is None
                assert (await client.get('/api/v1/modules')).json()['modules'][0]['runtime']['active_requests'] == 1
                count = len(backups.list())
                assert (await client.post('/api/v1/data/backups')).status_code == 409
                assert (await client.post('/api/v1/data/clear', json={'scope':'modules','confirmation':'CLEAR'})).status_code == 409
                assert len(backups.list()) == count and manager.entries['alpha'] is alpha
            finally:
                release.set()
                assert (await task).status_code == 200

            response = await client.post('/api/v1/data/clear', json={'scope':'modules','confirmation':'CLEAR'})
            assert response.status_code == 200 and response.json()['backup']['reason'] == 'before_clear'
            assert current().store.read('record') is None and not (current().data_dir / 'note.txt').exists()
            saved = response.json()['backup']['id']
            assert (await client.post(f'/api/v1/data/backups/{saved}/restore', json={'confirmation':'RESTORE'})).status_code == 200
            assert current().store.read('record')['text'] == 'version two'


if __name__ == '__main__':
    (ROOT / '.codex/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.codex/tmp') as directory:
        asyncio.run(check(Path(directory)))
    print('recovery: public error IDs, runtime/worker state, module-only snapshots, rollback, busy/corrupt refusal and clear recovery passed')
