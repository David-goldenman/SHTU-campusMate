"""Select public campus records and validate model citations."""
import json
from datetime import datetime, timezone

from fastapi import HTTPException

from .data import digest
from .remote import SourceError

PROVIDERS = ("ids", "coremail", "gradescope", "piazza")
FIELDS = ("source", "title", "url", "code", "term", "course_id", "sender", "received_at", "due_at", "release_at", "updated_at", "submitted", "actionable", "availability", "score", "max_score", "path", "teacher", "location", "weekday", "period_start", "period_end", "weeks", "grades", "stale")


def account_revision(context):
    return digest([context.auth.get_status(provider)["account_revision"] for provider in PROVIDERS])


async def build_context(context, course_id=None, context_ids=None):
    response = await context.api("courses")
    if response.status_code != 200:
        raise HTTPException(409, "请启用课程中心并同步来源资料。")
    data = response.json()["data"]
    courses = data["courses"]
    if course_id and not any(item["id"] == course_id for item in courses):
        raise HTTPException(404, "所选课程不存在或来源已停用。")
    selected_courses = [item for item in courses if item["id"] == course_id] if course_id else [item for item in courses if item.get("current")]
    members = {member for item in selected_courses for member in item["course_ids"]}
    items = []
    for kind in ("courses", "assignments", "announcements", "messages", "posts", "lessons", "materials", "timetable"):
        values = [source for item in selected_courses for source in item["sources"]] if kind == "courses" else data[kind]
        for value in values:
            if kind == "messages" and course_id is not None or kind not in {"courses", "messages"} and value.get("course_id") not in members:
                continue
            item = {key: value[key] for key in FIELDS if key in value}
            item.update(id=kind + ":" + value["id"], kind=kind, body_text=str(value.get("body_text") or "")[:1800], source_revision=digest(json.dumps(value, ensure_ascii=False, sort_keys=True)))
            items.append(item)
    known = {item["id"] for item in items}
    if context_ids is not None:
        if not set(context_ids) <= known:
            raise HTTPException(422, "部分所选资料已更新或不属于当前课程，请刷新资料范围。")
        requested = set(context_ids)
        items = [item for item in items if item["id"] in requested]
    total = len(items)
    scope = {"course_id": course_id, "semester": str(data["metadata"].get("current_semester") or "")[:120], "server_time": datetime.now(timezone.utc).isoformat(), "source_status": {name: {key: value.get(key) for key in ("status", "updated_at")} for name, value in data["metadata"].get("source_metadata", {}).items()}, "issues": [str(issue)[:300] for issue in data["issues"][:20]]}
    chosen = []
    for item in items[:400]:
        chosen.append(item)
        if len(json.dumps({"scope": scope, "items": chosen}, ensure_ascii=False)) > 85000:
            chosen.pop()
            break
    if len(json.dumps(scope, ensure_ascii=False)) > 20000:
        raise SourceError("来源诊断信息过多，请先修复来源连接。")
    epoch = account_revision(context)
    return {"items": chosen, "courses": [{key: item[key] for key in ("id", "title", "term", "current")} for item in courses], "text": json.dumps({"scope": scope, "items": chosen}, ensure_ascii=False), "context": {"total": total, "included": len(chosen), "truncated": len(chosen) < total, "text_available": sum(bool(item["body_text"]) for item in chosen), "course_id": course_id}, "account_revision": epoch, "revision": digest(json.dumps({"items": chosen, "course_id": course_id, "account": epoch}, ensure_ascii=False, sort_keys=True))}


def citations(ids, context):
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise SourceError("AI 返回的引用格式不正确。")
    known = {item["id"]: item for item in context["items"]}
    if any(identity not in known for identity in ids):
        raise SourceError("AI 引用了当前资料范围以外的条目，请重试。")
    return [{"id": identity, "title": known[identity].get("title", "来源"), "source": known[identity]["source"], "url": known[identity].get("url", "")} for identity in dict.fromkeys(ids)]
