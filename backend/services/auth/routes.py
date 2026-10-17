from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone

from .protocols import PROVIDERS
from .network import NetworkDiagnostics, explain_failure


class SyncNetworkFailure(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    target: Literal["timetable", "blackboard", "elrc", "ecourse"]
    kind: Literal["dns_error", "tls_error", "timeout", "proxy_error", "protocol_error", "configuration_error", "connection_error"]
    at: datetime
    host: str | None = Field(default=None, max_length=253)


class SyncNetworkFailures(BaseModel):
    failures: list[SyncNetworkFailure] = Field(min_length=1, max_length=6)


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(max_length=4096)


class LoginOptions(BaseModel):
    target: str | None = None


class DeviceConsent(BaseModel):
    confirmation: Literal["REGISTER_THIS_DEVICE"]


def create_router(service):
    router = APIRouter(prefix="/auth", tags=["共享认证"])
    network = NetworkDiagnostics()

    @router.get("/network")
    def network_status():
        return network.snapshot()

    @router.post("/network/check")
    async def check_network():
        return await network.check()

    @router.post("/network/explain")
    async def explain_network(body: SyncNetworkFailures):
        moments = [item.at.replace(tzinfo=timezone.utc) if item.at.tzinfo is None else item.at for item in body.failures]
        after = min(max(moments), datetime.now(timezone.utc))
        report = await network.check(after=after)
        return {"reports": [explain_failure(item.model_dump(mode="json"), report) for item in body.failures]}

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
