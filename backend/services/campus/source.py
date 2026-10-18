import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from ..auth import LoginRequired, VerificationRequired
from ..auth.network import failure_context
from .data import digest, validate_bundle
from .remote import Remote


class Source:
    def __init__(self, context, provider, hosts, fetch, target=None, state_prefix="", network_target=None, stale_after=21600):
        self.context, self.provider, self.hosts, self.fetch, self.target = context, provider, hosts, fetch, target
        self.network_target = network_target
        self.sync_key, self.snapshot_key = state_prefix + "sync", state_prefix + "snapshot"
        self.stale_after = stale_after
        self.cancelled, self.lock = threading.Event(), threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=context.id)
        self.future = None
        state = context.store.read(self.sync_key, {})
        if state.get("status") == "syncing":
            context.store.write(self.sync_key, {**state, "status": "error", "message": "上次同步已中断，请再次同步。"})

    def owner(self):
        return digest(self.context.auth.get_account_revision(self.provider))

    def snapshot(self):
        with self.lock:
            saved = self.context.store.read(self.snapshot_key, {})
            owner = self.owner()
            state = self.context.store.read(self.sync_key, {})
            if state.get("owner") != owner:
                state = {"status": "not_connected", "message": "请在设置连接账号，然后同步。"}
            if saved.get("owner") != owner:
                saved = {"data": validate_bundle({}), "updated_at": None}
            result = {key: value for key, value in {**state, "data": saved["data"], "updated_at": saved["updated_at"]}.items() if key != "owner"}
            # stale 降级：快照超期且当前状态不是正在同步/出错时，标记为 cached 并后台静默同步
            if self._is_stale(saved) and result["status"] == "ready":
                result["status"] = "cached"
                result["message"] = "本地缓存，待核实"
                self._background_sync()
            return result

    def _is_stale(self, saved):
        if not saved.get("updated_at"):
            return False
        from datetime import datetime, timezone
        try:
            updated = datetime.fromisoformat(saved["updated_at"].replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - updated).total_seconds() > self.stale_after
        except (ValueError, AttributeError):
            return False

    def _background_sync(self):
        with self.lock:
            if self.future is not None and not self.future.done():
                return
            self.context.store.write(self.sync_key, {"status": "syncing", "owner": self.owner()})
            self.future = self.executor.submit(self.run)
            if getattr(self.context, 'runtime', None):
                self.context.runtime.watch(self.sync_key, self.future)

    def sync(self):
        with self.lock:
            if self.cancelled.is_set():
                raise HTTPException(409, "模块正在停止。")
            if self.future is not None and not self.future.done():
                return {"queued": False, "status": "syncing"}
            self.context.store.write(self.sync_key, {"status": "syncing", "owner": self.owner()})
            self.future = self.executor.submit(self.run)
            if getattr(self.context, 'runtime', None):
                self.context.runtime.watch(self.sync_key, self.future)
            return {"queued": True, "status": "syncing"}

    def run(self):
        owner = self.owner()
        previous = self.snapshot()["data"]
        observed_network_error = None
        try:
            def read(client):
                nonlocal observed_network_error
                remote = Remote(client, self.cancelled, self.hosts)
                try:
                    return validate_bundle(self.fetch(remote, previous))
                finally:
                    observed_network_error = remote.network_error
            data = self.context.auth.read_with_recovery(self.provider, read, target=self.target, cancelled=self.cancelled)
            with self.lock:
                if self.cancelled.is_set() or owner != self.owner():
                    return
                self.context.store.write(self.snapshot_key, {"owner": owner, "data": data, "updated_at": datetime.now(timezone.utc).isoformat()})
                state = {"status": "partial" if data["issues"] else "ready", "owner": owner}
                if self.network_target and observed_network_error is not None:
                    state.update(status="partial", message="部分来源网络请求失败，已保留可用内容。",
                                 network_failure=failure_context(observed_network_error, self.network_target))
                self.context.store.write(self.sync_key, state)
        except Exception as error:
            if self.cancelled.is_set():
                return
            status = "verification_required" if isinstance(error, VerificationRequired) else "login_required" if isinstance(error, LoginRequired) else "error"
            if isinstance(error, LoginRequired):
                message = str(error)
            elif isinstance(error, HTTPException):
                message = str(error.detail)
            elif observed_network_error is not None or isinstance(error, httpx.RequestError):
                message = "来源网络请求失败，已保留缓存。"
            elif isinstance(error, httpx.HTTPStatusError):
                message = f"来源返回 HTTP {error.response.status_code}，已保留缓存，请稍后重试或检查访问权限。"
            else:
                message = "来源数据处理失败（" + type(error).__name__ + "），已保留缓存。"
            with self.lock:
                if self.cancelled.is_set() or owner != self.owner():
                    return
                state = {"status": status, "message": message, "owner": owner}
                if self.network_target and status == "error":
                    failure = failure_context(error if isinstance(error, httpx.RequestError) else observed_network_error, self.network_target)
                    if failure:
                        state["network_failure"] = failure
                self.context.store.write(self.sync_key, state)

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
            try:
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError
                value["data"] = validate_bundle(value.get("data"))
                result[name] = value
            except (ValueError, TypeError):
                unavailable.append(name)
        else:
            unavailable.append(name)
    return result, unavailable
