"""Department evidence and the public courses → timetable appearance contract."""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI

from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

courses_module = load('courses')
appearance = sys.modules[courses_module.__name__ + '.appearance']

for row in appearance.PALETTE[:-1]:
    item = {'code': 'QA100', 'sources': [{'department': row[2][0]}]}
    appearance.decorate([item], {})
    assert item['appearance']['key'] == row[0] and item['department_source'] == 'course'

examples = [{'code': 'CLPE1050', 'sources': [{'department': '上道书院'}]},
            {'code': 'CLGE1000', 'sources': [{'department': '科道书院'}]},
            {'code': 'QA101', 'sources': []},
            {'code': 'QA102', 'sources': [{'department': '人文科学研究院'}]},
            {'code': 'QA103', 'sources': [{'department': '物质科学与技术学院'}, {'department': '信息科学与技术学院'}]}]
plan = {'groups': [{'courses': [{'code': 'QA101', 'department': '数学科学研究所'}, {'code': 'QA103', 'department': '生命科学与技术学院'}]}]}
appearance.decorate(examples, plan)
assert examples[0]['appearance']['icon'] == 'person-running'
assert examples[0]['appearance']['accent'] == examples[1]['appearance']['accent'] == '#BF616A'
assert 'icon' not in examples[1]['appearance']
assert examples[2]['appearance']['key'] == 'ims' and examples[2]['department_source'] == 'study_plan'
assert examples[3]['appearance']['key'] == 'general' and examples[3]['department'] == '人文科学研究院'
assert examples[4]['appearance']['key'] == 'general' and examples[4]['department_source'] == 'unknown'


async def check():
    timetable_module = load('timetable')
    with sandbox('courses') as courses, sandbox('timetable') as timetable:
        app = FastAPI()
        app.include_router(courses_module.create_router(courses), prefix='/courses')
        app.include_router(timetable_module.create_router(timetable), prefix='/timetable')
        source = timetable_module._source
        data = validate_bundle({'courses': [course('timetable', '1', '合成课程', 'QA101', '2026-fall')],
            'timetable': [{'id': 'timetable:lesson', 'source': 'timetable', 'title': '合成课程', 'course_id': 'timetable:1', 'weeks': [1], 'weekday': 1, 'period_start': 1, 'period_end': 2}],
            'metadata': {'semester': '2026-fall'}})
        timetable.store.write('snapshot', {'owner': source.owner(), 'updated_at': datetime.now(timezone.utc).isoformat(), 'data': data})
        timetable.store.write('sync', {'owner': source.owner(), 'status': 'ready'})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
                async def api(module, path='/snapshot', **options):
                    if module in {'courses', 'timetable'}:
                        return await client.request(options.get('method', 'GET'), '/' + module + path, json=options.get('body'))
                    if module == 'eams':
                        return httpx.Response(200, json={'data': validate_bundle({'metadata': {'study_plan': plan}})})
                    return httpx.Response(404)
                courses.api = timetable.api = api
                value = (await client.get('/courses/appearance')).raise_for_status().json()
                assert len(value['palette']) == 7 and value['courses'][0]['appearance']['key'] == 'ims'
                assert value['courses'][0]['course_ids'] == ['timetable:1']
                (await client.put('/timetable/calendar-settings', json={'week_one': '2026-10-12'})).raise_for_status()
                calendar = (await client.get('/timetable/schedule?week_start=2026-10-12')).raise_for_status().json()
                event = calendar['calendar']['days'][0]['events'][0]
                assert event['appearance']['key'] == 'ims' and event['department'] == '数学科学研究所'
                assert len(calendar['palette']) == 7
                # Disabling courses leaves the timetable usable without inferred colors.
                original = timetable.api
                async def without_courses(module, path='/snapshot', **options):
                    return httpx.Response(404) if module == 'courses' else await original(module, path, **options)
                timetable.api = without_courses
                fallback = (await client.get('/timetable/schedule?week_start=2026-10-12')).json()
                assert fallback['calendar']['days'][0]['events'] and not fallback['palette']
        finally:
            timetable_module.stop(timetable)


asyncio.run(check())
print('course appearance: seven palettes, source precedence, sport icon, unknown/ambiguous evidence, public timetable integration and optional dependency passed')
