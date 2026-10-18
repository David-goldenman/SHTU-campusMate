from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

from backend.services.campus import SECTIONS, assignment_section, timestamp
from backend.services.campus.assignments import SHANGHAI, semester_start
from backend.services.campus.analysis import account_revision

SUBMISSION_STATES = ('not_submitted', 'draft', 'submitted', 'needs_grading', 'graded', 'exempt', 'unknown')


def submission_state(item):
    if item.get('exempt') is True:
        return 'exempt'
    if item.get('submission_status') in SUBMISSION_STATES:
        return item['submission_status']
    if item.get('submitted') is True:
        return 'graded' if item.get('score') is not None else 'submitted'
    return 'not_submitted' if item.get('submitted') is False else 'unknown'


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


def default_due(metadata):
    """Teaching week 18 Sunday is the fallback when a source omits a deadline."""
    start = semester_start(metadata)
    if not start:
        return None
    first = date.fromisoformat(start)
    first -= timedelta(days=first.weekday())
    day = first + timedelta(weeks=18) - timedelta(days=1)
    return datetime.combine(day, time(23, 59), tzinfo=SHANGHAI).isoformat()


def arrange(data, now=None, order=None, dues=None):
    at = now or datetime.now(timezone.utc)
    metadata = data.get("metadata", {})
    current = metadata.get("current_semester")
    start = semester_start(metadata)
    fallback = default_due(metadata)
    groups = {member: course for course in data["courses"] for member in course["course_ids"]}
    values = []
    for item in data["assignments"]:
        if item["source"] not in {"gradescope", "blackboard", "ecourse"}:
            continue
        group = groups.get(item.get("course_id"), {})
        saved_due = timestamp((dues or {}).get(item["id"]))
        due = saved_due or timestamp(item.get("due_at"))
        category = assignment_section({**item, "due_at": due}, at, course=group, current=current, start=start)
        due_default = False
        if not due and not saved_due and category == "pending" and fallback:
            due, due_default = fallback, True
        state = submission_state(item)
        source = data.get("metadata", {}).get("source_metadata", {}).get(item["source"], {})
        source_stale = source.get("status") in {"error", "login_required", "verification_required", "not_connected"}
        # Pending is the summary list shown by the dashboard: every current
        # assignment that still accepts work, including late submissions and
        # open work whose submission state could not be confirmed.  An
        # explicit "unavailable" history or an exempt record is not actionable.
        pending = (bool(group.get("current")) and category in {"pending", "late"}
                   and state != "exempt" and item.get("submission_evidence") != "unavailable")
        values.append({**item, "due_at": due, "due_default": due_default,
                       "due_source": "manual" if saved_due else "default" if due_default else "source" if due else None,
                       "submission_status": state, "source_status": source.get("status"),
                       "source_updated_at": source.get("updated_at"), "source_stale": source_stale,
                       "needs_review": state == "unknown" or bool(item.get("stale") or item.get("submission_stale") or source_stale),
                       "group_id": group.get("id"), "course_title": group.get("title", "未关联课程"),
                       "current": bool(group.get("current")), "category": category, "pending": pending,
                       "overdue": category == "late"})
    return apply_order(values, order)


class OrderUpdate(BaseModel):
    section: Literal["pending", "late", "graded", "completed", "ended"]
    ids: list[str] = Field(max_length=5000)
    account_revision: str = Field(min_length=1, max_length=100)


class DeadlineUpdate(BaseModel):
    assignment_id: str = Field(min_length=1, max_length=300)
    due_at: AwareDatetime | None = None
    account_revision: str = Field(min_length=1, max_length=100)


def counts(values):
    return {name: sum(item["category"] == name for item in values) for name in SECTIONS}


def summary(assignments):
    def count(items):
        return {'total': len(items), 'unsubmitted': sum(item.get('submitted') is False and item['submission_status'] in {'not_submitted', 'draft'} for item in items),
                'pending': sum(item['pending'] for item in items),
                'submission_states': {state: sum(item['submission_status'] == state for item in items) for state in SUBMISSION_STATES},
                'needs_review': sum(item['needs_review'] for item in items)}
    return {**count(assignments),
            'by_source': {source: count([item for item in assignments if item['source'] == source])
                                               for source in sorted({item['source'] for item in assignments})}}


def create_router(context):
    router = APIRouter()

    def order_key(owner):
        return "assignment-order:" + owner

    def due_key(owner):
        return "assignment-due:" + owner

    def saved_order(owner):
        value = context.store.read(order_key(owner), {})
        if not isinstance(value, dict):
            return {}
        return {section: [identity for identity in value.get(section, []) if isinstance(identity, str)]
                for section in SECTIONS if isinstance(value.get(section), list)}

    def saved_dues(owner):
        value = context.store.read(due_key(owner), {})
        if not isinstance(value, dict):
            return {}
        return {identity: due for identity, due in value.items()
                if isinstance(identity, str) and timestamp(due)}

    @router.get("/snapshot")
    async def snapshot():
        response = await context.api("courses")
        if response.status_code != 200:
            raise HTTPException(409, "请启用课程中心与作业来源模块。")
        value = response.json()
        data = value["data"]
        owner = account_revision(context)
        order, dues = saved_order(owner), saved_dues(owner)
        assignments = arrange(data, order=order, dues=dues)
        pending = sorted((item for item in assignments if item["pending"]), key=lambda item: datetime.fromisoformat(timestamp(item.get("due_at"))).timestamp() if timestamp(item.get("due_at")) else float("inf"))
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取作业。")
        return {"status": value["status"], "data": {**data, "assignments": assignments}, "pending": pending,
                "summary": summary(assignments), "counts": counts(assignments), "updated_at": value.get("updated_at"),
                "order": order, "due_overrides": dues, "account_revision": owner}

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

    @router.put("/deadline")
    async def save_deadline(body: DeadlineUpdate):
        owner = account_revision(context)
        if body.account_revision != owner:
            raise HTTPException(409, "账号已切换，请重新读取作业后再设置截止时间。")
        current = await snapshot()
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取作业后再设置截止时间。")
        if not any(item["id"] == body.assignment_id for item in current["data"]["assignments"]):
            raise HTTPException(404, "作业不在当前缓存中。")
        dues = saved_dues(owner)
        if body.due_at is None:
            dues.pop(body.assignment_id, None)
        else:
            dues[body.assignment_id] = body.due_at.astimezone(SHANGHAI).isoformat()
        context.store.write(due_key(owner), dues)
        return {"assignment_id": body.assignment_id, "due_at": dues.get(body.assignment_id),
                "due_overrides": dues, "account_revision": owner}

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
