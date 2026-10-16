from fastapi import APIRouter
from pydantic import BaseModel

from .service import Notifications

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
    def snapshot():
        return _service.snapshot()

    @router.post("/generate")
    def generate(force: bool = False):
        return _service.generate(force)

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
