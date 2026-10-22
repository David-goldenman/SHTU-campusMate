"""Request-local read reuse must preserve lifecycle, failures and account changes."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from fastapi import FastAPI, HTTPException
from backend.core.modules import ModuleManager
from backend.core.reads import read_once, request_reads, current_batch
from backend.core.store import Store
from checks.module_support import Memory, Auth, AI


def fixture(root, name, code):
    folder = root / name
    (folder / 'server').mkdir(parents=True)
    (folder / 'module.json').write_text(json.dumps({'id':name,'name':name,'version':'1','category':'checks','api_version':1}), encoding='utf-8')
    (folder / 'server/__init__.py').write_text(code, encoding='utf-8')


async def calculation():
    context, owner, calls = object(), ['one'], 0
    gate, entered = asyncio.Event(), asyncio.Event()
    async def load():
        nonlocal calls
        calls += 1
        entered.set()
        await gate.wait()
        return {'items':[owner[0]]}
    with request_reads():
        leader = asyncio.create_task(read_once(context, 'snapshot', lambda:owner[0], load))
        await entered.wait()
        follower = asyncio.create_task(read_once(context, 'snapshot', lambda:owner[0], load))
        await asyncio.sleep(0)
        follower.cancel()
        try: await follower
        except asyncio.CancelledError: pass
        gate.set()
        first = await leader
        first['items'].append('changed')
        assert (await read_once(context, 'snapshot', lambda:owner[0], load)) == {'items':['one']}
        assert calls == 1
        owner[0] = 'two'
        assert (await read_once(context, 'snapshot', lambda:owner[0], load))['items'] == ['two']
        assert calls == 2
        with request_reads(False):
            assert current_batch() is None
        await read_once(context, 'snapshot', lambda:owner[0], load)
        assert calls == 3, 'A write invalidates earlier reads'
    assert current_batch() is None
    with request_reads():
        await read_once(context, 'snapshot', lambda:owner[0], load)
        assert calls == 4, 'No reuse across requests'
    with request_reads():
        async def changed():
            owner[0] = 'three'
            return {'items':['old']}
        try: await read_once(context, 'changed', lambda:owner[0], changed)
        except HTTPException as error: assert error.status_code == 409
        else: raise AssertionError('Changed owner must reject a stale result')
    gate.clear(); entered.clear()
    with request_reads():
        leader = asyncio.create_task(read_once(context, 'cancel', lambda:owner[0], load))
        await entered.wait()
        leader.cancel()
        try: await leader
        except asyncio.CancelledError: pass
        gate.set()
        assert (await read_once(context, 'cancel', lambda:owner[0], load))['items'] == ['three']
    # A task inherited from a finished request must not retain an active cache.
    signal = asyncio.Event()
    with request_reads():
        async def later():
            await signal.wait()
            assert current_batch() is None
        inherited = asyncio.create_task(later())
    signal.set(); await inherited


async def transport():
    temporary = ROOT / '.codex/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='read-batch-', dir=temporary) as directory:
        folder = Path(directory)
        fixture(folder/'modules', 'source', '''import asyncio
from fastapi import APIRouter, HTTPException
count = 0
fail = False
gate = None
entered = asyncio.Event()
def create_router(context):
    router = APIRouter()
    @router.get('/snapshot')
    async def snapshot():
        global count, fail
        count += 1
        entered.set()
        if gate is not None: await gate.wait()
        if fail:
            fail = False
            raise HTTPException(503, 'try again')
        return {'count':count,'owner':context.auth.revision}
    return router
''')
        fixture(folder/'modules', 'reader', '''import asyncio
from fastapi import APIRouter
def create_router(context):
    router = APIRouter()
    @router.get('/snapshot')
    async def snapshot():
        owner = context.auth.revision
        rows = await asyncio.gather(*(context.api('source', reuse_key=owner) for _ in range(4)))
        rows.append(await context.api('source', reuse_key=owner))
        return [row.json() for row in rows]
    @router.get('/plain')
    async def plain():
        return [(await context.api('source')).json() for _ in range(2)]
    @router.get('/retry')
    async def retry():
        return [(await context.api('source', reuse_key=context.auth.revision)).status_code for _ in range(2)]
    return router
''')
        store = Store(folder/'state.sqlite3')
        manager = ModuleManager(store, Memory(), Auth(lambda req:httpx.Response(200)), AI(), root=folder/'modules', data=folder/'data')
        manager.loop = asyncio.get_running_loop()
        manager.reload()
        assert all(entry.info['status']=='ready' for entry in manager.entries.values())
        app=FastAPI(); app.mount('/modules', manager)
        source=manager.entries['source'].package
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                rows=(await client.get('/modules/reader/snapshot')).json()
                assert len(rows)==5 and {row['count'] for row in rows}=={1}
                assert source.count==1
                await client.get('/modules/reader/snapshot')
                assert source.count==2
                await client.get('/modules/reader/plain')
                assert source.count==4, 'Ordinary GETs are not implicitly reusable'
                source.fail=True
                assert (await client.get('/modules/reader/retry')).json()==[503,200]
                source.gate=asyncio.Event();source.entered.clear()
                request=asyncio.create_task(client.get('/modules/reader/snapshot'))
                await source.entered.wait()
                request.cancel()
                try: await request
                except asyncio.CancelledError: pass
                try: manager.set_enabled('source', False)
                except HTTPException as error: assert error.status_code==409
                else: raise AssertionError('An in-flight reused request still owns the module')
                source.gate.set()
                for _ in range(100):
                    if not manager.entries['source'].calls and not manager.entries['source'].requests: break
                    await asyncio.sleep(.01)
                assert not manager.entries['source'].calls and not manager.entries['source'].requests
                manager.set_enabled('source',False)
                assert (await client.get('/modules/reader/retry')).json()==[404,404]
                manager.set_enabled('source',True)
                assert (await client.get('/modules/reader/retry')).json()==[200,200]
        finally:
            await asyncio.to_thread(manager.close)
            store.close()


async def main():
    await calculation()
    await transport()
    print('read batches: concurrent reuse, independent results, failed reads, account changes, writes, cancellation, disable/re-enable and request cleanup passed')

asyncio.run(main())
