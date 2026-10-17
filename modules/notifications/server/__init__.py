from fastapi import APIRouter
from pydantic import BaseModel

from .service import Notifications, ImportedNotice

_service = None


class Settings(BaseModel):
    auto_generate: bool


class Read(BaseModel):
    read: bool


def create_router(context):
    global _service
    _service = Notifications(context)
    router = APIRouter()

    @router.get("/snapshot")
    async def snapshot():
        await _service.reconcile_assignments()
        return _service.snapshot()

    @router.post("/generate")
    def generate(force: bool = False):
        return _service.generate(force)

    @router.post('/imports')
    def import_notice(body: ImportedNotice):
        return _service.import_notice(body)

    @router.get('/agent/status')
    async def agent_status():
        response = await context.api('campus-agent', '/status')
        return response.json() if response.status_code == 200 else {'available': False}

    @router.put('/agent/settings')
    async def agent_settings(body: dict):
        response = await context.api('campus-agent', '/settings', method='PUT', body=body)
        return response.json()

    @router.post('/agent/check', status_code=202)
    async def agent_check():
        response = await context.api('campus-agent', '/check', method='POST')
        return response.json()

    @router.post('/proposals/{identity}/{action}')
    async def proposal(identity: str, action: str):
        from fastapi import HTTPException
        if action not in {'accept', 'dismiss'}:
            raise HTTPException(404, '未知操作。')
        response = await context.api('campus-agent', '/proposals/' + identity + '/' + action, method='POST')
        if response.status_code >= 400:
            raise HTTPException(response.status_code, response.json().get('detail', '安排暂时无法更新。'))
        return response.json()

    @router.get("/settings")
    def settings():
        return _service.settings()

    @router.put("/settings")
    def set_settings(body: Settings):
        return _service.set_settings(body.auto_generate)

    @router.put("/{notice_id}/read")
    def mark_read(notice_id: str, body: Read):
        return _service.mark_read(notice_id, body.read)

    return router


def start(context):
    _service.start()


def stop(context):
    if _service is not None:
        _service.close()
