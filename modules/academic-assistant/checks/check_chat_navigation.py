"""Conversation navigation must not wait for an old model process to exit."""
import asyncio
import sys
import threading
from pathlib import Path

import httpx
from fastapi import FastAPI
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

package = load('academic-assistant')
BASE = '/api/v1/modules/academic-assistant'


async def check(cancel):
    with sandbox('academic-assistant') as context:
        started, release, cancelled = threading.Event(), threading.Event(), threading.Event()
        app = FastAPI()
        router = package.create_router(context)
        app.include_router(router, prefix=BASE)

        def run(plugin_env, cancel_event, **kwargs):
            task = package._agent.tasks[plugin_env['CAMPUS_PLUGIN_STUDY_TOKEN']]
            task.answer = {'text': '合成回答', 'citations': []}
            started.set()
            if cancel:
                assert cancel_event.wait(5)
                cancelled.set()
            assert release.wait(5), 'Synthetic runtime must be released by the check'
            return {'content': '合成回答', 'model': 'synthetic', 'tools': []}

        context.ai.run = run
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            empty = (await client.get(BASE + '/chat')).json()
            assert empty['owner'] and empty['messages'] == [] and empty['conversation_id'] is None
            first = (await client.post(BASE + '/conversations')).json()['id']
            request = Request({'type': 'http', 'scheme': 'http', 'server': ('test', 80), 'path': BASE + '/chat/stream', 'headers': []})
            endpoint = next(route.endpoint for route in router.routes if route.path == '/chat/stream')
            stream = await endpoint(package.Chat(message='合成慢初始化', conversation_id=first), request)
            await anext(stream.body_iterator)
            assert await asyncio.to_thread(started.wait, 2)
            closing = asyncio.create_task(stream.body_iterator.aclose()) if cancel else None
            try:
                if cancel:
                    assert await asyncio.to_thread(cancelled.wait, 2)
                second = (await asyncio.wait_for(client.post(BASE + '/conversations'), 1)).json()['id']
                selected = await asyncio.wait_for(client.post(BASE + '/conversations/' + first + '/select'), 1)
                assert selected.status_code == 200 and selected.json()['messages'] == []
                await asyncio.wait_for(client.post(BASE + '/conversations/' + second + '/select'), 1)
            finally:
                release.set()
                if closing:
                    await closing
                else:
                    async for _ in stream.body_iterator:
                        pass
            assert not package._agent.tasks
            assert package._agent.conversations.index()['active_id'] == second, 'Old replies must not replace the user selection'
            assert len(package._agent.conversations.messages(first)) == (0 if cancel else 2)
            context.auth.revision = 'another-synthetic-account'
            changed = (await client.get(BASE + '/chat')).json()
            assert changed['owner'] != empty['owner'] and changed['messages'] == [] and changed['conversation_id'] is None


asyncio.run(check(True))
asyncio.run(check(False))
print('chat navigation: create/select during slow cancellation, no partial history, and selection preserved after old replies passed')
