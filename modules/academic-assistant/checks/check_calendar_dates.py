"""Unknown semester dates stay unknown through the calendar and AI public APIs."""
import asyncio
import copy
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
from backend.services.campus.analysis import account_revision
from backend.services.campus.data import validate_bundle

study, timetable = load('academic-assistant'), load('timetable')


async def check():
    # Each case deliberately selects a different past/future semester. Keep the
    # semester clock aligned with that fixture; rollover fetching has its own check.
    with sandbox('timetable') as context, sandbox('academic-assistant') as study_context, patch.object(
            sys.modules[timetable.__name__ + '.persistence'], 'expected_semester',
            side_effect=lambda *_: timetable.term_key(snapshot['data']['metadata'])):
        async def sources(name, path='/snapshot', **kwargs):
            return httpx.Response(200, json={'status': 'ready', 'updated_at': datetime.now(timezone.utc).isoformat(), 'data': validate_bundle({})})
        context.api = sources
        app = FastAPI()
        app.include_router(timetable.create_router(context))
        source = timetable._source
        snapshot = {'owner': source.owner(), 'updated_at': datetime.now(timezone.utc).isoformat(), 'data': validate_bundle({
            'metadata': {'semester': '2026-2027学年春季', 'semester_id': 'spring', 'units': 13},
            'timetable': [{'id': 'timetable:synthetic', 'source': 'timetable', 'title': '合成课程',
                           'weekday': 1, 'period_start': 1, 'period_end': 2, 'weeks': [1, 2]}]})}
        context.store.write('snapshot', snapshot)
        context.store.write('sync', {'owner': source.owner(), 'status': 'ready'})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
                async def api(name, path='/snapshot', **kwargs):
                    assert name == 'timetable'
                    return await client.get(path)
                study_context.api = api

                async def query(week):
                    task = study.Task(study_context, '查看本周课表')
                    return await task.query(study.Query(area='timetable', week_start=date.fromisoformat(week)))

                for semester in ('2025-2026学年秋季', '2025-2026学年春季', '2026-2027学年春季', '2026-2027学年夏季', 'Unknown term'):
                    snapshot['data']['metadata']['semester'] = semester
                    context.store.write('snapshot', snapshot)
                    settings = (await client.get('/calendar-settings')).json()
                    assert settings['week_one'] is None and settings['source'] is None, 'A semester name must not invent a start date'
                snapshot['data']['metadata']['semester'] = '2026-2027学年春季'
                context.store.write('snapshot', snapshot)
                raw = copy.deepcopy(snapshot)
                schedule = (await client.get('/schedule?week_start=2027-02-08')).json()
                assert schedule['status'] == 'partial' and schedule['data']['issues']
                assert schedule['calendar']['teaching_week'] is None
                assert not any(day['events'] for day in schedule['calendar']['days'])
                assert not schedule['calendar']['conflicts']['complete']
                unknown = await query('2027-02-08')
                assert not unknown['items'] and unknown['issues']
                assert unknown['week_one'] is None and unknown['week_one_source'] is None
                assert unknown['teaching_week'] is None and not unknown['conflicts']['complete']

                # Known personal dates remain usable, but missing courses prevent an all-clear.
                created = await client.post('/commands', json={'action': 'create', 'request_id': uuid4().hex,
                    'account_revision': account_revision(context), 'event': {'title': '合成学习安排', 'event_type': 'study',
                    'starts_at': '2027-02-08T15:00:00+08:00', 'ends_at': '2027-02-08T16:00:00+08:00'}})
                assert created.status_code == 200 and not created.json()['conflicts']['complete']
                unknown = await query('2027-02-08')
                assert len(unknown['items']) == 1 and '合成学习安排' in unknown['items'][0]['text'] and unknown['issues']

                official = {'terms': {'2026-spring': {'week_one': '2027-02-15', 'closures': []}}}
                context.store.write('school-calendar:2026', official)
                known = await query('2027-02-15')
                assert known['week_one'] == '2027-02-15' and known['week_one_source'] == 'school' and known['teaching_week'] == 1
                assert any('合成课程' in row['text'] for row in known['items']) and not known['issues']
                # A failed refresh must retain the last recognized school date.
                context.store.write('school-calendar:2026', {**official, 'error': '合成校历读取失败，已保留缓存。'})
                cached = await query('2027-02-15')
                assert cached['week_one'] == '2027-02-15' and cached['week_one_source'] == 'school' and cached['issues']

                assert (await client.put('/calendar-settings', json={'week_one': '2027-02-22'})).status_code == 200
                manual = await query('2027-02-22')
                assert manual['week_one'] == '2027-02-22' and manual['week_one_source'] == 'manual' and manual['teaching_week'] == 1
                assert (await client.delete('/calendar-settings')).json()['source'] == 'school'
                context.store.delete('school-calendar:2026')
                assert (await query('2027-02-15'))['week_one_source'] is None
                assert context.store.read('snapshot') == raw, 'Reading dates must preserve source data'
                assert len(context.store.read('events:' + source.owner())) == 1
        finally:
            timetable.stop(context)


asyncio.run(check())
print('PASS: unknown dates, AI provenance, cached/manual dates, personal events and incomplete conflict checks')
