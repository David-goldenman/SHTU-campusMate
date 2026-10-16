from fastapi import APIRouter, HTTPException, Query

from backend.services.campus import Remote, Source
from .reader import fetch, parse_post, rpc
from .snapshot import with_watched_courses

_source = None


def create_router(context):
    global _source
    _source = Source(context, "piazza", ["piazza.com"], fetch, state_prefix="campus:")
    if context.store.read("library_owner") is None:
        context.store.write("library_owner", _source.owner())
    router = APIRouter()

    @router.get("/snapshot")
    def snapshot():
        value = _source.snapshot()
        return with_watched_courses(context, value) if context.store.read("library_owner") == _source.owner() else value

    router.add_api_route("/sync", _source.sync, methods=["POST"], status_code=202)

    @router.get("/post")
    def post(course_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,120}$"), post_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,120}$")):
        canonical = "piazza:" + course_id + ":" + post_id
        if not any(item["id"] == canonical for item in _source.snapshot()["data"]["posts"]):
            raise HTTPException(404, "帖子不在当前账号的近期列表中，请先同步。")
        owner = _source.owner()
        with context.auth.authenticated_client("piazza") as client:
            value = rpc(Remote(client, _source.cancelled, _source.hosts), "content.get", {"nid": course_id, "cid": post_id})
            result = parse_post(value, course_id, post_id)
        with _source.lock:
            cached = context.store.read(_source.snapshot_key, {})
            if cached.get("owner") != owner or owner != _source.owner():
                raise HTTPException(409, "账号已更新，请重新读取。")
            for item in cached["data"]["posts"]:
                if item["id"] == canonical:
                    item["body_text"] = result["body_text"] + "\n" + "\n".join(reply["text"] for reply in result["replies"])
            context.store.write(_source.snapshot_key, cached)
        return result

    return router


def stop(context):
    if _source is not None:
        _source.close()
