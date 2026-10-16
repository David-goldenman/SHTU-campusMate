from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException

from backend.services.campus import timestamp


def arrange(data, now=None):
    at = now or datetime.now(timezone.utc)
    groups = {member: course for course in data["courses"] for member in course["course_ids"]}
    values = []
    for item in data["assignments"]:
        if item["source"] not in {"gradescope", "blackboard"}:
            continue
        group = groups.get(item.get("course_id"), {})
        due = timestamp(item.get("due_at"))
        pending = bool(group.get("current")) and item.get("actionable") is True and item.get("submitted") is False
        values.append({**item, "group_id": group.get("id"), "course_title": group.get("title", "未关联课程"), "current": bool(group.get("current")), "pending": pending, "overdue": bool(pending and due and datetime.fromisoformat(due) < at)})
    def order(item):
        value = timestamp(item.get("release_at") or item.get("created_at") or item.get("due_at"))
        return datetime.fromisoformat(value).timestamp() if value else 0
    return sorted(values, key=order, reverse=True)


def create_router(context):
    router = APIRouter()

    @router.get("/snapshot")
    async def snapshot():
        response = await context.api("courses")
        if response.status_code != 200:
            raise HTTPException(409, "请启用课程中心与作业来源模块。")
        value = response.json()
        data = value["data"]
        assignments = arrange(data)
        pending = sorted((item for item in assignments if item["pending"]), key=lambda item: datetime.fromisoformat(timestamp(item.get("due_at"))).timestamp() if timestamp(item.get("due_at")) else float("inf"))
        return {"status": value["status"], "data": {**data, "assignments": assignments}, "pending": pending, "updated_at": value.get("updated_at")}

    @router.post("/sync", status_code=202)
    async def sync():
        response = await context.api("courses", "/sync", method="POST")
        if response.status_code != 202:
            raise HTTPException(409, "请先启用课程中心。")
        return response.json()

    @router.get("/detail")
    async def detail(assignment_id: str):
        data = (await snapshot())["data"]
        item = next((item for item in data["assignments"] if item["id"] == assignment_id), None)
        if item is None:
            raise HTTPException(404, "作业不在当前缓存中。")
        if item["source"] == "gradescope" and item.get("source_id"):
            response = await context.api("gradescope", "/assignment?" + urlencode({"course_id": item["source_course_id"], "assignment_id": item["source_id"]}))
            if response.status_code != 200:
                raise HTTPException(response.status_code if response.status_code in {401, 404, 409} else 502, "作业详情当前不可用，请查看原站或重新同步。")
            return response.json()
        return {"assignment": item, "materials": [value for value in data["materials"] if value["id"].startswith(item["id"] + ":") and value.get("type") == "file"]}

    return router
