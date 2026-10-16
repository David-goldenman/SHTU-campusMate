import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from ..auth import LoginRequired, VerificationRequired
from .data import digest, validate_bundle
from .remote import Remote


class Source:
    def __init__(self, context, provider, hosts, fetch, target=None):
        self.context, self.provider, self.hosts, self.fetch, self.target = context, provider, hosts, fetch, target
        self.cancelled, self.lock = threading.Event(), threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=context.id)
        self.future = None
        state = context.store.read("sync", {})
        if state.get("status") == "syncing":
            context.store.write("sync", {**state, "status": "error", "message": "上次同步已中断，请再次同步。"})

    def owner(self):
        account = self.context.auth.get_status(self.provider)
        return digest(account["account_revision"])

    def snapshot(self):
        with self.lock:
            saved = self.context.store.read("snapshot", {})
            owner = self.owner()
            state = self.context.store.read("sync", {})
            if state.get("owner") != owner:
                state = {"status": "not_connected", "message": "请在设置连接账号，然后同步。"}
            if saved.get("owner") != owner:
                saved = {"data": validate_bundle({}), "updated_at": None}
            return {key: value for key, value in {**state, "data": saved["data"], "updated_at": saved["updated_at"]}.items() if key != "owner"}

    def sync(self):
        with self.lock:
            if self.cancelled.is_set():
                raise HTTPException(409, "模块正在停止。")
            if self.future is not None and not self.future.done():
                return {"queued": False, "status": "syncing"}
            self.context.store.write("sync", {"status": "syncing", "owner": self.owner()})
            self.future = self.executor.submit(self.run)
            return {"queued": True, "status": "syncing"}

    def run(self):
        owner = self.owner()
        previous = self.snapshot()["data"]
        try:
            with self.context.auth.authenticated_client(self.provider, target=self.target) as client:
                remote = Remote(client, self.cancelled, self.hosts)
                data = validate_bundle(self.fetch(remote, previous))
            with self.lock:
                if self.cancelled.is_set() or owner != self.owner():
                    return
                self.context.store.write("snapshot", {"owner": owner, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()})
                self.context.store.write("sync", {"status": "partial" if data["issues"] else "ready", "owner": owner})
        except Exception as error:
            if self.cancelled.is_set():
                return
            status = "verification_required" if isinstance(error, VerificationRequired) else "login_required" if isinstance(error, LoginRequired) else "error"
            if isinstance(error, LoginRequired):
                message = str(error)
            elif isinstance(error, HTTPException):
                message = str(error.detail)
            elif isinstance(error, httpx.HTTPError):
                message = "来源网络请求失败，已保留缓存。"
            else:
                message = "来源数据处理失败（" + type(error).__name__ + "），已保留缓存。"
            self.context.store.write("sync", {"status": status, "message": message, "owner": owner})

    def router(self):
        router = APIRouter()
        router.add_api_route("/snapshot", self.snapshot, methods=["GET"])
        router.add_api_route("/sync", self.sync, methods=["POST"], status_code=202)
        return router

    def close(self):
        self.cancelled.set()
        self.executor.shutdown(wait=True, cancel_futures=True)


async def snapshots(context, modules):
    import asyncio
    values = await asyncio.gather(*(context.api(module) for module in modules))
    result, unavailable = {}, []
    for name, response in zip(modules, values):
        if response.status_code == 200:
            result[name] = response.json()
        else:
            unavailable.append(name)
    return result, unavailable
