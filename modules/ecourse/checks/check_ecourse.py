"""Synthetic Ecourse read contract, partial refresh and aggregate acceptance."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI

from backend.services.auth import protocols
from backend.services.campus import SourceError
from checks.module_support import load, sandbox

package = load("ecourse")
reader = sys.modules[package.__name__ + ".reader"]
calls, broken, malformed = [], set(), set()


def handler(request):
    path = request.url.path
    calls.append((request.method, path))
    if path in broken:
        return httpx.Response(403)
    if path in malformed:
        return httpx.Response(200, json={"changed": []})
    if path == "/user/index":
        return httpx.Response(200, text='var globalData = {course:{id:0},user:{id:1,userNo:"synthetic-account",},dept:{}};')
    if path == "/api/my-courses":
        assert request.method == "POST"
        query = json.loads(request.content)
        assert query["conditions"] == {} and query["fields"] == "" and query["page_size"] == 100
        page = query["page"]
        values = [{"id": 1, "name": "合成课程-QA101.01", "course_code": "QA101.01", "semester": {"code": "2026-1"}, "department": {"name": "信息科学与技术学院"}}] if page == 1 else [{"id": 2, "name": "往期课程", "course_code": "QA102.01", "semester": {"code": "2025-2"}}]
        return httpx.Response(200, json={"courses": values, "page": page, "total": 2})
    assert request.method == "GET", "Only the known course search may POST"
    if path.endswith("/coursewares"):
        return httpx.Response(200, json={"activities": [{"id": 10, "title": "合成课件", "type": "material", "data": {"description": "<p>定义与例题</p>"}, "uploads": [{"id": 99, "name": "讲义.pdf", "type": "document", "size": 20, "link": "https://example.edu/private?token=secret"}]}], "page": 1, "total": 1})
    if path.endswith("/homework-activities"):
        values = [{"id": i, "title": "合成作业" + str(i), "submitted": submitted, "is_closed": False,
                   "published": True, "end_time": "2026-10-01T10:00:00Z"}
                  for i, submitted in [(11, True), (12, False), (13, None)]]
        values[0].update(score="0", is_announce_score_time_passed=True)
        return httpx.Response(200, json={"homework_activities": values, "page": 1, "total": 3})
    if path.endswith("/bulletins"):
        return httpx.Response(200, json={"bulletins": [{"id": 20, "title": "合成公告", "content": "<p>下周复习</p>"}]})
    raise AssertionError(path)


with httpx.Client(transport=httpx.MockTransport(handler)) as client:
    assert protocols.checked_target("ids", "ecourse") == "ecourse"
    assert protocols.validate(client, "ids", "ecourse", {}) == "synthetic-account"
for html in ('<html>登录</html>', 'var globalData={user:{id:1,userNo:""}};', 'var globalData={course:{userNo:"other"},user:{id:1}};'):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=html))) as client:
        try:
            protocols.validate(client, "ids", "ecourse", {})
            raise AssertionError("Missing identity must not authorize the session")
        except protocols.LoginRequired:
            pass


async def check():
    with sandbox("ecourse", handler) as source, sandbox("courses") as courses, sandbox("assignments") as assignments:
        app = FastAPI()
        app.include_router(package.create_router(source), prefix="/ecourse")
        app.include_router(load("courses").create_router(courses), prefix="/courses")
        app.include_router(load("assignments").create_router(assignments), prefix="/assignments")
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                async def api(module, path="/snapshot", **options):
                    if module in {"ecourse", "courses", "assignments"}:
                        return await client.request(options.get("method", "GET"), "/" + module + path, json=options.get("body"))
                    return httpx.Response(404)
                courses.api = assignments.api = api
                assert (await client.post("/ecourse/sync")).status_code == 202
                package._source.future.result(timeout=5)
                value = (await client.get("/ecourse/snapshot")).json()
                assert value["status"] == "partial", value
                data = value["data"]
                assert len(data["courses"]) == 2 and data["courses"][0]["code"] == "QA101"
                assert [item["semester"] for item in data["courses"]] == ["2026-fall", "2026-spring"]
                assert data["courses"][0]["department"] == "信息科学与技术学院"
                assert "token=secret" not in json.dumps(value)
                assert data["materials"][0]["body_text"] == "定义与例题\n讲义.pdf"
                assert [item["submission_status"] for item in data["assignments"][:3]] == ["graded", "not_submitted", "unknown"]
                assert data["assignments"][0]["score"] == 0
                # Failed collections retain old data, successful empty arrays clear it.
                broken.add("/api/course/1/coursewares")
                malformed.add("/api/courses/1/homework-activities")
                package._source.run()
                value = package._source.snapshot()
                assert value["data"]["materials"][0]["stale"]
                assert all(item["stale"] for item in value["data"]["assignments"][:3])
                assert value["data"]["announcements"] and value["status"] == "partial"
                broken.clear()
                malformed.clear()
                combined = (await client.get("/courses/snapshot")).json()["data"]
                group = next(item for item in combined["courses"] if item["code"] == "QA101")
                evidence = (await client.post("/courses/context", json={"course_id": group["id"]})).json()
                assert any(item["source"] == "ecourse" and item.get("submitted") is True for item in evidence["items"])
                overview = (await client.get("/assignments/snapshot")).json()
                stats = overview["summary"]["by_source"]["ecourse"]
                assert stats["total"] == 6 and stats["unsubmitted"] == 2 and stats["submission_states"]["graded"] == 2
                # Full course-list failure must keep the last complete snapshot.
                broken.add("/api/my-courses")
                package._source.run()
                assert package._source.snapshot()["status"] == "error"
                assert len(package._source.snapshot()["data"]["courses"]) == 2
                source.auth.revision = "synthetic-other"
                assert package._source.snapshot()["data"]["courses"] == []
        finally:
            package.stop(source)
            assert package._source.cancelled.is_set()


asyncio.run(check())
selected = reader.course_record({"id": 1, "name": "合成课程"})
assert reader.material({"id": 4, "title": "合成页面", "type": "page", "data": {"content": "<p>页面正文</p>"}}, selected)["body_text"] == "页面正文"
previous = {"ecourse:1:homework:3": {"submitted": True, "submission_status": "submitted", "checked_at": "2026-01-01T00:00:00Z"}}
kept = reader.assignment({"id": 3, "title": "合成作业"}, selected, previous, "2026-10-17T00:00:00Z")
assert kept["submitted"] is True and kept["submission_stale"] and kept["checked_at"] == "2026-01-01T00:00:00Z"
assert reader.assignment({"id": 3, "title": "合成作业", "submitted": True}, selected, {}, "2026-10-17T00:00:00Z")["submission_status"] == "submitted"


class Repeated:
    def json(self, *args, **kwargs):
        return {"activities": [{"id": 1}], "total": 2, "page": kwargs["params"]["page"]}


class Empty:
    def json(self, *args, **kwargs):
        return {"activities": [], "total": 0, "page": 0, "pages": 0}


assert reader.paged(Empty(), "/test", "activities") == []
try:
    reader.paged(Repeated(), "/test", "activities")
    raise AssertionError("Repeated pages must fail")
except SourceError:
    pass
assert all(method == "GET" or path == "/api/my-courses" for method, path in calls)
print("ecourse: read-only API, identity, pagination, status evidence, partial cache, account isolation, cancellation and aggregate context passed")
