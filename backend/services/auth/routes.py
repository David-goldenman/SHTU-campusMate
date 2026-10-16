from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from .protocols import PROVIDERS


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(max_length=4096)


class LoginOptions(BaseModel):
    target: str | None = None


class DeviceConsent(BaseModel):
    confirmation: Literal["REGISTER_THIS_DEVICE"]


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

    @router.post("/{provider}/refresh")
    def refresh(provider: str, body: LoginOptions | None = None):
        return service.refresh(checked(provider), body.target if body else None)

    @router.post("/ids/device/browser")
    def device_browser():
        return service.open_device_browser()

    @router.post("/ids/device/bind")
    def bind_device(body: DeviceConsent):
        return service.bind_device()

    @router.post("/ids/device/start")
    def start_device(body: DeviceConsent):
        return service.start_device_setup()

    @router.post("/ids/device/recover")
    def recover_device():
        return service.recover_device()

    @router.delete("/ids/device")
    def forget_device():
        return service.forget_device()

    @router.post("/{provider}/import-session")
    def import_session(provider: str, body: LoginOptions | None = None):
        return service.import_session(checked(provider), body.target if body else None)

    @router.delete("/{provider}")
    def forget(provider: str):
        return service.forget(checked(provider))

    return router
