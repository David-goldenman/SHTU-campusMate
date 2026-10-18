from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.services.campus import Remote, Source
from backend.services.campus.accounts import AccountCache
from backend.services.campus.files import download
from .resources import BASE, IDENTIFIER
from .reader import fetch, parse_post, rpc
from .snapshot import with_watched_courses

_source = None


def create_router(context):
    global _source
    _source = Source(context, "piazza", ["piazza.com"], fetch, state_prefix="campus:")
    accounts = AccountCache(context, "piazza")
    router = APIRouter()

    @router.get("/snapshot")
    def snapshot():
        current = accounts.capture()
        value = _source.snapshot()
        result = with_watched_courses(current, value)
        accounts.check(current)
        return result

    router.add_api_route("/sync", _source.sync, methods=["POST"], status_code=202)

    @router.get('/file')
    def file(material_id: str = Query(min_length=1, max_length=400), inline: bool = False) -> FileResponse:
        """Read a file only from the current account's synchronized resource catalog."""
        owner = _source.owner()
        item = next((item for item in _source.snapshot()['data']['materials'] if item['id'] == material_id and item.get('download_url')), None)
        if item is None:
            raise HTTPException(404, '课件不在当前账号的 Piazza 缓存中，请先同步。')
        course_id, resource_id = item['source_course_id'], item['source_id']
        if not IDENTIFIER.fullmatch(course_id) or not IDENTIFIER.fullmatch(resource_id):
            raise HTTPException(422, 'Piazza 课件标识不正确，请重新同步。')
        url = BASE + '/class_profile/get_resource/' + course_id + '/' + resource_id
        response = download(context, 'piazza', _source.hosts, lambda remote: (url, item['title']), _source.cancelled, max_bytes=30 * 1024 * 1024)
        try:
            latest = next((row for row in _source.snapshot()['data']['materials'] if row['id'] == material_id), None)
            if owner != _source.owner() or latest != item:
                raise HTTPException(409, '账号或课件目录已更新，请重新读取。')
            if inline and response.media_type == 'application/pdf':
                response.headers['content-disposition'] = response.headers['content-disposition'].replace('attachment;', 'inline;', 1)
            return response
        except BaseException:
            Path(response.path).unlink(missing_ok=True)
            raise

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
