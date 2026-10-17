import argparse
import asyncio
import json
import os
import secrets
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import VERSION, Settings
from .core.modules import ModuleManager
from .core.paths import DATA, MODULES, WEB
from .core.store import Store
from .core.vault import Vault
from .core.backups import Backups
from .core.errors import PublicError, catch_errors, error_response, file_error, http_error, storage_error
from .services.ai import AIService, create_router as ai_router
from .services.ai.harness import Harness
from .services.auth import AuthService, LoginRequired, VerificationRequired, create_router as auth_router


async def login_error(request, error):
    verification = isinstance(error, VerificationRequired)
    return error_response(request, 409 if verification else 401, str(error),
                          code='verification_required' if verification else 'login_required',
                          action='请到设置 → 账号连接，完成官方窗口验证。' if verification else None)


async def network_error(request, error):
    timeout = isinstance(error, httpx.TimeoutException)
    return error_response(request, 504 if timeout else 502, '来源服务响应超时。' if timeout else '无法连接来源服务。', error=error)


async def runtime_error(request, error):
    return error_response(request, 400,
                          str(error) if isinstance(error, PublicError) else '服务未能完成操作，请检查本地设置和来源连接。', error=error)


async def argument_error(request, error):
    return error_response(request, 400, '参数格式与服务要求不一致。', error=error)


async def validation_error(request, error):
    return error_response(request, 422, [{key: item[key] for key in ('loc', 'msg', 'type')} for item in error.errors()])


class ModuleState(BaseModel):
    enabled: bool


class ClearData(BaseModel):
    scope: Literal["credentials", "modules", "all"]
    confirmation: Literal["CLEAR"]


class RestoreBackup(BaseModel):
    confirmation: Literal['RESTORE']


class DeleteBackup(BaseModel):
    confirmation: Literal['DELETE_BACKUP']


def create_app(*, active_port=None, store=None, vault=None, modules_root=MODULES, data_dir=DATA):
    store = store or Store()
    vault = vault or Vault()
    active_port = Settings(port=active_port or store.read("settings", {"port": 16666})["port"]).port
    csrf = secrets.token_urlsafe(32)
    auth, ai = AuthService(vault, store, runtime_dir=Path(data_dir) / 'runtime'), AIService(vault, store)
    errors = {LoginRequired: login_error, VerificationRequired: login_error, httpx.HTTPError: network_error, RuntimeError: runtime_error, ValueError: argument_error, RequestValidationError: validation_error, StarletteHTTPException: http_error, sqlite3.Error: storage_error, OSError: file_error}
    modules = ModuleManager(store, vault, auth, ai, root=modules_root, data=data_dir, exception_handlers=errors)
    backups = Backups(store, data_dir)
    ai.harness = Harness(modules)

    @asynccontextmanager
    async def lifespan(app):
        modules.loop = asyncio.get_running_loop()
        await run_in_threadpool(modules.reload)
        try:
            yield
        finally:
            try:
                await run_in_threadpool(modules.close)
            finally:
                await run_in_threadpool(auth.close)
                store.close()

    app = FastAPI(title="Campus Framework · 共享接口", version=VERSION, docs_url=None, redoc_url=None, openapi_url="/api/openapi.json", lifespan=lifespan, exception_handlers=errors,
                  dependencies=[Security(APIKeyHeader(name="X-Framework-Token", auto_error=False, description="写操作填写 GET /api/v1/bootstrap 返回的 csrf_token。"))])
    app.state.modules, app.state.auth, app.state.ai = modules, auth, ai
    app.state.store, app.state.vault, app.state.port = store, vault, active_port
    app.state.backups = backups
    app.state.launch_id = secrets.token_hex(16)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        hosts = {f"127.0.0.1:{active_port}", f"localhost:{active_port}"}
        origins = {"http://" + host for host in hosts}
        if request.headers.get("host") not in hosts:
            return error_response(request, 403, '仅允许从本机地址访问。')
        if request.headers.get("origin") and request.headers["origin"] not in origins or request.headers.get("sec-fetch-site") == "cross-site":
            return error_response(request, 403, '请求来源不匹配。')
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(request.headers.get("x-framework-token", ""), csrf) and not modules.authorize_write(request):
            return error_response(request, 403, '请刷新工作台后重试。')
        response = await catch_errors(request, call_next)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path == "/api/docs":
            response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    def settings():
        value = {"port": 16666, **store.read("settings", {})}
        return {**value, "active_port": active_port, "restart_required": value["port"] != active_port, "storage": {"directory": ".private", "encryption": "Windows DPAPI / CurrentUser"}}

    @app.get("/api/v1/bootstrap", tags=["框架"], summary="初始化网页与模块清单")
    def bootstrap():
        return {"version": VERSION, "csrf_token": csrf, "settings": settings(), **modules.list()}

    @app.get("/api/v1/health", tags=["框架"], summary="本机启动器就绪检查")
    def health():
        return {"application": "campus-framework", "version": VERSION, "launch_id": app.state.launch_id}

    @app.get("/api/v1/settings", tags=["设置"], summary="读取全局设置与存储说明")
    def get_settings():
        return settings()

    @app.put("/api/v1/settings", tags=["设置"], summary="保存下次启动使用的端口")
    def save_settings(body: Settings):
        store.write("settings", body.model_dump())
        return settings()

    @app.get("/api/v1/modules", tags=["模块"], summary="列出已发现的模块与状态")
    def list_modules():
        return modules.list()

    @app.post("/api/v1/modules/reload", tags=["模块"], summary="释放并重新发现模块")
    def reload_modules():
        return modules.reload()

    @app.put("/api/v1/modules/{module_id}", tags=["模块"], summary="启用或停用一个模块")
    def toggle_module(module_id: str, body: ModuleState):
        return modules.set_enabled(module_id, body.enabled)

    @app.post("/api/v1/data/clear", tags=["设置"], summary="清除项目本地凭据或模块数据")
    def clear_data(body: ClearData):
        backup = None
        with modules.lifecycle_lock:
            try:
                if body.scope in {"modules", "all"}:
                    modules.close()
                    backup = backups.create('before_clear')
                    modules.clear_data()
                else:
                    modules.close()
                if body.scope in {"credentials", "all"}:
                    auth.clear_all()
                    vault.clear()
                    current_ai = ai.settings()
                    store.write('ai:settings', {'enabled': False, 'provider': current_ai['provider'], 'model': current_ai['model']})
                if body.scope == "all":
                    store.clear()
            finally:
                modules.reload()
        return {"cleared": body.scope, 'backup': backup}

    @app.get('/api/v1/data/backups', tags=['设置'], summary='读取本机模块数据备份')
    def list_backups():
        with modules.lifecycle_lock:
            return {'backups': backups.list()}

    @app.post('/api/v1/data/backups', tags=['设置'], summary='创建模块数据备份')
    def create_backup():
        with modules.lifecycle_lock:
            try:
                modules.close()
                return {'backup': backups.create()}
            finally:
                modules.reload()

    @app.post('/api/v1/data/backups/{backup_id}/restore', tags=['设置'], summary='恢复模块数据并保留当前备份')
    def restore_backup(backup_id: str, body: RestoreBackup):
        with modules.lifecycle_lock:
            backups.validate(backup_id)
            try:
                modules.close()
                return backups.restore(backup_id)
            finally:
                modules.reload()

    @app.delete('/api/v1/data/backups/{backup_id}', tags=['设置'], summary='删除指定备份')
    def delete_backup(backup_id: str, body: DeleteBackup):
        with modules.lifecycle_lock:
            backups.delete(backup_id)
        return {'deleted': backup_id}

    @app.get("/module-assets/{module_id}/{revision}/web/{path:path}", include_in_schema=False)
    def module_asset(module_id: str, revision: str, path: str):
        return FileResponse(modules.asset(module_id, revision, path))

    @app.get("/api/docs", include_in_schema=False)
    def docs():
        return get_swagger_ui_html(openapi_url="/api/openapi.json", title="Campus Framework · API")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")

    app.include_router(auth_router(auth), prefix="/api/v1")
    app.include_router(ai_router(ai), prefix="/api/v1")
    app.mount("/api/v1/modules", modules, name="module-api")
    app.mount("/assets", StaticFiles(directory=WEB), name="assets")
    return app


def main():
    parser = argparse.ArgumentParser(description="Campus Framework 本地网页服务")
    parser.add_argument("--port", type=int)
    parser.add_argument("--launch-id", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = create_app(active_port=args.port)
    if args.launch_id:
        app.state.launch_id = args.launch_id
    ready = DATA / "runtime" / "launcher" / "server.json"
    ready.parent.mkdir(parents=True, exist_ok=True)
    state = {"launch_id": app.state.launch_id, "port": app.state.port, "pid": os.getpid()}
    ready.write_text(json.dumps(state), encoding="utf-8")
    print(f"Campus Framework: http://127.0.0.1:{app.state.port}", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=app.state.port, access_log=False)
    finally:
        if ready.exists() and json.loads(ready.read_text(encoding="utf-8")).get("launch_id") == app.state.launch_id:
            ready.unlink()


if __name__ == "__main__":
    main()
