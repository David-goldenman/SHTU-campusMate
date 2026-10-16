import re
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.services.campus import KINDS, semester
from backend.services.campus.data import digest

SOURCES = {"timetable": "ids", "blackboard": "ids", "gradescope": "gradescope", "piazza": "piazza", "elrc": "ids", "mail": "coremail"}


def current_semester(snapshots):
    value = snapshots.get("timetable", {}).get("data", {}).get("metadata", {}).get("semester")
    if value:
        return semester(value)
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return str(now.year - (now.month == 1)) + "-" + ("fall" if now.month in {1, 9, 10, 11, 12} else "spring" if now.month <= 6 else "summer")


def combine(snapshots, groups, current):
    result = {kind: [] for kind in KINDS}
    result.update(metadata={"current_semester": current, "source_metadata": {}}, issues=[])
    raw_courses = []
    for source, snapshot in snapshots.items():
        data = snapshot["data"]
        raw_courses.extend(data["courses"])
        for kind in KINDS:
            if kind != "courses":
                result[kind].extend(data[kind])
        result["metadata"]["source_metadata"][source] = {"status": snapshot.get("status"), "updated_at": snapshot.get("updated_at"), **data["metadata"]}
        result["issues"].extend(source + "：" + str(issue) for issue in data["issues"])
        if snapshot.get("message"):
            result["issues"].append(source + "：" + str(snapshot["message"]))
    manual = {member: group for group in groups for member in group["course_ids"]}
    buckets = {}
    for item in raw_courses:
        code, term = str(item.get("code") or ""), semester(item.get("term"))
        group = manual.get(item["id"])
        group_id = "manual:" + group["id"] if group else "course:" + digest([code, term]) if re.fullmatch(r"[A-Z]{2,}\d{2,}[A-Z]?", code) and re.fullmatch(r"20\d{2}-(fall|spring|summer)", term) else "course:" + digest(item["id"])
        merged = buckets.setdefault(group_id, {"id": group_id, "source": "catalog", "title": group["title"] if group else item["title"], "code": code, "term": term, "current": False, "course_ids": [], "sources": [], "url": item.get("url", "")})
        merged["current"] = merged["current"] or term == current
        merged["course_ids"].append(item["id"])
        merged["sources"].append(item)
    result["courses"] = sorted(buckets.values(), key=lambda item: (not item["current"], item["term"], item["code"], item["title"]))
    return result


def query(data, collection, *, course_id=None, current=False, pending=False, source=None, q=""):
    courses = [item for item in data["courses"] if (not course_id or item["id"] == course_id) and (not current or item["current"])]
    members = {member for item in courses for member in item["course_ids"]}
    if collection == "courses":
        values = [item for item in courses if not source or any(value["source"] == source for value in item["sources"])]
    else:
        values = [item for item in data[collection] if (not course_id and not current or item.get("course_id") in members) and (not source or item["source"] == source)]
    if pending:
        values = [item for item in values if item["source"] in {"gradescope", "blackboard"} and item.get("actionable") is True and item.get("submitted") is False]
    if q:
        text = q.casefold()
        values = [item for item in values if text in " ".join(str(item.get(key) or "") for key in ("title", "code", "body_text", "sender")).casefold()]
    return values
