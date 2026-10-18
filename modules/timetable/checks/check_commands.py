"""Exercise the same schedule-read / class-adjustment path used by the page."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
from backend.services.campus.data import validate_bundle

module = load('timetable')


async def check():
    with sandbox('timetable') as context:
        style = {'course_ids': ['timetable:course'], 'department': '合成院系',
                 'appearance': {'accent': '#5E81AC', 'tint': '#ECEFF4', 'ink': '#2E3440'}}
        appearance_enabled = True

        async def api(name, path='/snapshot', **options):
            if name == 'courses' and path == '/appearance' and appearance_enabled:
                return httpx.Response(200, json={'courses': [style], 'palette': []})
            return httpx.Response(404)

        context.api = api
        app = FastAPI()
        app.include_router(module.create_router(context))
        source = module._source
        data = validate_bundle({'metadata': {'semester': '2026-2027学年秋季', 'semester_id': '91'},
                                'timetable': [{'id': 'timetable:lesson', 'course_id': 'timetable:course',
                                               'source': 'timetable', 'title': '合成课程', 'weekday': 2,
                                               'weeks': [1, 2], 'period_start': 3, 'period_end': 4, 'location': '教室 A'}]})
        context.store.write('snapshot', {'owner': source.owner(), 'data': data, 'updated_at': datetime.now(timezone.utc).isoformat()})
        context.store.write('sync', {'owner': source.owner(), 'status': 'ready'})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
                assert (await client.put('/calendar-settings', json={'week_one': '2026-10-19'})).status_code == 200

                async def read_class():
                    response = await client.get('/schedule?week_start=2026-10-19')
                    assert response.status_code == 200, response.text
                    schedule = response.json()
                    event = next(item for day in schedule['calendar']['days'] for item in day['events']
                                 if item['id'] == 'timetable:lesson:2026-10-20')
                    return schedule, event

                def command(schedule, event, action, **fields):
                    return {'action': 'adjust_class', 'account_revision': schedule['account_revision'],
                            'request_id': str(uuid4()), 'record_id': event['id'], 'expected_revision': event['revision'],
                            'adjustment': {'lesson_id': event['lesson_id'], 'on_date': event['original_date'],
                                           'action': action, **fields}}

                for action, status in [('leave', 'leave'), ('restore', 'scheduled'), ('cancel', 'cancel'), ('restore', 'scheduled')]:
                    schedule, event = await read_class()
                    assert event['department'] == style['department'] and event['appearance'] == style['appearance']
                    body = command(schedule, event, action)
                    if action == 'cancel':
                        # Display changes while a dialog is open must not invalidate its course version.
                        style.update(department='另一合成院系', appearance={'accent': '#A3BE8C', 'tint': '#ECEFF4', 'ink': '#2E3440'})
                    response = await client.post('/commands', json=body)
                    assert response.status_code == 200, response.text
                    assert response.json()['applied'] and response.json()['affected_count'] == 1
                    assert (await read_class())[1]['status'] == status
                    replay = await client.post('/commands', json=body)
                    assert replay.status_code == 200 and replay.json()['already_applied']
                    stale = await client.post('/commands', json={**body, 'request_id': str(uuid4())})
                    assert stale.status_code == 409, 'A prior course adjustment must still invalidate an old dialog'

                schedule, event = await read_class()
                appearance_enabled = False
                moved = await client.post('/commands', json=command(schedule, event, 'move', to_date='2026-10-27', location='教室 B'))
                assert moved.status_code == 200, moved.text
                target = (await client.get('/schedule?week_start=2026-10-26')).json()
                moved_event = next(item for day in target['calendar']['days'] for item in day['events']
                                   if item['id'] == 'timetable:lesson:2026-10-20:moved')
                assert moved_event['location'] == '教室 B' and moved_event['status'] == 'rescheduled'
                appearance_enabled = True
                restored = await client.post('/commands', json=command(target, moved_event, 'restore'))
                assert restored.status_code == 200, restored.text
                schedule, event = await read_class()
                assert event['status'] == 'scheduled' and event['location'] == '教室 A'
                stale_body = command(schedule, event, 'cancel')
                saved = context.store.read('snapshot')
                saved['data']['timetable'][0]['location'] = '教室 C'
                context.store.write('snapshot', saved)
                assert (await client.post('/commands', json=stale_body)).status_code == 409
                schedule, event = await read_class()
                assert event['status'] == 'scheduled' and event['location'] == '教室 C'
                fresh = await client.post('/commands', json=command(schedule, event, 'leave'))
                assert fresh.status_code == 200, fresh.text
        finally:
            module.stop(context)


asyncio.run(check())
print('timetable commands: styled course adjustments, display changes, cross-week restore, replay and stale-edit protection passed')
