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
                assert [item["id"] for item in schedule["data"]["events"]] == ["gradescope:hw", "blackboard:quiz", "eams:exam"]
                assert [item["event_type"] for item in schedule["data"]["events"]] == ["deadline", "deadline", "exam"]
                assert schedule["data"]["undated"] == 1
                assert "events" not in (await client.get("/snapshot")).json()["data"]
                disabled = True
                schedule = (await client.get("/schedule")).json()
                assert len(schedule["data"]["events"]) == 2 and "教务系统" in schedule["data"]["issues"][0]
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
