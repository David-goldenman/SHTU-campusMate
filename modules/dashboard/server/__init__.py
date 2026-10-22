import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from backend.services.campus.analysis import account_revision


def summarize(data, pending, notices):
    courses = [item for item in data["courses"] if item.get("current")]
    ids = {member for item in courses for member in item["course_ids"]}
    sources = data["metadata"].get("source_metadata", {})
    return {"stats": {"courses": len(courses), "pending": len(pending), "materials": sum(item.get("course_id") in ids for item in data["materials"]), "ready_sources": sum(value.get("status") in {"ready", "partial", "cached"} for value in sources.values())}, "upcoming": [item for item in pending if item.get("due_at") and not item.get("due_default")][:5], "notifications": [item for item in notices if not item.get("read")][:3]}


def compact(snapshot):
    """Keep every pending item for counts, but omit unrelated course contents."""
    fields = ('id', 'title', 'course_title', 'url', 'due_at', 'due_default', 'needs_review')
    return {**snapshot,
            'data': {key: snapshot['data'][key] for key in ('metadata', 'issues')},
            'pending': [{key: item[key] for key in fields if key in item} for item in snapshot['pending']],
            'upcoming': [{key: item[key] for key in fields if key in item} for item in snapshot['upcoming']]}


def create_router(context):
    router = APIRouter()

    @router.get("/snapshot")
    async def snapshot():
        owner = account_revision(context)
        courses, assignments, notices, schedule = await asyncio.gather(context.api("courses", reuse_key=owner), context.api("assignments", reuse_key=owner), context.api("notifications"), context.api('timetable', '/schedule'))
        if courses.status_code != 200:
            raise HTTPException(409, "请启用课程中心，连接来源后即可查看总览。")
        value = courses.json()
        pending = assignments.json().get("pending", []) if assignments.status_code == 200 else []
        coverage = assignments.json().get('coverage', {'status': 'ready', 'sources': []}) if assignments.status_code == 200 else {'status': 'unavailable', 'sources': []}
        notifications = notices.json().get("items", []) if notices.status_code == 200 else []
        if assignments.status_code != 200:
            value["data"]["issues"].append("作业管理模块未启用或暂时不可用。")
        if owner != account_revision(context):
            raise HTTPException(409, '账号已切换，请重新读取总览。')
        today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        days = schedule.json().get('calendar', {}).get('days', []) if schedule.status_code == 200 else []
        agenda = [day for day in days if day['date'] >= today][:2]
        result = {**value, **summarize(value["data"], pending, notifications), 'pending': pending, 'agenda': agenda,
                  'assignment_coverage': coverage}
        if coverage['status'] == 'unavailable':
            result['stats']['pending'] = None
        return result

    @router.get('/summary')
    async def summary():
        return compact(await snapshot())

    @router.post("/sync", status_code=202)
    async def sync():
        response = await context.api("courses", "/sync", method="POST")
        if response.status_code != 202:
            raise HTTPException(409, "请启用课程中心。")
        return response.json()

    return router
