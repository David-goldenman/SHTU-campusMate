"""Outstanding homework for the timetable's four-week reminder window."""
from datetime import date, datetime, timedelta

from backend.services.campus import assignment_section, timestamp

from .calendar import ZONE, calendar, event_order

PLATFORMS = {"blackboard": "Blackboard", "gradescope": "Gradescope", "ecourse": "E 云课堂"}


def homework_window(values, now=None):
    """Return pending and late work from last week through the next two weeks."""
    at = (now or datetime.now(ZONE)).astimezone(ZONE)
    monday = at.date() - timedelta(days=at.weekday())
    start = monday - timedelta(days=7)
    end = monday + timedelta(days=21)
    start_at = datetime.combine(start, datetime.min.time(), ZONE)
    end_at = datetime.combine(end, datetime.min.time(), ZONE)
    items, seen = [], set()
    for name in PLATFORMS:
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


def overview_weeks(data, homework, week_one, adjustments=()):
    """Build the fixed four-week grid and enrich matching deadlines.

    The regular calendar already contains assignment deadlines.  The reminder
    window adds the submission platform, course title and late state, so the
    grid can show one card per outstanding item instead of a second copy.
    Weeks do not follow the selected week: they stay anchored to the current
    teaching week, just like the reminder counts.
    """
    anchor = date.fromisoformat(homework["week_start"])
    reminders = {item["id"]: item for item in homework["items"]}
    weeks = []
    for offset in range(-1, 3):
        week = calendar(data, anchor + timedelta(weeks=offset), week_one, adjustments)
        for day in week["days"]:
            events, seen = [], set()
            for item in day["events"]:
                reminder = reminders.get(item["id"]) if item.get("event_type") == "deadline" else None
                if reminder:
                    seen.add(item["id"])
                    events.append({**item, "homework": True, "platform": PLATFORMS.get(reminder["source"], reminder["source"]),
                                   "late": reminder["late"], "category": reminder["category"],
                                   "course_title": reminder.get("course_title") or item.get("course_title", "")})
                else:
                    events.append(item)
            for identity, reminder in reminders.items():
                if identity in seen or (reminder.get("due_at") or "")[:10] != day["date"]:
                    continue
                events.append({"id": identity, "title": reminder.get("title", ""), "url": reminder.get("url"),
                               "source": reminder["source"], "event_type": "deadline", "at": reminder["due_at"],
                               "course_title": reminder.get("course_title", ""), "homework": True,
                               "platform": PLATFORMS.get(reminder["source"], reminder["source"]),
                               "late": reminder["late"], "category": reminder["category"]})
            day["events"] = sorted(events, key=event_order)
        weeks.append({**week, "offset": offset})
    return {"week_start": anchor.isoformat(), "start": homework["start"], "end": homework["end"], "weeks": weeks,
            "pending": homework["pending"], "late": homework["late"]}
