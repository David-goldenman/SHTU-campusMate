import asyncio
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('campus-map')


async def check():
    with sandbox('campus-map') as context:
        app = FastAPI()
        app.include_router(module.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
            snapshot = (await client.get('/conditions')).json()
            assert snapshot['version'] == 0 and snapshot['items'][0]['state'] == 'pending'
            base = {key: value for key, value in snapshot['items'][0].items() if key not in {'id', 'created_at', 'updated_at', 'revision'}}
            base.update(title='合成西门施工', state='confirmed', source_kind='onsite', source_title='合成现场围挡观察', note='合成测试：行人通道封闭，不写入真实数据。')

            def body(item=base, state=None):
                value = state or snapshot
                return {'version': value['version'], 'account_revision': value['account_revision'], 'item': item}

            wrong = {**base, 'source_kind': 'report'}
            assert (await client.post('/conditions', json=body(wrong))).status_code == 422
            assert (await client.post('/conditions', json=body({**base, 'source_kind': 'official', 'source_url': 'javascript:alert(1)'}))).status_code == 422
            assert (await client.post('/conditions', json=body({**base, 'scope': 'edges', 'place_id': '', 'edge_keys': ['missing-road']}))).status_code == 422
            assert (await client.post('/conditions', json=body({**base, 'scope': 'area', 'place_id': '', 'bounds': [0, 0, 1, 1]}))).status_code == 422
            stale = body()
            response = await client.post('/conditions', json=stale)
            assert response.status_code == 201, response.text
            snapshot = response.json()
            identity = snapshot['items'][-1]['id']
            assert snapshot['version'] == 1 and len(snapshot['history']) == 1
            assert (await client.post('/conditions', json=stale)).status_code == 409
            assert (await client.put('/conditions/'+identity, json=body({**base, 'state': 'pending'}))).status_code == 422
            assert (await client.put('/conditions/'+identity, json=body({**base, 'state': 'resolved'}))).status_code == 422
            snapshot = (await client.put('/conditions/'+identity, json=body({**base, 'state': 'resolved', 'note': '合成现场复核：围挡移除，行人通道恢复。'}))).json()
            assert snapshot['items'][-1]['state'] == 'resolved'
            snapshot = (await client.post('/conditions/undo', json={k: snapshot[k] for k in ('version','account_revision')})).json()
            assert snapshot['items'][-1]['state'] == 'confirmed' and snapshot['version'] == 3
            snapshot = (await client.post('/conditions/undo', json={k: snapshot[k] for k in ('version','account_revision')})).json()
            assert snapshot['items'][-1]['state'] == 'withdrawn' and not snapshot['undo_available']
            assert (await client.post('/conditions/undo', json={k: snapshot[k] for k in ('version','account_revision')})).status_code == 409
            old = body()
            context.auth.revision = 'synthetic-account-two'
            assert (await client.post('/conditions', json=old)).status_code == 409
            other = (await client.get('/conditions')).json()
            assert other['version'] == 0 and len(other['items']) == 1
            context.auth.revision = 'synthetic-account-one'
            assert (await client.get('/conditions')).json()['version'] == 4
        restored = FastAPI()
        restored.include_router(module.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(restored), base_url='http://fixture') as client:
            assert (await client.get('/conditions')).json()['version'] == 4


asyncio.run(check())
print('campus-map conditions: evidence validation, target validation, version conflicts, account isolation, undo and reload persistence passed')
