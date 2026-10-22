"""Daily-use boundaries: unavailable sources, stale records and manual deadlines."""
import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from checks.module_support import load, sandbox

package = load('assignments')
data = {
    'courses': [{'id': 'c', 'title': '合成课程', 'current': True, 'course_ids': ['blackboard:c']}],
    'assignments': [{'id': 'blackboard:a', 'title': '无日期作业', 'source': 'blackboard',
                     'course_id': 'blackboard:c', 'availability': 'open', 'submitted': False}],
    'metadata': {'source_metadata': {'blackboard': {'status': 'ready', 'updated_at': '2026-10-20T00:00:00Z'}}},
}
for status in ('cached', 'syncing', 'error', 'login_required', 'verification_required'):
    fixture = copy.deepcopy(data)
    fixture['metadata']['source_metadata']['blackboard']['status'] = status
    item = package.arrange(fixture)[0]
    assert item['source_stale'] and item['needs_review'] and item['pending']
    assert package.coverage(fixture)['status'] == 'partial'
assert package.coverage({'assignments': []})['status'] == 'unavailable'
assert package.coverage({'assignments': [], 'metadata': data['metadata']})['status'] == 'ready'
assert package.coverage({'assignments': [], 'metadata': {'source_metadata': {'blackboard': {'status': 'error'}}}})['status'] == 'unavailable'
assert package.arrange(data)[0]['due_at'] is None


async def check_api():
    with sandbox('assignments') as context:
        switched = False

        async def api(name, path='/snapshot', **kwargs):
            if switched:
                context.auth.revision = 'different-account'
            return httpx.Response(200, json={'status': 'ready', 'data': data})

        context.api = api

        def app():
            result = FastAPI()
            result.include_router(package.create_router(context))
            return result

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app()), base_url='http://fixture') as client:
            initial = (await client.get('/snapshot')).json()
            owner = initial['account_revision']
            body = {'assignment_id': 'blackboard:a', 'due_at': '2030-10-21T20:15:00+08:00', 'account_revision': owner}
            assert (await client.put('/deadline', json=body)).status_code == 200
            assert (await client.put('/deadline', json={**body, 'account_revision': 'old-account'})).status_code == 409
            assert (await client.put('/deadline', json={**body, 'due_at': '2030-10-21T20:15:00'})).status_code == 422
        # Recreate the router with the same store, as after a module reload.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app()), base_url='http://fixture') as client:
            value = (await client.get('/snapshot')).json()
            saved = value['pending'][0]
            assert saved['due_source'] == 'manual' and saved['due_at'] == body['due_at']
            assert data['assignments'][0].get('due_at') is None, 'Source records are never overwritten'
            assert (await client.put('/deadline', json={**body, 'due_at': None})).status_code == 200
            assert (await client.get('/snapshot')).json()['pending'][0]['due_at'] is None
            switched = True
            assert (await client.get('/snapshot')).status_code == 409, 'Reject an account switch while awaiting source data'


asyncio.run(check_api())
print('assignment reliability: stale/absent sources, unknown dates, persistent manual deadlines and account changes passed')
