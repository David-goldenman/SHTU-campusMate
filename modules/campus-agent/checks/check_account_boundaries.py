import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import HTTPException
from backend.services.campus.analysis import account_revision
from checks.module_support import load, sandbox

package = load('campus-agent')
service = sys.modules[package.__name__ + '.service']


def check_boundary(boundary, cancel=False):
    with sandbox('campus-agent') as context:
        agent = service.CampusAgent(context)
        agent.origin = 'http://127.0.0.1:17668/api/v1/modules/campus-agent'
        owner = account_revision(context)
        context.store.write('state:' + owner, {'summary': 'Account A private summary'})
        context.auth.revision = 'synthetic-account-B'
        other_key = agent.key('state')
        other_state = {'summary': 'Account B existing summary', 'pending': ['mail:B']}
        context.store.write(other_key, other_state)
        context.auth.revision = 'synthetic-account-one'
        writes, calls, crossed = [], [], []
        write = context.store.write
        def record_write(key, value):
            writes.append(key)
            write(key, value)
        context.store.write = record_write
        def change():
            crossed.append(len(writes))
            if cancel:
                agent.cancelled.set()
            else:
                context.auth.revision = 'synthetic-account-B'
        message = {'id': 'mail:A', 'title': 'Account A notice', 'classification': {}}
        if boundary == 'reviews':
            message['classification'] = {'fingerprint': 'existing-review'}
        async def collect():
            if boundary == 'collect':
                change()
            return ({'mail': {'id': 'mail', 'name': 'Mail', 'reads': []}},
                    {'mail': {'status': 'ready', 'data': {'messages': [message]}}},
                    {'messages': [message], 'preferences': {'requirements': 'Account A private preference'}})
        async def api(module, path='/snapshot', **kwargs):
            if module == 'notifications':
                if boundary == 'notifications':
                    change()
                return httpx.Response(200, json={'items': []})
            assert module == 'mail' and path == '/intelligence'
            assert boundary == 'reviews'
            change()
            return httpx.Response(200, json={'messages': [], 'preferences': {}})
        def ai_run(**kwargs):
            calls.append(kwargs)
            if boundary == 'model_result':
                change()
            return {'tools': []}
        to_thread = asyncio.to_thread
        async def queued(function, *args, **kwargs):
            if boundary == 'model_queue':
                change()
            return await to_thread(function, *args, **kwargs)
        agent.collect, context.api, context.ai.run = collect, api, ai_run
        with patch.object(service.asyncio, 'to_thread', queued):
            try:
                asyncio.run(agent.check())
            except HTTPException as error:
                assert error.status_code == 409
        assert crossed, boundary
        assert context.store.read(other_key) == other_state, (boundary, 'another account was overwritten')
        assert len(writes) == crossed[0], (boundary, 'stale task wrote state after the boundary')
        assert len(calls) == (1 if boundary == 'model_result' else 0), (boundary, 'stale task started AI')
        assert agent.jobs == {}, 'Task tokens must be released after account changes or cancellation'


for boundary in ('collect', 'notifications', 'reviews', 'model_queue', 'model_result'):
    check_boundary(boundary)
    check_boundary(boundary, cancel=True)
print('campus agent: account changes and cancellation stop state writes and AI at async boundaries')
