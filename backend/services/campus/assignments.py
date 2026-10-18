"""Shared assignment state used by the assignment center and timetable."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .data import semester, timestamp

SECTIONS = ("pending", "late", "graded", "completed", "ended")
AVAILABILITY = {"open", "scheduled", "closed", "unknown"}
SHANGHAI = ZoneInfo("Asia/Shanghai")
TERM_ORDER = {"spring": 0, "summer": 1, "fall": 2}


def term_rank(value):
    match = re.fullmatch(r"(20\d{2})-(fall|spring|summer)", semester(value))
    return (int(match[1]), TERM_ORDER[match[2]]) if match else None


def semester_start(metadata):
    """Return the current semester's first day from the available source metadata."""
    sources = (metadata or {}).get("source_metadata", {})
    for name in ("timetable", "elrc"):
        value = sources.get(name, {}).get("semester")
        if isinstance(value, dict):
            value = value.get("startTime") or value.get("startDate") or value.get("week_one")
        if not value:
            continue
        parsed = timestamp(value)
        if parsed:
            return datetime.fromisoformat(parsed).astimezone(SHANGHAI).date().isoformat()
    return None


def historical(item, course=None, current=None, start=None):
    """Tell whether an assignment belongs to a semester before the current one.

    Historical work remains visible in the ended section, but its open/closed
    state and submission evidence no longer produce reminders or source errors.
    """
    course = course or {}
    rank, current_rank = term_rank(course.get("term") or course.get("semester")), term_rank(current)
    if rank and current_rank and rank < current_rank:
        return True
    if course.get("current") is False:
        return True
    due = timestamp(item.get("due_at"))
    return bool(start and due and datetime.fromisoformat(due).astimezone(SHANGHAI).date().isoformat() < start)


def filter_issues(issues, assignments, courses, current=None, start=None):
    """Hide issue text that only belongs to an already ended historical assignment."""
    by_id = courses if isinstance(courses, dict) else {course.get("id"): course for course in courses}
    titles = [item.get("title") for item in assignments
              if item.get("title") and historical(item, by_id.get(item.get("course_id"), {}), current, start)]

    def belongs_to_history(issue):
        return any(str(issue).startswith(title + " 的") for title in titles)

    return [issue for issue in issues if not belongs_to_history(issue)]


def availability(item):
    """Return the source's own open state instead of guessing from a due date."""
    state = item.get("availability")
    if state in AVAILABILITY:
        return state
    actionable = item.get("actionable")
    return "open" if actionable is True else "closed" if actionable is False else "unknown"


def section(item, now=None, *, course=None, current=None, start=None):
    """Classify one assignment.

    Work from a semester before the current one is always ended, even when its
    stale source still claims that it is open or has unresolved submission
    evidence.  Graded and completed take precedence for current-semester work
    because a submission is final even when the source has since closed the
    assignment.  Only an explicit submission is final: an open assignment whose
    submission status could not be read stays actionable instead of
    disappearing from the reminders.
    """
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if historical(item, course, current, start):
        return "ended"
    submitted, score = item.get("submitted"), item.get("score")
    if submitted is True or score is not None:
        return "graded" if score is not None else "completed"
    if availability(item) != "open":
        return "ended"
    due = timestamp(item.get("due_at"))
    return "late" if due and datetime.fromisoformat(due) <= at else "pending"
