import threading

from fastapi import HTTPException, Query

from backend.services.campus import Remote, Source
from .reader import DEFAULT_UNITS, DEFAULT_WEEKS, fetch, parse, table

HOSTS = ["eams.shanghaitech.edu.cn"]
_source = None


def create_router(context):
    global _source
    source = _source = Source(context, "ids", HOSTS, fetch, target="timetable")
    router = source.router()

    @router.get("/table")
    def semester_table(semester_id: str = Query(pattern=r"^\d{1,12}$")):
        """按学期读取课表，供页面切换学年与学期；未发布的学期返回空课表和提示。"""
        data = source.snapshot()["data"]
        metadata = data.get("metadata", {})
        student = metadata.get("student_id")
        if not student:
            raise HTTPException(409, "请先同步教务课表，再切换学期。")
        term = next((item for item in metadata.get("semesters", []) if item["id"] == semester_id), {})
        if semester_id == metadata.get("semester_id"):
            return {"semester_id": semester_id, "semester": term.get("name") or metadata.get("semester", ""), "week_count": metadata.get("week_count") or DEFAULT_WEEKS,
                    "units": metadata.get("units") or DEFAULT_UNITS, "timetable": data.get("timetable", []), "issues": []}
        cancelled = threading.Event()
        with context.auth.authenticated_client("ids", target="timetable", cancelled=cancelled) as client:
            result = parse(table(Remote(client, cancelled, HOSTS), student, semester_id), term.get("name", ""))
        return {"semester_id": semester_id, "semester": term.get("name") or result["metadata"]["semester"], "week_count": result["metadata"].get("week_count") or DEFAULT_WEEKS,
                "units": result["metadata"].get("units") or DEFAULT_UNITS, "timetable": result["timetable"], "issues": result.get("issues", [])}

    return router


def stop(context):
    if _source is not None:
        _source.close()
