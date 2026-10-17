import asyncio
import copy
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
from backend.services.campus import SourceError
from backend.services.campus.data import validate_bundle

module = load("timetable")
reader = module.fetch.__globals__
weeks, parse = reader["weeks"], reader["parse"]
assert weeks("0" * 49 + "1100", 2026, 50, 1, 10) == [1, 2]
assert weeks("01" + "0" * 51, 2026, 50, 1, 10) == [5]
mask = "011" + "0" * 50
html = f'''<tr><td>CS100</td><td><a class="cs-detail-link" data-course-id="7">合成课程</a></td></tr><script>
var table = new CourseTable(2026,91); var unitCount=13;
var teachers=[{{name:"合成教师"}}];
activity = new TaskActivity(t.join(','), names.join(','), "7(CS100)", "合成课程,实验", "1", "测试教室", "{mask}", null);
index=1*unitCount+4; index=1*unitCount+5; index=1*unitCount+8;
table.marshalTable(2,1,18);</script>'''
result = parse(html, "2026-2027学年秋季")
assert len(result["timetable"]) == 2
item = result["timetable"][0]
assert (item["weekday"], item["period_start"], item["period_end"], item["weeks"], item["teacher"]) == (2, 5, 6, [1, 2], "合成教师")
clock_html = html + '<table><tr><td>第一节<br>8:15 - 9:00</td><td id="TD0_0"></td></tr></table>'
assert parse(clock_html, '合成学期')['metadata']['periods'] == [{'period': 1, 'start': '08:15', 'end': '09:00'}]
partial_clock = html + '''<table>
<tr><td>第一节（未公布时间）</td><td id="TD0_0"></td></tr>
<tr><th>第二节 9：10 - 9：55</th><td id="TD0_1"></td></tr>
<tr><td>第三节 25:00 - 26:00</td><td id="TD0_2"></td></tr>
<tr><td>第四节 11:10 - 11:55</td><td id="TD0_3"></td></tr></table>'''
assert parse(partial_clock, '合成学期')['metadata']['periods'] == [
    {'period': 2, 'start': '09:10', 'end': '09:55'}, {'period': 4, 'start': '11:10', 'end': '11:55'}]
assert parse('<table><tr><td>' + partial_clock + '</td></tr></table>', '合成学期')['metadata']['periods'] == parse(partial_clock, '合成学期')['metadata']['periods']
calendar_parser = module.SchoolCalendar.refresh.__globals__['parse']
official_terms = calendar_parser('秋 学 期 （2026．9．14—2027．1．17）10月28日校运动会，全校停课。春学期（2027.2.15-2027.6.20）暑学期（2027.6.21-2027.7.18）')
assert official_terms['2026-fall']['week_one'] == '2026-09-14'
assert official_terms['2026-fall']['closures'] == [{'date': '2026-10-28', 'title': '校运动会（全校停课）'}]
assert official_terms['2026-spring']['week_one'] == '2027-02-15'
from datetime import date
legacy = {'metadata': {'units': 13}, 'timetable': [
    {**item, 'id': 'a-evening', 'period_start': 10, 'period_end': 11},
    {**item, 'id': 'z-morning', 'period_start': 3, 'period_end': 4},
    {**item, 'id': 'b-afternoon', 'period_start': 7, 'period_end': 8}], 'events': [
        {'id': 'earlier', 'event_type': 'activity', 'at': '2026-10-20T09:00:00+09:00'},
        {'id': 'later', 'event_type': 'activity', 'at': '2026-10-20T08:30:00+08:00'}]}
original = copy.deepcopy(legacy)
legacy_week = module.calendar(legacy, date(2026, 10, 19), '2026-10-19')
assert [row['period'] for row in legacy_week['periods']] == list(range(1, 14))
assert all(row['start'] is None and row['end'] is None for row in legacy_week['periods'])
assert [row['id'].split(':')[0] for row in legacy_week['days'][1]['events']] == ['z-morning', 'b-afternoon', 'a-evening', 'earlier', 'later']
assert all(row['at'] is None for row in legacy_week['days'][1]['events'][:3])
assert legacy == original, 'Reading a legacy snapshot must not overwrite saved data'
legacy['metadata']['periods'] = [{'period': 3, 'start': '10:15', 'end': '11:00'}, {'period': 4, 'start': '11:10', 'end': '11:55'}]
recovered = module.calendar(legacy, date(2026, 10, 19), '2026-10-19')['days'][1]['events']
assert recovered[0]['at'] == '2026-10-20T10:15:00+08:00' and recovered[0]['ends_at'] == '2026-10-20T11:55:00+08:00'
assert recovered[1]['at'] is None, 'Missing period clocks must not use another lesson clock'
legacy['metadata']['periods'] = []
assert module.calendar(legacy, date(2026, 10, 19), '2026-10-19')['periods'] == legacy_week['periods']
node = shutil.which('node') or shutil.which('node.exe')
planner = str(Path(__file__).with_name('check_planner.mjs'))
if os.name != 'nt' and node and node.casefold().endswith('.exe') and shutil.which('wslpath'):
    planner = subprocess.run(['wslpath', '-w', planner], check=True, capture_output=True, text=True).stdout.strip()
subprocess.run([node, planner], check=True)
dated = {'metadata': {'periods': [{'period': 5, 'start': '13:00', 'end': '13:45'}, {'period': 6, 'start': '13:50', 'end': '14:35'}]},
         'timetable': [{**item, 'weekday': 3, 'weeks': [7]}], 'events': []}
open_day = module.calendar(dated, date(2026, 10, 26), '2026-09-14')['days'][2]
assert open_day['events'][0]['at'] == '2026-10-28T13:00:00+08:00'
assert open_day['events'][0]['ends_at'] == '2026-10-28T14:35:00+08:00'
dated['events'] = [{'id': 'calendar:closure', 'source': 'calendar', 'date': '2026-10-28', 'at': '2026-10-28T00:00:00+08:00'}]
assert all(event.get('event_type') != 'class' for event in module.calendar(dated, date(2026, 10, 26), '2026-09-14')['days'][2]['events'])
# A room change across weeks must not duplicate the card inside one week.
split = {'metadata': {'periods': []}, 'events': [], 'timetable': [
    {**item, 'id': 'first-room', 'weekday': 2, 'weeks': [1, 2], 'location': 'A'},
    {**item, 'id': 'second-room', 'weekday': 2, 'weeks': [3], 'location': 'B'}]}
assert [event['location'] for event in module.calendar(split, date(2026, 9, 14), '2026-09-14')['days'][1]['events']] == ['A']
assert [event['location'] for event in module.calendar(split, date(2026, 9, 28), '2026-09-14')['days'][1]['events']] == ['B']
homework = module.homework_window({
    'blackboard': {'data': {'courses': [{'id': 'blackboard:course', 'title': '合成课程'}], 'assignments': [
        {'id': 'blackboard:late', 'title': '上周迟交', 'course_id': 'blackboard:course', 'submitted': False, 'availability': 'open', 'due_at': '2026-10-08T23:59:00+08:00'},
        {'id': 'blackboard:current', 'title': '本周迟交', 'course_id': 'blackboard:course', 'submitted': False, 'availability': 'open', 'due_at': '2026-10-15T23:59:00+08:00'},
        {'id': 'blackboard:pending', 'title': '下周待交', 'course_id': 'blackboard:course', 'submitted': False, 'availability': 'open', 'due_at': '2026-10-22T23:59:00+08:00'},
        {'id': 'blackboard:ended', 'title': '已结束', 'course_id': 'blackboard:course', 'submitted': False, 'availability': 'closed', 'due_at': '2026-10-15T23:59:00+08:00'},
        {'id': 'blackboard:future', 'title': '窗口外', 'course_id': 'blackboard:course', 'submitted': False, 'availability': 'open', 'due_at': '2026-11-20T23:59:00+08:00'}]}},
    'gradescope': {'data': {'courses': [], 'assignments': [
        {'id': 'gradescope:pending', 'title': '下下周待交', 'course_id': 'gradescope:other', 'submitted': False, 'availability': 'open', 'due_at': '2026-10-30T23:59:00Z'}]}},
}, datetime(2026, 10, 16, tzinfo=module.ZONE))
assert (homework['week_start'], homework['start'], homework['end']) == ('2026-10-12', '2026-10-05', '2026-11-01')
assert [item['id'] for item in homework['items']] == ['blackboard:late', 'blackboard:current', 'blackboard:pending', 'gradescope:pending']
assert [item['offset'] for item in homework['items']] == [-1, 0, 1, 2]
assert [item['late'] for item in homework['items']] == [True, True, False, False]
assert homework['items'][0]['course_title'] == '合成课程' and (homework['pending'], homework['late']) == (2, 2)
for invalid in [html.replace(mask, "010"), "<html>maintenance</html>"]:
    try:
        parse(invalid, "2026 Fall")
        raise AssertionError("Malformed timetable must preserve the previous snapshot")
    except SourceError:
        pass

async def check_schedule():
    with sandbox("timetable") as context:
        changed = False
        disabled = False

        async def api(name, path="/snapshot", **options):
            if changed:
                context.auth.revision = "synthetic-account-two"
            if disabled and name == "eams":
                return httpx.Response(404)
            if path == "/sync":
                return httpx.Response(202, json={"status": "syncing"})
            items = {
                "blackboard": [{"id": "blackboard:quiz", "source": "blackboard", "title": "Quiz 1", "due_at": "2026-10-20T09:00:00+08:00"}, {"id": "blackboard:untimed", "source": "blackboard", "title": "Untimed", "due_at": "invalid"}],
                "gradescope": [{"id": "gradescope:hw", "source": "gradescope", "title": "HW 1", "due_at": "2026-10-19T16:00:00Z", "submitted": True}],
                "eams": [{"id": "eams:exam", "source": "eams", "title": "Exam", "kind": "exam", "due_at": "2026-10-20T10:00:00+09:00"}],
            }
            return httpx.Response(200, json={"status": "ready", "updated_at": "2026-10-16T00:00:00Z", "data": validate_bundle({"assignments": items[name]})})

        context.api = api
        app = FastAPI()
        app.include_router(module.create_router(context))
        source = module._source
        context.store.write("snapshot", {"owner": source.owner(), "data": validate_bundle(result), "updated_at": "2026-10-16T00:00:00Z"})
        context.store.write("sync", {"owner": source.owner(), "status": "ready"})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fixture") as client:
                schedule = (await client.get("/schedule")).json()
                assert len(schedule["data"]["timetable"]) == 2
                assert schedule["homework"]["items"] == [] and schedule["homework"]["pending"] == schedule["homework"]["late"] == 0
                fallback = (await client.get('/schedule?week_start=2026-09-15')).json()['calendar']
                assert fallback['week_start'] == '2026-09-14' and fallback['teaching_week'] is None
                assert fallback['week_one'] is None and fallback['week_one_source'] is None
                assert not any(row['event_type'] == 'class' for day in fallback['days'] for row in day['events'])
                assert (await client.get('/calendar-settings')).json()['source'] is None
                assert not fallback['conflicts']['complete'] and schedule['status'] == 'partial'
                assert [item["id"] for item in schedule["data"]["events"]] == ["gradescope:hw", "blackboard:quiz", "eams:exam"]
                assert [item["event_type"] for item in schedule["data"]["events"]] == ["deadline", "deadline", "exam"]
                assert schedule["data"]["undated"] == 1
                assert "events" not in (await client.get("/snapshot")).json()["data"]
                assert (await client.put('/calendar-settings', json={'week_one': '2026-10-20'})).status_code == 422
                assert (await client.put('/calendar-settings', json={'week_one': '2026-10-19'})).status_code == 200
                context.store.write('school-calendar:2026', {'terms': official_terms})
                anchor = (await client.get('/calendar-settings')).json()
                assert anchor['source'] == 'manual' and anchor['week_one'] == '2026-10-19'
                saved = context.store.read('snapshot')
                context.store.write('snapshot', {**saved, 'data': {**saved['data'], 'metadata': {**saved['data']['metadata'], 'semester': '2026-2027学年春季', 'semester_id': '92'}}})
                spring = (await client.get('/calendar-settings')).json()
                assert spring['source'] == 'school' and spring['week_one'] == '2027-02-15'
                context.store.write('snapshot', saved)
                assert (await client.get('/calendar-settings')).json()['week_one'] == '2026-10-19'
                selected = (await client.get('/schedule?week_start=2026-10-20')).json()['calendar']
                assert selected['week_start'] == '2026-10-19' and selected['teaching_week'] == 1
                assert len([item for item in selected['days'][1]['events'] if item['event_type'] == 'class']) == 2
                event = {'title': '合成讲座', 'event_type': 'lecture', 'starts_at': '2026-10-20T16:00:00+08:00', 'ends_at': '2026-10-20T17:00:00+08:00'}
                response = await client.post('/events', json=event)
                assert response.status_code == 201
                event_id = response.json()['id']
                assert (await client.put('/events/' + event_id, json={**event, 'title': '更新讲座'})).status_code == 200
                selected = (await client.get('/schedule?week_start=2026-10-20')).json()['calendar']
                assert any(item['title'] == '更新讲座' for item in selected['days'][1]['events'])
                assert (await client.delete('/events/' + event_id)).status_code == 200
                assert (await client.delete('/calendar-settings')).json()['week_one'] == '2026-09-14'
                disabled = True
                schedule = (await client.get("/schedule")).json()
                assert len([item for item in schedule['data']['events'] if item['source'] != 'calendar']) == 2 and "教务系统" in schedule["data"]["issues"][0]
                synced = await client.post("/schedule/sync")
                assert synced.status_code == 202 and set(synced.json()["sources"]) == {"timetable", "blackboard", "gradescope", "eams"}
                assert synced.json()["sources"]["eams"]["status"] == "unavailable"
                changed = True
                response = await client.get("/schedule")
                assert response.status_code == 409 and "data" not in response.json()
        finally:
            module.stop(context)


asyncio.run(check_schedule())
print("timetable: week parsing, combined deadlines/exams, timezone order, optional sources and account isolation passed")
