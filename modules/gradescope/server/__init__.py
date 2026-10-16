from urllib.parse import urljoin
from fastapi import HTTPException, Query

from backend.services.campus import Remote, Source
from backend.services.campus.files import download
from .reader import BASE, HOSTS, detail, fetch

_source = None


def create_router(context):
    global _source
    _source = Source(context, "gradescope", HOSTS, fetch)
    router = _source.router()

    @router.get("/assignment")
    def assignment(course_id: int = Query(gt=0), assignment_id: int = Query(gt=0)):
        with context.auth.authenticated_client("gradescope") as client:
            item, _ = detail(Remote(client, _source.cancelled, HOSTS), course_id, assignment_id)
            return {"assignment": {key: value for key, value in item.items() if key != "materials"}, "materials": item["materials"]}

    @router.get("/file")
    def file(course_id: int = Query(gt=0), assignment_id: int = Query(gt=0)):
        def resolve(remote):
            _, data = detail(remote, course_id, assignment_id)
            template = data["assignment"].get("template_url") if data else None
            if not isinstance(template, str) or not template:
                raise HTTPException(404, "该作业当前没有题目文件。")
            return urljoin(BASE, template), None
        return download(context, "gradescope", HOSTS, resolve, _source.cancelled)

    return router


def stop(context):
    if _source is not None:
        _source.close()
