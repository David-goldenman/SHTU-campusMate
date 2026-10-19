import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.campus.source import snapshots
from backend.services.campus.analysis import account_revision
from .context import build_context
from .catalog import SOURCES, combine, current_semester, query
from .appearance import PALETTE, colors, decorate


class Selection(BaseModel):
    course_id: str | None = Field(default=None, max_length=160)
    context_ids: list[str] | None = Field(default=None, max_length=400)


class Group(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    course_ids: list[str] = Field(min_length=2, max_length=20)


class Groups(BaseModel):
    groups: list[Group] = Field(max_length=200)


def create_router(context):
    router = APIRouter()

    @router.get("/identities")
    async def identities(current: bool = True):
        """Course identity only; never reads group facts or calls back into group messages."""
        owner = account_revision(context)
        values, unavailable = await snapshots(context, {name: provider for name, provider in SOURCES.items() if name != 'mail'})
        data = combine(values, context.store.read('groups', []), current_semester(values))
        if owner != account_revision(context):
            raise HTTPException(409, '账号已更新，请刷新课程列表。')
        fields = ('id', 'title', 'title_source', 'title_source_id', 'aliases', 'code', 'term', 'current', 'course_ids')
        return {'items': [{key: row[key] for key in fields if key in row} for row in data['courses'] if not current or row['current']],
                'account_revision': owner, 'current_semester': data['metadata']['current_semester'], 'unavailable': unavailable}

    @router.get("/snapshot")
    async def snapshot():
        owner = account_revision(context)
        values, unavailable = await snapshots(context, SOURCES)
        # Optional local facts have no school login provider and never call back into courses.
        group_response = await context.api('group-messages', '/snapshot')
        if group_response.status_code == 200:
            values['group-messages'] = group_response.json()
        response = await context.api("eams")
        plan = {}
        if response.status_code == 200:
            try:
                candidate = response.json().get("data", {}).get("metadata", {}).get("study_plan", {})
                plan = candidate if isinstance(candidate, dict) else {}
            except (ValueError, AttributeError):
                pass  # Optional plan metadata must not hide readable courses.
        if owner != account_revision(context):
            raise HTTPException(409, "账号已更新，请刷新课程资料。")
        data = combine(values, context.store.read("groups", []), current_semester(values))
        decorate(data["courses"], plan)
        if unavailable:
            data["issues"].append("以下来源模块未启用或暂时不可用：" + "、".join(unavailable))
        status = ("syncing" if any(value.get("status") == "syncing" for value in values.values()) else
                  "partial" if any(value.get("network_failure") for value in values.values()) else
                  "ready" if values else "not_connected")
        return {"status": status, "data": data, "updated_at": max((value["updated_at"] for value in values.values() if value.get("updated_at")), default=None), "unavailable": unavailable,
                "network_failures": [value["network_failure"] for value in values.values() if value.get("network_failure")]}

    @router.get("/appearance")
    async def appearance():
        value = await snapshot()
        return {"courses": [{key: item[key] for key in ("id", "course_ids", "code", "term", "department", "department_source", "appearance")}
                            for item in value["data"]["courses"]], "palette": [colors(row) for row in PALETTE]}

    @router.post("/context")
    async def selected_context(body: Selection):
        owner = account_revision(context)
        data = (await snapshot())["data"]
        selected = build_context(data, owner, body.course_id, body.context_ids)
        if owner != account_revision(context):
            raise HTTPException(409, "账号已更新，请重新选择资料。")
        return selected

    @router.post("/sync", status_code=202)
    async def sync():
        async def dispatch(source, provider):
            account = context.auth.get_status(provider)
            if not account.get("has_session") and not account.get("has_password"):
                return source, {"status": "not_connected"}
            response = await context.api(source, "/sync", method="POST")
            return source, response.json() if response.status_code == 202 else {"status": "unavailable"}
        return {"sources": dict(await asyncio.gather(*(dispatch(source, provider) for source, provider in SOURCES.items())))}

    @router.get("/catalog/{collection}")
    async def catalog(collection: Literal["courses", "assignments", "materials", "announcements", "posts", "lessons", "timetable", "messages"], course_id: str | None = None, current: bool = False, pending: bool = False, source: str | None = None, q: str = Query(default="", max_length=1000), offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
        data = (await snapshot())["data"]
        if course_id and not any(item["id"] == course_id for item in data["courses"]):
            raise HTTPException(404, "课程不存在或来源已停用。")
        if pending and collection != "assignments":
            raise HTTPException(400, "待办筛选用于作业集合。")
        values = query(data, collection, course_id=course_id, current=current, pending=pending, source=source, q=q)
        return {"items": values[offset:offset + limit], "total": len(values), "offset": offset, "limit": limit, "issues": data["issues"]}

    @router.get("/course")
    async def course(course_id: str):
        data = (await snapshot())["data"]
        item = next((item for item in data["courses"] if item["id"] == course_id), None)
        if item is None:
            raise HTTPException(404, "课程不存在或来源已停用。")
        return {"course": item, **{kind: query(data, kind, course_id=course_id) for kind in ("assignments", "materials", "announcements", "posts", "lessons", "timetable")}, "issues": data["issues"]}

    @router.get("/groups")
    def groups():
        return {"groups": context.store.read("groups", [])}

    @router.put("/groups")
    async def set_groups(body: Groups):
        data = (await snapshot())["data"]
        known = {member for item in data["courses"] for member in item["course_ids"]}
        members = [member for group in body.groups for member in group.course_ids]
        if len(set(members)) != len(members) or len({group.id for group in body.groups}) != len(body.groups) or not set(members) <= known:
            raise HTTPException(422, "课程组标识应唯一，每门已知课程只能属于一个手动分组。")
        context.store.write("groups", [group.model_dump() for group in body.groups])
        return {"saved": True}

    return router
