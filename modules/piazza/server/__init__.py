"""Manual, resumable Piazza collection using shared authentication and module state."""
import threading
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.services.auth import LoginRequired
from backend.services.campus.accounts import AccountCache

from .courses import course_catalog, school_reference
from .source import Piazza, identifier, parse_post
from . import campus

_source = None


class Course(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=200)


class Courses(BaseModel):
    model_config = ConfigDict(extra="forbid")
    courses: list[Course] = Field(max_length=30)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({course.id for course in self.courses}) != len(self.courses):
            raise ValueError("课程 ID 不能重复。")
        return self


class Collect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, le=100000)


class ReadState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: bool


class Semester(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)


class Discover(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_semester: Semester | None = None


def create_router(context):
    global _source
    router = APIRouter()
    lock = threading.Lock()
    accounts = AccountCache(context, "piazza")
    collection = None

    def selected(course_id, current):
        identifier(course_id)
        if not any(course["id"] == course_id for course in current.store.read("courses", [])):
            raise HTTPException(404, "请先保存要关注的 Piazza 课程。")

    @router.get("/courses")
    def courses():
        current = accounts.capture()
        result = {"courses": current.store.read("courses", []), "status": current.store.read("status", {})}
        for report in result['status'].values():
            if report.get('status') == 'syncing' and (collection is None or collection.done()):
                report.update(status='error', next_offset=report['offset'], message='上次采集已停止，已保存的帖子保留，可重试本页。')
        accounts.check(current)
        return result

    @router.get("/catalog")
    def catalog():
        current = accounts.capture()
        result = current.store.read("catalog", {"courses": [], "reference_semester": None, "checked_at": None})
        accounts.check(current)
        return result

    @router.post("/discover")
    def discover(body: Discover):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Piazza 正在读取数据，请稍后再试。")
        try:
            current = accounts.capture()
            reference = school_reference(body.current_semester.model_dump() if body.current_semester else None)
            with context.auth.authenticated_client("piazza") as client:
                accounts.check(current)
                available = course_catalog(Piazza(client).courses(), reference)
            result = {"courses": available, "reference_semester": reference,
                      "checked_at": datetime.now(UTC).isoformat()}
            accounts.check(current)
            current.store.write("catalog", result)
            return result
        finally:
            lock.release()

    @router.put("/courses")
    def save_courses(body: Courses):
        with lock:
            accounts.capture().store.write("courses", [course.model_dump() for course in body.courses])
        return courses()

    @router.post("/courses/{course_id}/sync", status_code=202)
    def sync(course_id: str, body: Collect):
        nonlocal collection
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Piazza 正在采集，请稍后再试。")
        try:
            current = accounts.capture()
            selected(course_id, current)
            if _source.cancelled.is_set():
                raise HTTPException(409, '模块正在停止。')
            reports = current.store.read('status', {})
            reports[course_id] = {'course_id': course_id, 'status': 'syncing', 'offset': body.offset,
                                  'next_offset': body.offset, 'message': '正在后台采集，可离开此页。'}
            current.store.write('status', reports)
            collection = _source.executor.submit(collect, course_id, body, current)
            if getattr(context, 'runtime', None):
                context.runtime.watch('帖子采集', collection)
            return reports[course_id]
        except Exception:
            lock.release()
            raise

    def collect(course_id, body, current):
        try:
            accounts.check(current)
            if _source.cancelled.is_set():
                return
            posts = current.store.read("posts:" + course_id, {})
            failures, saved = [], 0
            with context.auth.authenticated_client("piazza", cancelled=_source.cancelled) as client:
                accounts.check(current)
                source = Piazza(client)
                rows = source.feed(course_id, body.offset)
                for row in rows:
                    accounts.check(current)
                    if _source.cancelled.is_set():
                        return
                    cid = identifier(row["id"])
                    try:
                        raw = source.post(course_id, cid)
                        post = parse_post(raw, course_id)
                        if post["id"] != cid and str(raw.get("nr")) != cid:
                            raise ValueError("Piazza 返回了其他帖子。")
                        old = posts.get(post["id"], {})
                        same = all(old.get(key) == post[key] for key in ("title", "body", "attachments"))
                        post["read"] = bool(old.get("read")) if same else False
                        posts[post["id"]] = post
                        # Commit each successful post; a later login/network error cannot erase it.
                        accounts.check(current)
                        if _source.cancelled.is_set():
                            return
                        current.store.write("posts:" + course_id, posts)
                        saved += 1
                    except LoginRequired:
                        raise
                    except (ValueError, RuntimeError, httpx.HTTPError):
                        failures.append(cid)
            report = {"course_id": course_id, "status": "partial" if failures else "ready",
                      "saved": saved, "failed_ids": failures, "offset": body.offset,
                      "next_offset": body.offset if failures else body.offset + len(rows) if len(rows) == 20 else None,
                      "checked_at": datetime.now(UTC).isoformat(),
                      "message": "部分帖子失败；继续采集会重试本页。" if failures else "本页已更新；按更新时间分页，可能重复，缓存会去重。"}
            accounts.check(current)
            if _source.cancelled.is_set():
                return
            status = current.store.read("status", {})
            status[course_id] = report
            current.store.write("status", status)
            return report
        except Exception:
            accounts.check(current)
            status = current.store.read("status", {})
            status[course_id] = {"status": "error", "offset": body.offset, "next_offset": body.offset,
                                 "message": "采集未完成，已保存的帖子保留；请检查连接后重试。"}
            current.store.write("status", status)
            raise
        finally:
            lock.release()

    @router.get("/posts")
    def posts(course_id: str = Query(..., max_length=100),
              offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
              level: Literal["all", "high", "medium", "normal"] = "all",
              q: str = Query("", max_length=200)):
        current = accounts.capture()
        selected(course_id, current)
        items = list(current.store.read("posts:" + course_id, {}).values())
        items = [item for item in items if (level == "all" or item["level"] == level)
                 and (not q or q.casefold() in (item["title"] + "\n" + item["body"]).casefold())]
        items.sort(key=lambda item: (item.get("updated_at") or item.get("created_at") or 0, item["id"]), reverse=True)
        accounts.check(current)
        return {"items": items[offset:offset + limit], "total": len(items),
                "next_offset": offset + limit if offset + limit < len(items) else None}

    @router.put("/courses/{course_id}/posts/{post_id}/read")
    def mark_read(course_id: str, post_id: str, body: ReadState):
        current = accounts.capture()
        selected(course_id, current)
        with lock:
            posts = current.store.read("posts:" + course_id, {})
            if post_id not in posts:
                raise HTTPException(404, "帖子不存在。")
            posts[post_id]["read"] = body.read
            accounts.check(current)
            current.store.write("posts:" + course_id, posts)
        return {"read": body.read}

    router.include_router(campus.create_router(context))
    _source = campus._source
    return router


def stop(context):
    campus.stop(context)
