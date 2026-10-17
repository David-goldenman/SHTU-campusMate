from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.campus import SECTIONS, assignment_section, timestamp
from backend.services.campus.analysis import account_revision


def _release(item):
    value = timestamp(item.get("release_at") or item.get("created_at") or item.get("due_at"))
    return datetime.fromisoformat(value).timestamp() if value else 0


def apply_order(values, order=None):
    """Sort by the saved drag order, falling back to newest first."""
    positions = {}
    for section, ids in (order or {}).items():
        if section in SECTIONS and isinstance(ids, list):
            positions[section] = {identity: index for index, identity in enumerate(ids) if isinstance(identity, str)}
    return sorted(values, key=lambda item: (positions.get(item["category"], {}).get(item["id"], float("inf")), -_release(item)))


def arrange(data, now=None, order=None):
    at = now or datetime.now(timezone.utc)
    groups = {member: course for course in data["courses"] for member in course["course_ids"]}
    values = []
    for item in data["assignments"]:
        if item["source"] not in {"gradescope", "blackboard"}:
            continue
        group = groups.get(item.get("course_id"), {})
        category = assignment_section(item, at)
        # Pending is the summary list shown by the dashboard: every current
        # assignment that still accepts work, including late submissions.
        pending = bool(group.get("current")) and category in {"pending", "late"}
        values.append({**item, "group_id": group.get("id"), "course_title": group.get("title", "未关联课程"), "current": bool(group.get("current")), "category": category, "pending": pending, "overdue": category == "late"})
    return apply_order(values, order)


class OrderUpdate(BaseModel):
    section: Literal["pending", "late", "graded", "completed", "ended"]
    ids: list[str] = Field(max_length=5000)
    account_revision: str = Field(min_length=1, max_length=100)


def counts(values):
    return {name: sum(item["category"] == name for item in values) for name in SECTIONS}


def create_router(context):
    router = APIRouter()

    def order_key(owner):
        return "assignment-order:" + owner

    def saved_order(owner):
        value = context.store.read(order_key(owner), {})
        if not isinstance(value, dict):
            return {}
        return {section: [identity for identity in value.get(section, []) if isinstance(identity, str)]
                for section in SECTIONS if isinstance(value.get(section), list)}

    @router.get("/snapshot")
    async def snapshot():
        response = await context.api("courses")
        if response.status_code != 200:
            raise HTTPException(409, "请启用课程中心与作业来源模块。")
        value = response.json()
        data = value["data"]
        owner = account_revision(context)
        order = saved_order(owner)
        assignments = arrange(data, order=order)
        pending = sorted((item for item in assignments if item["pending"]), key=lambda item: datetime.fromisoformat(timestamp(item.get("due_at"))).timestamp() if timestamp(item.get("due_at")) else float("inf"))
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取作业。")
        return {"status": value["status"], "data": {**data, "assignments": assignments}, "pending": pending,
                "counts": counts(assignments), "updated_at": value.get("updated_at"), "order": order, "account_revision": owner}

    @router.put("/order")
    async def save_order(body: OrderUpdate):
        owner = account_revision(context)
        if body.account_revision != owner:
            raise HTTPException(409, "账号已切换，请重新读取作业后再排序。")
        if len(set(body.ids)) != len(body.ids) or any(not identity or len(identity) > 300 for identity in body.ids):
            raise HTTPException(422, "作业顺序包含无效或重复的项目。")
        current = await snapshot()
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取作业后再排序。")
        available = {item["id"] for item in current["data"]["assignments"] if item["category"] == body.section}
        if set(body.ids) != available:
            raise HTTPException(409, "作业列表已更新，请重新排序。")
        order = saved_order(owner)
        order[body.section] = body.ids
        context.store.write(order_key(owner), order)
        return {"order": order, "account_revision": owner}

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
