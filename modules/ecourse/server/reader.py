"""Read the four student collections exposed by Ecourse's official client."""
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import HTTPException

from backend.services.campus import SourceError, course, identity, plain, rows, timestamp

BASE = "https://ecourse.shanghaitech.edu.cn"


def checked(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9]\d{0,17}", str(value)):
        raise SourceError("E 云课堂记录缺少合法标识。")
    return str(value)


def paged(remote, path, key, *, post=False):
    result, seen = [], set()
    for page in range(1, 101):
        params = {"page": page, "page_size": 100, "conditions": {}}
        if post:
            params["fields"] = ""
            # This POST is the platform's read-only course search, not a mutation.
            token = next((c.value for c in remote.client.cookies.jar
                          if c.name == "XSRF-TOKEN" and c.domain.lstrip(".") == "ecourse.shanghaitech.edu.cn"), "")
            headers = {"Referer": BASE + "/user/index", "X-Requested-With": "XMLHttpRequest"}
            if token:
                headers["X-XSRF-TOKEN"] = unquote(token)
            data = remote.json("POST", BASE + path, json=params, headers=headers)
        else:
            params["conditions"] = json.dumps(params["conditions"])
            data = remote.json("GET", BASE + path, params=params)
        batch = rows(data, key)
        total = data.get("total")
        if page == 1 and type(total) is int and total == 0 and not batch and data.get("page") == 0:
            return []  # Ecourse uses page=0 for a verified empty collection.
        if type(total) is not int or total < 0 or total > 10000 or data.get("page") != page:
            raise SourceError("E 云课堂分页信息无法核实，保留上次数据。")
        for item in batch:
            identifier = checked(item.get("id"))
            if identifier in seen:
                raise SourceError("E 云课堂分页出现重复记录，保留上次数据。")
            seen.add(identifier)
        result.extend(batch)
        if len(result) == total:
            return result
        if not batch or len(result) > total:
            raise SourceError("E 云课堂分页总量不一致，保留上次数据。")
    raise SourceError("E 云课堂分页超过读取上限，保留上次数据。")


def course_record(item):
    cid = checked(item.get("id"))
    code = str(item.get("course_code") or "")
    title = plain(item.get("name"))
    if not title:
        raise SourceError("E 云课堂课程缺少名称。")
    if code and title.endswith("-" + code):
        title = title[:-(len(code) + 1)].strip()
    term = item.get("semester") or {}
    department = item.get("department") or {}
    if not isinstance(term, dict) or not isinstance(department, dict):
        raise SourceError("E 云课堂课程学期或院系格式变化。")
    match = re.fullmatch(r"(20\d{2})-([123])", str(term.get("code") or ""))
    term_name = f"{match[1]}-{int(match[1]) + 1}-{match[2]}" if match else str(term.get("name") or "")
    return course("ecourse", cid, title, code, term_name, BASE + f"/course/{cid}/index",
                  department=plain(department.get("name")), department_id=department.get("id"))


def base_record(item, selected, section):
    sid = checked(item.get("id"))
    title = plain(item.get("title"))
    if not title:
        raise SourceError("E 云课堂内容缺少标题。")
    data = item.get("data") or {}
    if not isinstance(data, dict):
        raise SourceError("E 云课堂内容格式变化。")
    return {"id": identity("ecourse", selected["source_id"] + ":" + section + ":" + sid),
            "source": "ecourse", "source_id": sid, "course_id": selected["id"],
            "title": title, "body_text": plain(item.get("content") if section == "bulletin" else data.get("description")),
            "url": BASE + f"/course/{selected['source_id']}/{section}",
            "created_at": timestamp(item.get("created_at")), "updated_at": timestamp(item.get("updated_at"))}


def attachments(item):
    # Signed download links and account metadata do not belong in the cache.
    return [{"name": plain(upload.get("name")), "type": plain(upload.get("type")),
             "size": upload.get("size") if type(upload.get("size")) is int else None}
            for upload in rows(item.get("uploads", [])) if upload.get("deleted") is not True]


def material(item, selected):
    result = base_record(item, selected, "courseware")
    files = attachments(item)
    description = "\n".join(file["name"] for file in files if file["name"])
    content = plain((item.get("data") or {}).get("content")) if item.get("type") == "page" else ""
    return {**result, "type": plain(item.get("type")) or "content", "attachments": files,
            "body_text": "\n".join(part for part in (result["body_text"], content, description) if part)}


def assignment(item, selected, previous, checked_at):
    result = base_record(item, selected, "homework")
    submitted = item.get("submitted") if type(item.get("submitted")) is bool else None
    state = "submitted" if submitted is True else "not_submitted" if submitted is False else "unknown"
    score = None
    if submitted is True and (item.get("score_published") is True or item.get("is_announce_score_time_passed") is True):
        try:
            value = float(item.get("score"))
            if math.isfinite(value):
                score, state = value, "graded"
        except (ValueError, TypeError):
            pass
    judgement = {"submitted": submitted, "submission_status": state, "score": score,
                 "submission_evidence": "ecourse_homework" if submitted is not None else "unavailable",
                 "checked_at": checked_at if submitted is not None else None,
                 "submission_stale": submitted is None}
    if submitted is None:
        old = previous.get(result["id"], {})
        if type(old.get("submitted")) is bool:
            for key in ("submitted", "submission_status", "score", "submission_evidence", "checked_at"):
                judgement[key] = old.get(key)
        judgement["submission_reason"] = "本次无法核实提交情况，请重新同步或查看原站。"
    start = timestamp(item.get("start_time"))
    if item.get("published") is False or start and datetime.fromisoformat(start) > datetime.fromisoformat(checked_at):
        availability, actionable = "scheduled", False
    elif item.get("is_closed") is True:
        availability, actionable = "closed", False
    elif item.get("is_closed") is False and item.get("published") is True:
        availability, actionable = "open", True
    else:
        availability, actionable = "unknown", None
    return {**result, **judgement, "due_at": timestamp(item.get("deadline") or item.get("end_time")),
            "release_at": start or result["created_at"], "availability": availability,
            "actionable": actionable, "attachments": attachments(item)}


def fetch(remote, previous):
    result = {"courses": [], "materials": [], "assignments": [], "announcements": [],
              "issues": [], "metadata": {"scope": "all_visible_courses", "read_only": True}}
    prior_assignments = {item["id"]: item for item in previous.get("assignments", [])}
    checked_at = datetime.now(timezone.utc).isoformat()
    # A broken course list must fail the whole refresh, preserving the old snapshot.
    courses = [course_record(item) for item in paged(remote, "/api/my-courses", "courses", post=True)]
    result["courses"] = courses
    for selected in courses:
        cid = selected["source_id"]
        for kind in ("materials", "assignments", "announcements"):
            try:
                if kind == "materials":
                    values = [material(item, selected) for item in paged(remote, f"/api/course/{cid}/coursewares", "activities")]
                elif kind == "assignments":
                    values = [assignment(item, selected, prior_assignments, checked_at)
                              for item in paged(remote, f"/api/courses/{cid}/homework-activities", "homework_activities")]
                else:
                    data = remote.json("GET", BASE + f"/api/courses/{cid}/bulletins")
                    values = [{**base_record(item, selected, "bulletin"), "attachments": attachments(item)}
                              for item in rows(data, "bulletins") if item.get("deleted") is not True]
                result[kind].extend(values)
                if kind == "assignments" and any(item["submission_stale"] for item in values):
                    result["issues"].append(selected["title"] + " 的部分作业提交情况待核实。")
            except HTTPException:
                result["issues"].append(selected["title"] + " 的" + {"materials": "课件", "assignments": "作业", "announcements": "公告"}[kind] + "读取失败，保留上次数据。")
                result[kind].extend({**item, "stale": True} for item in previous.get(kind, []) if item.get("course_id") == selected["id"])
    return result
