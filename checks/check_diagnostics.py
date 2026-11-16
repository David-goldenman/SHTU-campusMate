"""Correlated failures and source freshness, using synthetic local data only."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx

from backend.core.runtime import RuntimeStatus
from backend.core.store import Store
from backend.main import create_app
from backend.services.campus.source import Source
from checks.check_framework import MemoryVault


def module(root, name, source):
    folder = root / name
    (folder / 'server').mkdir(parents=True)
    (folder / 'module.json').write_text(json.dumps({
        'id': name, 'name': name, 'version': '1', 'category': 'checks', 'api_version': 1,
    }), encoding='utf-8')
    (folder / 'server' / '__init__.py').write_text(source, encoding='utf-8')


async def correlation(directory):
    modules, data = directory / 'modules', directory / 'data'
    data.mkdir()
    module(modules, 'child', '''from fastapi import APIRouter
def create_router(context):
    router = APIRouter()
    @router.get('/snapshot')
    def snapshot():
        raise RuntimeError('synthetic-secret-cookie-and-private-body')
    return router
''')
    module(modules, 'parent', '''from fastapi import APIRouter
def create_router(context):
    router = APIRouter()
    @router.get('/snapshot')
    async def snapshot():
        response = await context.api('child')
        missing = await context.api('disabled')
        return {'partial': True, 'failure': response.json(), 'missing': missing.json()}
    return router
''')
    store = Store(data / 'settings.sqlite3')
    app = create_app(active_port=17666, store=store, vault=MemoryVault(), modules_root=modules, data_dir=data)
    app.state.auth.browser = SimpleNamespace(close_all=lambda: None)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17666') as client:
            response = await client.get('/api/v1/modules/parent/snapshot', headers={'X-Operation-ID': 'user-supplied-identifier'})
            assert response.status_code == 200
            failure, missing = response.json()['failure'], response.json()['missing']
            operation = response.headers.get('x-operation-id')
            assert operation and operation != 'user-supplied-identifier', 'The server must issue its own operation ID'
            assert failure['operation_id'] == missing['operation_id'] == operation, 'Nested and unavailable calls share the parent operation'
            assert failure['component'] == 'child' and failure['phase'] == 'request'
            assert missing['component'] == 'disabled' and missing['code'] == 'module_unavailable'
            assert failure['request_id'] != operation, 'Failure IDs remain distinct from operation correlation'
            assert 'synthetic-secret-cookie-and-private-body' not in response.text
            child = next(row for row in app.state.modules.list()['modules'] if row['id'] == 'child')
            assert child['runtime']['last_error']['operation_id'] == operation
            parent = next(row for row in app.state.modules.list()['modules'] if row['id'] == 'parent')
            assert parent['runtime']['last_request'].get('operation_id') == operation, 'Successful aggregation retains the same diagnostic operation'
            second = await client.get('/api/v1/modules/parent/snapshot')
            assert second.headers['x-operation-id'] != operation, 'Independent operations must not reuse context'


def source_outcomes(directory):
    store = Store(directory / 'source.sqlite3')
    runtime = RuntimeStatus()
    auth = SimpleNamespace(get_account_revision=lambda _: 'synthetic-account',
                           read_with_recovery=lambda _, read, **kwargs: read(None))
    context = SimpleNamespace(id='synthetic-source', store=store, runtime=runtime, auth=auth)
    fail = True

    def fetch(*_):
        if fail:
            raise ValueError('synthetic-private-source-body')
        return {}

    source = Source(context, 'ids', [], fetch, stale_after=None)
    cached_at = '2026-10-20T12:00:00+00:00'
    try:
        store.write('snapshot', {'owner': source.owner(), 'data': source.snapshot()['data'], 'updated_at': cached_at})
        store.write('sync', {'owner': source.owner(), 'status': 'ready', 'last_success_at': cached_at})
        source.run()
        runtime.record(200, .001)
        result = runtime.snapshot()
        assert result['last_success_at'], 'HTTP success remains available for compatibility'
        sync = result.get('sources', {}).get('sync')
        assert sync and sync['status'] == 'error', 'A successful status poll must not hide a failed synchronization'
        assert sync['code'] == 'source_parse_error' and sync['phase'] == 'sync'
        assert sync['cached_at'] == sync['last_success_at'] == cached_at
        assert sync['request_id'] and sync['operation_id']
        snapshot = source.snapshot()
        assert snapshot['status'] == 'error' and snapshot['updated_at'] == cached_at
        assert snapshot['diagnostic']['operation_id'] == sync['operation_id']
        assert 'synthetic-private-source-body' not in json.dumps(result)
        assert 'synthetic-private-source-body' not in json.dumps(snapshot)
        fail = False
        source.run()
        recovered = runtime.snapshot()['sources']['sync']
        assert recovered['status'] == 'ready' and recovered['last_success_at'] != cached_at
        assert recovered.get('code') is None and recovered.get('request_id') is None
    finally:
        source.close()
        store.close()


def interrupted_sync(directory):
    store = Store(directory / 'interrupted.sqlite3')
    runtime = RuntimeStatus()
    context = SimpleNamespace(id='interrupted-source', store=store, runtime=runtime,
                              auth=SimpleNamespace(get_account_revision=lambda _: 'synthetic-account'))
    previous = Source(context, 'ids', [], lambda *_: {}, stale_after=None)
    owner = previous.owner()
    previous.close()
    store.write('sync', {'status': 'syncing', 'owner': owner})
    reopened = Source(context, 'ids', [], lambda *_: {}, stale_after=None)
    try:
        assert reopened.snapshot()['status'] == 'error'
        result = runtime.snapshot()['sources']['sync']
        assert result['status'] == 'error', 'An interrupted task cannot still be shown as running after restart'
        assert result['code'] == 'source_interrupted'
    finally:
        reopened.close()
        store.close()


def main():
    root = PROJECT / '.codex' / 'tmp'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='diagnostics-', dir=root) as temporary:
        directory = Path(temporary)
        asyncio.run(correlation(directory))
        source_outcomes(directory)
        interrupted_sync(directory)
    print('diagnostics: nested correlation, unavailable dependencies, safe errors and distinct sync freshness passed')


if __name__ == '__main__':
    main()
