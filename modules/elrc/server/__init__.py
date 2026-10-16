"""Course discovery, explicit synchronization and offline evidence API."""
import asyncio
import threading

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from backend.services.campus.accounts import AccountCache

from .catalog import ELRC
from .content import ContentLibrary, now
from . import campus

_source = None


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semester: str = Field(default="current", min_length=1, max_length=100)


class SyncCourse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force: bool = False


def create_router(context):
    global _source
    router = APIRouter()
    lock = threading.Lock()
    accounts = AccountCache(context, "ids")

    def cache():
        current = accounts.capture()
        offline = ELRC(current.data_dir)
        return current, offline, ContentLibrary(offline)
    if context.store.read("sync", {}).get("status") == "syncing":
        context.store.write("sync", {"status": "interrupted", "message": "上次同步中断，可重新同步。"})

    @router.get("/catalog")
    def catalog(semester: str = Query("current", min_length=1, max_length=100)):
        current, offline, library = cache()
        result = offline.catalog(semester)
        accounts.check(current)
        return result

    @router.post("/discover")
    def discover(body: Selection):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "课程同步正在进行，请稍后再试。")
        try:
            current, offline, library = cache()
            with context.auth.authenticated_client("ids", target="elrc") as client:
                accounts.check(current)
                asyncio.run(ELRC(current.data_dir, client).discover_courses(body.semester))
            accounts.check(current)
            return offline.catalog(body.semester)
        finally:
            lock.release()

    @router.get("/sync")
    def sync_status():
        return accounts.capture().store.read("sync", {"status": "idle"})

    @router.get("/courses/{course_id}")
    def course(course_id: str):
        current, offline, library = cache()
        result = library.overview(course_id)
        accounts.check(current)
        return result

    @router.post("/courses/{course_id}/sync")
    def sync(course_id: str, body: SyncCourse):
        current, offline, library = cache()
        selected = library.course(course_id)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "课程同步正在进行，请稍后再试。")
        state = {"status": "syncing", "course_id": course_id, "started_at": now()}
        try:
            current.store.write("sync", state)
            with context.auth.authenticated_client("ids", target="elrc") as client:
                accounts.check(current)
                worker = ContentLibrary(ELRC(current.data_dir, client))

                def progress(lesson):
                    current.store.write("sync", {**state, "lesson": lesson})

                async def run():
                    reviews = await worker.review_catalog()
                    await worker.sync_course(selected, reviews, progress, body.force)

                asyncio.run(run())
            result = library.overview(course_id)
            accounts.check(current)
            current.store.write("sync", {**state, "status": result["status"], "finished_at": now()})
            return result
        except Exception:
            current.store.write("sync", {**state, "status": "error", "message": "同步未完成，已缓存内容保留，可重试。"})
            manifest = library.read(course_id)
            if manifest.get("status") == "syncing":
                library.write(course_id, {**manifest, "status": "partial", "error": "同步中断，请重试。"})
            raise
        finally:
            lock.release()

    @router.get("/courses/{course_id}/lessons/{lesson_id}")
    def lesson(course_id: str, lesson_id: str, offset: int = Query(0, ge=0),
               limit: int = Query(100, ge=1, le=200), q: str = Query("", max_length=200)):
        current, offline, library = cache()
        result = library.lesson(course_id, lesson_id, offset=offset, limit=limit, query=q)
        accounts.check(current)
        return result

    @router.get("/search")
    def search(q: str = Query(..., min_length=1, max_length=200),
               semester: str = Query("current", max_length=100),
               course_id: str | None = Query(None, max_length=100),
               limit: int = Query(12, ge=1, le=12)):
        current, offline, library = cache()
        courses = {item["id"]: item for item in offline.catalog(semester)["courses"]}
        if course_id and course_id not in courses:
            raise HTTPException(400, "课程不在所选学期中。")
        ranked = library.search(q.strip(), courses, course_id=course_id) if q.strip() else []
        ranked.sort(key=lambda item: (-item[0], item[1].source_id))
        accounts.check(current)
        return {"items": [item.model_copy(update={"text": item.text[:4000]}).model_dump()
                          for _, item in ranked[:limit]]}

    router.include_router(campus.create_router(context))
    _source = campus._source
    return router


def stop(context):
    campus.stop(context)
