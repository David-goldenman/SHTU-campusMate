import asyncio
import sys
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
calendar_parser = module.SchoolCalendar.refresh.__globals__['parse']
official_terms = calendar_parser('秋 学 期 （2026．9．14—2027．1．17）10月28日校运动会，全校停课。春学期（2027.2.15-2027.6.20）暑学期（2027.6.21-2027.7.18）')
assert official_terms['2026-fall']['week_one'] == '2026-09-14'
assert official_terms['2026-fall']['closures'] == [{'date': '2026-10-28', 'title': '校运动会（全校停课）'}]
assert official_terms['2026-spring']['week_one'] == '2027-02-15'
from datetime import date
dated = {'metadata': {'periods': [{'period': 5, 'start': '13:00', 'end': '13:45'}, {'period': 6, 'start': '13:50', 'end': '14:35'}]},
         'timetable': [{**item, 'weekday': 3, 'weeks': [7]}], 'events': []}
open_day = module.calendar(dated, date(2026, 10, 26), '2026-09-14')['days'][2]
assert open_day['events'][0]['at'] == '2026-10-28T13:00:00+08:00'
assert open_day['events'][0]['ends_at'] == '2026-10-28T14:35:00+08:00'
dated['events'] = [{'id': 'calendar:closure', 'source': 'calendar', 'date': '2026-10-28', 'at': '2026-10-28T00:00:00+08:00'}]
assert all(event.get('event_type') != 'class' for event in module.calendar(dated, date(2026, 10, 26), '2026-09-14')['days'][2]['events'])
inferred = module.inferred_week_one
assert inferred({'semester': '2026-2027学年秋季'}) == '2026-09-14'
assert inferred({'semester': '2026-2027学年春季'}) == '2027-02-08'
assert inferred({'semester': '2026-2027学年夏季'}) == '2027-07-05'
assert inferred({'semester': '2026 Fall'}) is None
# A room change across weeks must not duplicate the card inside one week.
split = {'metadata': {'periods': []}, 'events': [], 'timetable': [
    {**item, 'id': 'first-room', 'weekday': 2, 'weeks': [1, 2], 'location': 'A'},
    {**item, 'id': 'second-room', 'weekday': 2, 'weeks': [3], 'location': 'B'}]}
assert [event['location'] for event in module.calendar(split, date(2026, 9, 14), '2026-09-14')['days'][1]['events']] == ['A']
assert [event['location'] for event in module.calendar(split, date(2026, 9, 28), '2026-09-14')['days'][1]['events']] == ['B']
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
                fallback = (await client.get('/schedule?week_start=2026-09-15')).json()['calendar']
                assert fallback['week_start'] == '2026-09-14' and fallback['teaching_week'] == 1
                assert fallback['week_one'] == '2026-09-14' and fallback['week_one_source'] == 'inferred'
                assert len(fallback['days'][1]['events']) == 2 and all(event['event_type'] == 'class' for event in fallback['days'][1]['events'])
                assert (await client.get('/calendar-settings')).json()['source'] == 'inferred'
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
