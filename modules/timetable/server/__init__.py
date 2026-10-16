import asyncio
from datetime import datetime

from fastapi import HTTPException

from backend.services.campus import Source, timestamp
from backend.services.campus.analysis import account_revision
from backend.services.campus.source import snapshots
from .reader import fetch

SCHEDULE_SOURCES = {"blackboard": "Blackboard", "gradescope": "Gradescope", "eams": "教务系统"}
_source = None


def create_router(context):
    global _source
    source = _source = Source(context, "ids", ["eams.shanghaitech.edu.cn"], fetch, target="timetable")
    router = source.router()

    @router.get("/schedule")
    async def schedule():
        owner = account_revision(context)
        values, unavailable = await snapshots(context, SCHEDULE_SOURCES)
        values = {"timetable": source.snapshot(), **values}
        events, issues, undated = [], [], 0
        for name, value in values.items():
            data = value["data"]
            label = SCHEDULE_SOURCES.get(name, "教务课表")
            issues.extend(label + "：" + str(issue) for issue in data["issues"])
            if value.get("message"):
                issues.append(label + "：" + value["message"])
            courses = {item["id"]: item["title"] for item in data["courses"]}
            for item in data["assignments"]:
                at = timestamp(item.get("due_at"))
                if not at:
                    undated += 1
                    continue
                events.append({**item, "at": at, "event_type": "exam" if name == "eams" else "deadline", "course_title": courses.get(item.get("course_id"), "")})
        if unavailable:
            issues.append("以下来源未启用或暂时不可用：" + "、".join(SCHEDULE_SOURCES[name] for name in unavailable))
        events.sort(key=lambda item: (datetime.fromisoformat(item["at"]).timestamp(), item["id"]))
        syncing = any(value.get("status") == "syncing" for value in values.values())
        updated = max((value["updated_at"] for value in values.values() if value.get("updated_at")), default=None)
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取时间表。")
        return {"status": "syncing" if syncing else "partial" if issues and updated else "ready" if updated else "not_connected",
                "updated_at": updated, "data": {**values["timetable"]["data"], "events": events, "undated": undated, "issues": issues},
                "sources": {name: {"status": value.get("status"), "updated_at": value.get("updated_at")} for name, value in values.items()}}

    @router.post("/schedule/sync", status_code=202)
    async def sync_schedule():
        results = await asyncio.gather(*(context.api(name, "/sync", method="POST") for name in SCHEDULE_SOURCES))
        return {"sources": {"timetable": source.sync(), **{name: result.json() if result.status_code == 202 else {"status": "unavailable"} for name, result in zip(SCHEDULE_SOURCES, results)}}}

    return router


def stop(context):
    if _source is not None:
        _source.close()
