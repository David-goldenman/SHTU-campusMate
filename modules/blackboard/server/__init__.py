from urllib.parse import urljoin

from fastapi import HTTPException, Query

from backend.services.campus import Source, SourceError, rows
from backend.services.campus.files import download
from .reader import BASE, checked, fetch

_source = None


class BlackboardSource(Source):
    def snapshot(self):
        value = super().snapshot()
        # Existing cached nulls follow the same meaning as newly synced records.
        for item in value['data']['assignments']:
            if item.get('submitted') is None:
                item['submitted'] = False
        return value


def create_router(context):
    global _source
    _source = BlackboardSource(context, "ids", ["elearning.shanghaitech.edu.cn"], fetch, target="blackboard")
    router = _source.router()

    @router.get("/file")
    def file(material_id: str = Query(min_length=1, max_length=400)):
        item = next((item for item in _source.snapshot()["data"]["materials"] if item["id"] == material_id and item.get("download_url")), None)
        if item is None:
            raise HTTPException(404, "资料不在当前账号缓存中，请先同步。")
        def resolve(remote):
            if item.get("source_path"):
                if not item["source_path"].startswith("/bbcswebdav/"):
                    raise SourceError("Blackboard 附件路径不正确。")
                return urljoin(BASE, item["source_path"]), item["title"]
            cid, content = checked(item["source_course_id"]), checked(item["source_id"])
            attachments = rows(remote.json("GET", BASE + f"/learn/api/public/v1/courses/{cid}/contents/{content}/attachments"), "results")
            if not attachments:
                raise HTTPException(404, "该资料当前没有附件。")
            attachment = checked(attachments[0].get("id"))
            return BASE + f"/learn/api/public/v1/courses/{cid}/contents/{content}/attachments/{attachment}/download", attachments[0].get("fileName") or item["title"]
        return download(context, "ids", _source.hosts, resolve, _source.cancelled, target="blackboard")

    return router


def stop(context):
    if _source is not None:
        _source.close()
