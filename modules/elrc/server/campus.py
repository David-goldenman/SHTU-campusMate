from fastapi import APIRouter, HTTPException, Query

from backend.services.campus import Remote, Source
from .reader import fetch, recording, transcript
from .snapshot import with_library

_source = None


def create_router(context):
    global _source
    _source = Source(context, "ids", ["elrc.shanghaitech.edu.cn"], fetch, target="elrc", state_prefix="campus:")
    if context.store.read("library_owner") is None:
        context.store.write("library_owner", _source.owner())
    router = APIRouter()

    @router.get("/snapshot")
    def snapshot():
        value = _source.snapshot()
        return with_library(context, value) if context.store.read("library_owner") == _source.owner() else value

    router.add_api_route("/sync", _source.sync, methods=["POST"], status_code=202)

    @router.get("/recording")
    def get_recording(course_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,120}$"), recording_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,120}$")):
        owner = _source.owner()
        canonical = "elrc:recording:" + course_id + ":" + recording_id
        if not any(item["id"] == canonical for item in _source.snapshot()["data"]["lessons"]):
            raise HTTPException(404, "录播不在当前账号目录中，请先同步。")
        with context.auth.authenticated_client("ids", target="elrc") as client:
            value = recording(Remote(client, _source.cancelled, _source.hosts), course_id, recording_id)
        with _source.lock:
            cached = context.store.read(_source.snapshot_key, {})
            if cached.get("owner") != owner or owner != _source.owner():
                raise HTTPException(409, "账号已更新，请重新读取。")
            for item in cached["data"]["lessons"]:
                if item["id"] == canonical:
                    item["stream_ids"] = [stream["id"] for lesson in value["lessons"] for stream in lesson["streams"]]
            context.store.write(_source.snapshot_key, cached)
        return value

    @router.get("/transcript")
    def get_transcript(stream_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,120}$")):
        owner = _source.owner()
        lessons = _source.snapshot()["data"]["lessons"]
        if not any(stream_id in item.get("stream_ids", []) for item in lessons):
            raise HTTPException(404, "请先读取当前录播课次，再选择转写。")
        with context.auth.authenticated_client("ids", target="elrc") as client:
            value = transcript(Remote(client, _source.cancelled, _source.hosts), stream_id)
        with _source.lock:
            cached = context.store.read(_source.snapshot_key, {})
            if cached.get("owner") != owner or owner != _source.owner():
                raise HTTPException(409, "账号已更新，请重新读取。")
            for item in cached["data"]["lessons"]:
                if stream_id in item.get("stream_ids", []):
                    item["body_text"] = "\n".join(line["text"] for line in value["transcript"]) + "\n" + "\n".join(chapter["body_text"] for chapter in value["summary"])
            context.store.write(_source.snapshot_key, cached)
        return value

    return router


def stop(context):
    if _source is not None:
        _source.close()
