import asyncio
import os
import shutil
import subprocess
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
            places = (await client.get('/places')).json()
            assert len(places['buildings']) == 65 and len(places['elevators']) == 3
            walking = (await client.get('/walking-network')).json()
            assert walking['license'] == 'ODbL-1.0' and len(walking['ways']) > 200
            assert walking['boundary'][0] == walking['boundary'][-1]
            unavailable = (await client.get('/day?date=2026-10-21')).json()
            assert unavailable['available'] is False and unavailable['events'] == []
            assert (await client.get('/day?date=invalid')).status_code == 422
            changed = False

            async def api(name, path, **options):
                assert name == 'timetable' and path == '/schedule?week_start=2026-10-21'
                if changed:
                    context.auth.revision = 'synthetic-other-account'
                return httpx.Response(200, json={'status': 'partial', 'data': {'issues': ['合成来源不可用']}, 'calendar': {'days': [
                    {'date': '2026-10-20', 'events': [{'id': 'previous'}]},
                    {'date': '2026-10-21', 'events': [
                        {'id': 'lesson', 'event_type': 'class', 'location': '体育馆B107', 'at': '2026-10-21T18:00:00+08:00', 'status': 'scheduled', 'private_payload': 'not needed'},
                        {'id': 'deadline', 'event_type': 'deadline', 'at': '2026-10-20T16:30:00Z'},
                        {'id': 'moved-new', 'status': 'rescheduled'},
                        {'id': 'cancelled', 'status': 'cancel'}, {'id': 'leave', 'status': 'leave'}, {'id': 'moved-old', 'status': 'moved'}]}]}})

            context.api = api
            result = (await client.get('/day?date=2026-10-21')).json()
            assert result['available'] and result['status'] == 'partial'
            assert result['account_revision'] == unavailable['account_revision']
            assert [item['id'] for item in result['events']] == ['lesson', 'deadline', 'moved-new']
            assert result['events'][1]['at'] == '2026-10-20T16:30:00Z'
            assert 'private_payload' not in result['events'][0]
            assert result['issues'] == ['合成来源不可用']
            changed = True
            response = await client.get('/day?date=2026-10-21')
            assert response.status_code == 409 and 'events' not in response.json()


asyncio.run(check())
node = shutil.which('node') or shutil.which('node.exe')
script = str(Path(__file__).with_name('check_locations.mjs'))
if os.name != 'nt' and node and node.casefold().endswith('.exe') and shutil.which('wslpath'):
    script = subprocess.run(['wslpath', '-w', script], check=True, capture_output=True, text=True).stdout.strip()
subprocess.run([node, script], check=True)
print('campus-map: optional timetable, selected date, status filtering and account isolation passed')
