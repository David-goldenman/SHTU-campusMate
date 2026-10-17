"""Shared assignment state used by the assignment center and timetable."""
from datetime import datetime, timezone

from .data import timestamp

SECTIONS = ("pending", "late", "graded", "completed", "ended")
AVAILABILITY = {"open", "scheduled", "closed", "unknown"}


def availability(item):
    """Return the source's own open state instead of guessing from a due date."""
    state = item.get("availability")
    if state in AVAILABILITY:
        return state
    actionable = item.get("actionable")
    return "open" if actionable is True else "closed" if actionable is False else "unknown"


def section(item, now=None):
    """Classify one assignment.

    Graded and completed take precedence because a submission is final even when
    the source has since closed the assignment.  Only an explicit submission is
    final: an open assignment whose submission status could not be read stays
    actionable instead of disappearing from the reminders.
    """
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    submitted, score = item.get("submitted"), item.get("score")
    if submitted is True or score is not None:
        return "graded" if score is not None else "completed"
    if availability(item) != "open":
        return "ended"
    due = timestamp(item.get("due_at"))
    return "late" if due and datetime.fromisoformat(due) <= at else "pending"
