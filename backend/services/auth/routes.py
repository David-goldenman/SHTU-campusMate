from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .protocols import PROVIDERS


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(max_length=4096)


class LoginOptions(BaseModel):
    target: str | None = None


def create_router(service):
    router = APIRouter(prefix="/auth", tags=["共享认证"])

    def checked(provider):
        if provider not in PROVIDERS:
            raise HTTPException(404, "认证提供方不存在。")
        return provider

    @router.get("/providers")
    def providers():
        return {"providers": service.providers()}

    @router.get("/{provider}/status")
    def status(provider: str):
        return service.get_status(checked(provider))

    @router.put("/{provider}/credentials")
    def credentials(provider: str, body: Credentials):
        return service.save_credentials(checked(provider), body.username, body.password)

    @router.post("/{provider}/login")
    def login(provider: str, body: LoginOptions | None = None):
        return service.login(checked(provider), body.target if body else None)

    @router.post("/{provider}/browser")
    def browser(provider: str, body: LoginOptions | None = None):
        return service.open_browser(checked(provider), body.target if body else None)

    @router.post("/{provider}/import-session")
    def import_session(provider: str, body: LoginOptions | None = None):
        return service.import_session(checked(provider), body.target if body else None)

    @router.delete("/{provider}")
    def forget(provider: str):
        return service.forget(checked(provider))

    return router
