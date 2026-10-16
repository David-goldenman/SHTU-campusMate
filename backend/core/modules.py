import importlib.util
import json
import re
import shutil
import sys
import threading
import types
import uuid
from urllib.parse import unquote
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .context import ModuleContext, ModuleSecrets
from .paths import DATA, MODULES


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=40)
    category: Literal["dashboard", "mail", "timetable", "courses", "assignments", "notifications", "assistant"]
    api_version: Literal[1]


@dataclass
class Entry:
    info: dict
    folder: Path
    context: ModuleContext | None = None
    package: types.ModuleType | None = None
    app: FastAPI | None = None
    requests: int = 0


class ModuleManager:
    def __init__(self, store, vault, auth, ai, root=MODULES, data=DATA, exception_handlers=None):
        self.store, self.vault, self.auth, self.ai = store, vault, auth, ai
        self.root, self.data = Path(root).resolve(), Path(data).resolve()
        self.exception_handlers = exception_handlers or {}
        self.entries: dict[str, Entry] = {}
        self.lock = threading.RLock()
        sys.dont_write_bytecode = True
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self):
        with self.lock:
            return {"modules": [dict(entry.info) for entry in self.entries.values()]}

    def _idle(self, entries):
        if any(entry.requests for entry in entries):
            raise HTTPException(409, "模块仍有请求正在执行，请完成后重试。")

    def _stop(self, entry):
        entry.app = None
        entry.info.update(status="disabled", frontend_url=None)
        if entry.package and hasattr(entry.package, "stop"):
            entry.package.stop(entry.context)
        if entry.context:
            entry.context.store.close()
            entry.context = None
        if entry.package:
            prefix = entry.package.__name__
            for name in list(sys.modules):
                if name == prefix or name.startswith(prefix + "."):
                    del sys.modules[name]
            entry.package = None

    def _load(self, folder):
        info = {"id": folder.name, "name": folder.name, "version": "", "category": "dashboard", "enabled": False, "status": "error", "frontend_url": None}
        entry = Entry(info, folder)
        try:
            if not folder.resolve().is_relative_to(self.root) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", folder.name):
                raise ValueError("模块目录名称或位置不符合规范。")
            manifest = Manifest.model_validate(json.loads((folder / "module.json").read_text(encoding="utf-8")))
            if manifest.id != folder.name:
                raise ValueError("module.json 的 id 必须与目录名称一致。")
            if manifest.id == "reload":
                raise ValueError("reload 是框架保留的模块标识。")
            info.update(manifest.model_dump())
            frontend, backend = folder / "web" / "index.js", folder / "server" / "__init__.py"
            for path in (frontend, backend):
                if not path.resolve().is_relative_to(folder.resolve()):
                    raise ValueError("模块入口必须位于自己的目录内。")
            if not frontend.is_file() and not backend.is_file():
                raise ValueError("模块至少需要 web/index.js 或 server/__init__.py 入口。")
            info["enabled"] = self.store.read("modules", {}).get(manifest.id, True)
            if not info["enabled"]:
                info["status"] = "disabled"
                return entry
            revision = uuid.uuid4().hex
            data_dir = self.data / "modules" / manifest.id
            data_dir.mkdir(parents=True, exist_ok=True)
            entry.context = ModuleContext(manifest.id, self.store.for_module(manifest.id), ModuleSecrets(self.vault, manifest.id), data_dir, self.auth, self.ai, self.read_api)
            if backend.is_file():
                name = "framework_module_" + manifest.id.replace("-", "_") + "_" + revision
                spec = importlib.util.spec_from_file_location(name, backend, submodule_search_locations=[str(backend.parent)])
                entry.package = importlib.util.module_from_spec(spec)
                sys.modules[name] = entry.package
                # Reload reads source directly, including edits made within the same second.
                exec(compile(backend.read_text(encoding="utf-8"), str(backend), "exec"), entry.package.__dict__)
                router = entry.package.create_router(entry.context)
                if not isinstance(router, APIRouter):
                    raise ValueError("create_router(context) 必须返回 APIRouter。")
                entry.app = FastAPI(title=manifest.name, version=manifest.version, docs_url=None, redoc_url=None, exception_handlers=self.exception_handlers)
                entry.app.include_router(router)
                if hasattr(entry.package, "start"):
                    entry.package.start(entry.context)
            info.update(status="ready", revision=revision, frontend_url=f"/module-assets/{manifest.id}/{revision}/web/index.js?v={revision}" if frontend.is_file() else None)
        except Exception as error:
            try:
                self._stop(entry)
            except Exception as stop_error:
                info.update(status="error", error=f"模块停止失败（{type(stop_error).__name__}），请检查 stop(context)。")
                return entry
            info.update(status="error", error=str(error) if type(error) is ValueError else f"模块加载失败（{type(error).__name__}）。")
        return entry

    def reload(self):
        with self.lock:
            self.close()
            for folder in sorted(self.root.iterdir()):
                if folder.is_dir() and (folder / "module.json").is_file():
                    entry = self._load(folder)
                    self.entries[entry.info["id"]] = entry
            return self.list()

    def set_enabled(self, module_id, enabled):
        with self.lock:
            entry = self.entries.get(module_id)
            if not entry:
                raise HTTPException(404, "模块尚未安装，请先刷新模块。")
            self._idle([entry])
            try:
                self._stop(entry)
            except Exception:
                entry.info.update(status="error", error="模块停止失败，请检查 stop(context)。")
                raise HTTPException(409, "模块停止失败，请检查 stop(context) 后重试。") from None
            values = self.store.read("modules", {})
            values[module_id] = enabled
            self.store.write("modules", values)
            self.entries[module_id] = self._load(entry.folder)
            return self.list()

    def close(self):
        with self.lock:
            self._idle(self.entries.values())
            errors = []
            for entry in self.entries.values():
                try:
                    self._stop(entry)
                except Exception:
                    entry.info.update(status="error", error="模块停止失败，请检查 stop(context)。")
                    errors.append(entry.info["id"])
            if errors:
                raise HTTPException(409, "模块停止失败：" + ", ".join(errors))
            self.entries.clear()

    def clear_data(self):
        with self.lock:
            self.close()
            self.store.clear_modules()
            self.vault.delete_prefix("module:")
            directory = (self.data / "modules").resolve()
            if not directory.is_relative_to(self.data):
                raise ValueError("模块数据目录超出项目私有目录。")
            if directory.exists():
                shutil.rmtree(directory)

    def asset(self, module_id, revision, path):
        with self.lock:
            entry = self.entries.get(module_id)
            if not entry or entry.info["status"] != "ready" or entry.info.get("revision") != revision:
                raise HTTPException(404, "模块已停用或版本已更新，请刷新页面。")
            root = (entry.folder / "web").resolve()
            file = (root / path).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                raise HTTPException(404, "模块资源不存在。")
            return file

    def _begin_request(self, module_id):
        with self.lock:
            entry = self.entries.get(module_id)
            if entry and entry.app and entry.info["status"] == "ready":
                entry.requests += 1
                return entry

    def _end_request(self, entry):
        with self.lock:
            entry.requests -= 1

    async def read_api(self, module_id, path="/snapshot"):
        """Call another module's public GET API through the same HTTP lifecycle."""
        parts = unquote(path.split("?", 1)[0]).split("/")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", module_id) or not path.startswith("/") or path.startswith("//") or any(part in {".", ".."} for part in parts) or "\\" in path or "#" in path:
            raise ValueError("模块读取需要合法模块 ID 和模块内相对路径。")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self), base_url="http://modules.local") as client:
            return await client.get("/" + module_id + path)

    def authorize_write(self, request):
        parts = request.url.path.split("/")
        if len(parts) < 6 or parts[1:4] != ["api", "v1", "modules"]:
            return False
        entry = self.entries.get(parts[4])
        hook = getattr(entry.package, "authorize_write", None) if entry and entry.app else None
        return bool(hook and hook(entry.context, request))

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        path = scope["path"][len(scope.get("root_path", "")):]
        module_id = path.lstrip("/").split("/", 1)[0]
        entry = await run_in_threadpool(self._begin_request, module_id)
        if not entry:
            await JSONResponse({"detail": "模块未启用或没有后端入口。"}, status_code=404)(scope, receive, send)
            return
        try:
            nested = {**scope, "root_path": scope.get("root_path", "") + "/" + module_id}
            await entry.app(nested, receive, send)
        finally:
            await run_in_threadpool(self._end_request, entry)
