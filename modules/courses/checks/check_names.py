"""Existing Chinese source names win; identities stay independent of group facts."""
import asyncio
import copy
import sys
from itertools import permutations
from pathlib import Path

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

module = load('courses')
catalog = sys.modules[module.__name__ + '.catalog']
rows = [course('gradescope', '1', 'Electromagnetics', 'EE130', '2026-fall'),
        course('blackboard', '2', '电磁学-2026秋', 'EE130', '2026-fall'),
        course('elrc', '3', '电磁学', 'EE130', '2026-fall'),
        course('ecourse', '4', '电磁学', 'EE130', '2026-fall')]
original = copy.deepcopy(rows)
for ordered in permutations(rows):
    snapshots = {row['source']: {'data': validate_bundle({'courses': [row]})} for row in ordered}
    data = catalog.combine(snapshots, [], '2026-fall')
    value = data['courses'][0]
    assert value['title'] == '电磁学' and value['title_source'] == 'elrc'
    assert set(value['aliases']) == {'Electromagnetics', '电磁学', '电磁学-2026秋'}
    assert catalog.query(data, 'courses', q='electromagnetics')[0]['id'] == value['id']
assert rows == original
snapshots['timetable'] = {'data': validate_bundle({'courses': [course('timetable', '5', '电磁学（教务）', 'EE130', '2026-fall')]})}
assert catalog.combine(snapshots, [], '2026-fall')['courses'][0]['title_source'] == 'timetable'
manual = catalog.combine(snapshots, [{'id': 'mine', 'title': 'My chosen name', 'course_ids': [row['id'] for row in rows] + ['timetable:5']}], '2026-fall')['courses'][0]
assert manual['title'] == 'My chosen name' and manual['title_source'] == 'manual'


async def check():
    with sandbox('courses') as context:
        calls = []
        async def api(name, path='/snapshot', **kwargs):
            calls.append(name)
            return httpx.Response(200, json={'status': 'ready', 'data': validate_bundle({'courses': [
                course('timetable', 'now', '本学期', 'QA100', '2026-fall'),
                course('timetable', 'old', '以前学期', 'QA200', '2025-fall')], 'metadata': {'semester': '2026-fall'}})}) if name == 'timetable' else httpx.Response(404)
        context.api = api
        app = FastAPI(); app.include_router(module.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
            value = (await client.get('/identities')).json()
            assert len(value['items']) == 1 and value['items'][0]['title'] == '本学期'
            assert value['current_semester'] == '2026-fall' and value['account_revision']
            assert not {'mail', 'group-messages', 'eams'} & set(calls), calls
            assert len((await client.get('/identities?current=false')).json()['items']) == 2


asyncio.run(check())
print('PASS: Chinese source priority, aliases, manual title preservation and current identity API without group callbacks')
