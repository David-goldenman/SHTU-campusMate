"""Synthetic faults must remain local and never release still-running resources."""
import asyncio
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from backend.core.store import Store
from backend.main import create_app
from checks.check_framework import MemoryVault, fixture


async def check(root):
    modules, data = root / 'modules', root / 'data'
    modules.mkdir(); data.mkdir()
    fixture(modules, 'alpha', 'one'); fixture(modules, 'beta', 'two')
    app = create_app(active_port=17668, store=Store(data / 'state.sqlite3'), vault=MemoryVault(), modules_root=modules, data_dir=data)
    manager = app.state.modules
    manager.stop_timeout = .05
    manager.api_timeout = .05
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17668') as client:
            client.headers['X-Framework-Token'] = (await client.get('/api/v1/bootstrap')).json()['csrf_token']
            alpha = manager.entries['alpha']
            stop = alpha.package.stop
            alpha.context.store.write('preserve', 'synthetic original data')

            def failed(context):
                raise RuntimeError('synthetic stop failure')

            alpha.package.stop = failed
            refreshed = await client.post('/api/v1/modules/reload')
            assert refreshed.status_code == 200 and refreshed.json()['warnings']
            assert alpha.info['status'] == 'error' and alpha.context is not None
            assert (await client.get('/api/v1/modules/beta/state')).status_code == 200
            assert (await client.post('/api/v1/data/clear', json={'scope':'modules', 'confirmation':'CLEAR'})).status_code == 409
            assert alpha.context.store.read('preserve') == 'synthetic original data'
            assert (await client.get('/api/v1/modules/beta/state')).status_code == 200
            alpha.package.stop = stop
            await client.post('/api/v1/modules/reload')

            alpha = manager.entries['alpha']
            entered, release = threading.Event(), threading.Event()
            stops = []

            def delayed(context):
                stops.append(True); entered.set()
                assert release.wait(3)
                context.store.write('finished', True)

            alpha.package.stop = delayed
            try:
                response = await asyncio.wait_for(client.post('/api/v1/modules/reload'), 1)
                assert response.status_code == 200 and entered.is_set()
                pending = alpha.stopping
                assert alpha.info['status'] == 'error' and not pending.done()
                assert alpha.context.store.read('preserve') == 'synthetic original data'
                await client.post('/api/v1/modules/reload')
                assert alpha.stopping is pending and len(stops) == 1
                assert (await client.get('/api/v1/modules/beta/state')).status_code == 200
            finally:
                release.set()
                await asyncio.to_thread(pending.result, 2)
            assert alpha.context is None
            await client.post('/api/v1/modules/reload')
            assert manager.entries['alpha'].context.store.read('finished') is True

            alpha = manager.entries['alpha']
            entered, release = threading.Event(), threading.Event()

            @alpha.app.get('/slow')
            def slow():
                entered.set()
                assert release.wait(4)
                # This must stay open even after the caller times out or cancels.
                return {'value': alpha.context.store.read('preserve')}

            try:
                response = await manager.call_api('alpha', '/slow')
                assert response.status_code == 504 and entered.is_set()
                assert alpha.calls and alpha.requests
                first_revision = alpha.info['revision']
                result = (await client.post('/api/v1/modules/reload')).json()
                assert result['warnings'] and manager.entries['alpha'] is alpha
                assert alpha.info['revision'] == first_revision
                assert (await client.get('/api/v1/modules/beta/state')).status_code == 200
                assert (await client.put('/api/v1/modules/alpha', json={'enabled':False})).status_code == 409
                # A short-lived worker event loop must not cancel work on the host loop.
                result = await asyncio.to_thread(lambda: asyncio.run(manager.call_api('alpha', '/slow')))
                assert result.status_code == 504 and len(alpha.calls) == 2
                for _ in range(6):
                    assert (await manager.call_api('alpha', '/slow')).status_code == 504
                assert len(alpha.calls) == 8
                assert (await manager.call_api('alpha', '/slow')).status_code == 503
            finally:
                release.set()
                for _ in range(200):
                    if not alpha.calls and not alpha.requests:
                        break
                    await asyncio.sleep(.01)
            assert not alpha.calls and not alpha.requests
            await client.post('/api/v1/modules/reload')
            assert manager.entries['alpha'].info['status'] == 'ready'
    print('resilience: failed/blocked cleanup isolated, safe recovery, cache preserved, bounded cross-module waits and retained in-flight resources passed')


temporary = ROOT / '.codex' / 'tmp'
temporary.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='resilience-', dir=temporary) as folder:
    asyncio.run(check(Path(folder)))
