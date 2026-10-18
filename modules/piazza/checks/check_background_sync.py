"""Accepted collection survives client disposal and exposes resumable progress."""
import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from checks.module_support import load, sandbox


async def check():
    package = load('piazza')
    entered, release = threading.Event(), threading.Event()

    class Reader:
        def __init__(self, client):
            pass

        def feed(self, course, offset):
            entered.set()
            assert release.wait(3)
            return [{'id': 'p1'}]

        def post(self, course, post):
            return {'id': 'p1', 'history': [{'subject': 'Synthetic', 'content': 'Homework'}]}

    with sandbox('piazza') as context, patch.object(package, 'Piazza', Reader):
        app = FastAPI()
        app.include_router(package.create_router(context))
        transport = httpx.ASGITransport(app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
                assert (await client.put('/courses', json={'courses': [{'id': 'c1', 'name': 'Synthetic'}]})).status_code == 200
                response = await client.post('/courses/c1/sync', json={'offset': 0})
                assert response.status_code == 202 and response.json()['status'] == 'syncing'
                assert entered.wait(1)
                assert (await client.post('/courses/c1/sync', json={'offset': 0})).status_code == 409
            # A new page/client sees the same module-owned job, not a new collection.
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
                assert (await client.get('/courses')).json()['status']['c1']['status'] == 'syncing'
                release.set()
                for _ in range(100):
                    value = (await client.get('/courses')).json()['status']['c1']
                    if value['status'] != 'syncing':
                        break
                    await asyncio.sleep(.02)
                assert value['status'] == 'ready' and value['saved'] == 1, value
                assert (await client.get('/posts?course_id=c1')).json()['total'] == 1
        finally:
            release.set()
            package.stop(context)
            assert not package._source.refresh_thread.is_alive()
    print('piazza: accepted background collection, duplicate prevention, returning-client progress and cleanup passed')


if __name__ == '__main__':
    asyncio.run(check())
