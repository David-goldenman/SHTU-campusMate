"""Outstanding homework for the timetable's four-week reminder window."""
from datetime import datetime, timedelta

from backend.services.campus import assignment_section, timestamp

from .calendar import ZONE


def homework_window(values, now=None):
    """Return pending and late work from last week through the next two weeks."""
    at = (now or datetime.now(ZONE)).astimezone(ZONE)
    monday = at.date() - timedelta(days=at.weekday())
    start = monday - timedelta(days=7)
    end = monday + timedelta(days=21)
    start_at = datetime.combine(start, datetime.min.time(), ZONE)
    end_at = datetime.combine(end, datetime.min.time(), ZONE)
    items, seen = [], set()
    for name in ("blackboard", "gradescope"):
        data = values.get(name, {}).get("data", {})
        courses = {item["id"]: item.get("title", "") for item in data.get("courses", [])}
        for item in data.get("assignments", []):
            if item.get("id") in seen:
                continue
            category = assignment_section(item, at)
            if category not in {"pending", "late"}:
                continue
            due = timestamp(item.get("due_at"))
            if not due:
                continue
            when = datetime.fromisoformat(due).astimezone(ZONE)
            if not start_at <= when < end_at:
                continue
            seen.add(item["id"])
            week = when.date() - timedelta(days=when.weekday())
            items.append({"id": item["id"], "title": item.get("title", ""), "url": item.get("url"), "source": name,
                          "course_title": courses.get(item.get("course_id"), ""), "due_at": due, "category": category,
                          "late": category == "late", "week_start": week.isoformat(), "offset": (week - monday).days // 7})
    items.sort(key=lambda item: (datetime.fromisoformat(item["due_at"]).timestamp(), item["id"]))
    return {"week_start": monday.isoformat(), "start": start.isoformat(), "end": (end - timedelta(days=1)).isoformat(),
            "items": items, "pending": sum(not item["late"] for item in items), "late": sum(item["late"] for item in items)}
