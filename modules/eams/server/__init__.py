import re
import threading
from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Query

from backend.services.campus import Remote, Source
from .reader import BASE, INDEX_URL, exams, fetch, index, public_data, read
from .catalogue import search, syllabus

HOSTS = ["eams.shanghaitech.edu.cn"]
_source = None


def create_router(context):
    global _source
    source = _source = Source(context, "ids", HOSTS, fetch, target="timetable")
    router = APIRouter()
    router.add_api_route('/sync', source.sync, methods=['POST'], status_code=202)

    @router.get('/snapshot')
    def snapshot():
        value = source.snapshot()
        return {**value, 'data': public_data(value['data'])}

    def check_owner(owner):
        if owner != source.owner():
            raise HTTPException(409, "账号已更新，请重新同步教务系统数据。")

    @router.get('/course-search')
    def course_search(q: str = Query(min_length=1, max_length=160), page: int = Query(default=1, ge=1, le=100)):
        if not q.strip():
            raise HTTPException(422, '请输入课程名称或代码。')
        owner = source.owner()
        def query(client):
            return search(Remote(client, source.cancelled, HOSTS), q.strip(), page)
        result = context.auth.read_with_recovery('ids', query, target='timetable', cancelled=source.cancelled)
        check_owner(owner)
        return result

    @router.get('/course-info')
    def course_info(syllabus_id: int = Query(gt=0)):
        owner = source.owner()
        def query(client):
            return syllabus(Remote(client, source.cancelled, HOSTS), syllabus_id)
        result = context.auth.read_with_recovery('ids', query, target='timetable', cancelled=source.cancelled)
        check_owner(owner)
        return result

    @router.get("/exams")
    def semester_exams(semester_id: str = Query(pattern=r"^\d{1,12}$"), batch_id: str = Query(default="", pattern=r"^\d{0,12}$")):
        """按学期读取考试安排，供页面切换往年考试。"""
        owner = source.owner()
        data = source.snapshot()["data"]
        check_owner(owner)
        metadata = data.get("metadata", {})
        student = metadata.get("student_id")
        if not student:
            raise HTTPException(409, "请先同步教务系统数据，再切换学期。")
        term = next((item["name"] for item in metadata.get("semesters", []) if item["id"] == semester_id), "")
        if semester_id == metadata.get("semester_id") and not batch_id:
            return {"semester_id": semester_id, "semester": term, "exams": data.get("assignments", []), **metadata.get("exams", {})}
        cancelled = threading.Event()
        with context.auth.authenticated_client("ids", target="timetable", cancelled=cancelled) as client:
            check_owner(owner)
            remote = Remote(client, cancelled, HOSTS)
            page = read(remote, "POST", INDEX_URL, data={"semester.id": semester_id, "semesterId": semester_id, "examBatch.id": batch_id, "tutorRedirectstudentId": student})
            value = index(page)
            target = "/eams/stdExamTable!examTable.action?examBatch.id=" + batch_id + "&tutorRedirectstudentId=" + student if batch_id else value["target"]
            items = exams(read(remote, "GET", urljoin(BASE, target)), term, INDEX_URL)
        check_owner(owner)
        batch = re.search(r"examBatch\.id=(\d+)", target)
        return {"semester_id": semester_id, "semester": term, "batches": value["batches"], "batch_id": batch[1] if batch else "",
                "batch": next((item["name"] for item in value["batches"] if item["id"] == batch[1]), "") if batch else "", "exams": items}

    return router


def stop(context):
    if _source is not None:
        _source.close()
