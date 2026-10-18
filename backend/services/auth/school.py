"""Bounded, account-scoped connection of the services sharing school IDS."""
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx

from . import protocols
from .protocols import SERVICES, LoginRequired

TARGET_NAMES = {"blackboard": "Blackboard", "elrc": "虚拟教学社区", "ecourse": "E 云课堂", "timetable": "教务与课表"}


def now():
    return datetime.now(timezone.utc).isoformat()


class SchoolConnections:
    def __init__(self, auth):
        self.auth = auth
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="school-connect")
        self.future = None
        self.cancelled = threading.Event()
        self.closed = False
        state = self.snapshot()
        if state.get("status") in {"connecting", "waiting_for_login"}:
            self.auth.store.write("auth:school_connection", {"status": "interrupted"})

    def snapshot(self):
        return self.auth.store.read("auth:school_connection", {"status": "idle"})

    def cancel(self):
        self.cancelled.set()
        if self.future is not None:
            self.future.cancel()
        state = self.snapshot()
        if state.get("status") in {"connecting", "waiting_for_login"}:
            self.auth.store.write("auth:school_connection", {**state, "status": "interrupted", "active_target": None})

    def watch_browser(self, target):
        """Wait for a user-completed official login; never submit credentials here."""
        with self.auth.locks["ids"]:
            self.cancel()
            cancelled = self.cancelled = threading.Event()
            self.auth.store.write("auth:school_connection", {"status": "waiting_for_login"})
            self.future = self.executor.submit(self._watch_browser, target, cancelled)

    def _watch_browser(self, target, cancelled):
        deadline = time.monotonic() + 600
        while not cancelled.wait(2) and time.monotonic() < deadline:
            with self.auth.locks["ids"]:
                if cancelled.is_set():
                    return
                try:
                    state = protocols.filtered_state("ids", self.auth.browser.state("ids"))
                    with protocols.http_client(state) as client:
                        protocols.validate(client, "ids", target, state)
                    if cancelled.is_set():
                        return
                    # Successful import cancels this watcher and queues the other services.
                    self.auth.import_session("ids", target)
                    return
                except (LoginRequired, httpx.HTTPError):
                    continue
                except Exception:
                    break
        with self.auth.locks["ids"]:
            if not cancelled.is_set():
                self.auth.store.write("auth:school_connection", {"status": "interrupted"})

    def start(self, *, completed_target=None, reset=True):
        with self.auth.locks["ids"]:
            if self.closed:
                return
            owner = self.auth.get_account_revision("ids")
            current = self.snapshot()
            if self.future is not None and not self.future.done() and not self.cancelled.is_set() and current.get("owner") == owner:
                return
            self.cancel()
            cancelled = self.cancelled = threading.Event()
            if reset:
                self.auth.store.delete("auth:recovery:ids")
                for target in SERVICES:
                    state = self.auth._saved_state("ids", target)
                    if state.get("blocked"):
                        self.auth.store.write("auth:target:ids:" + target, {**state, "blocked": False})
            identity = self.auth.vault.get("auth:identity:ids").get("subject")
            if not self.auth.vault.get("auth:session:ids") and not self.auth.get_status("ids")["automatic_recovery"]:
                raise LoginRequired("请先登录一次学校账号，再自动连接校内服务。")
            token = secrets.token_hex(12)
            self.auth.store.write("auth:school:auto_connect", True)
            self.auth.store.write("auth:school_connection", {"status": "connecting", "job_id": token, "owner": owner,
                                  "started_at": now(), "completed": 0, "total": len(SERVICES)})
            self.future = self.executor.submit(self._run, token, owner, identity, cancelled, completed_target)

    def _run(self, token, owner, identity, cancelled, completed_target):
        completed = 0
        for target in SERVICES:
            with self.auth.locks["ids"]:
                state = self.snapshot()
                if cancelled.is_set() or state.get("job_id") != token or self.auth.get_account_revision("ids") != owner:
                    return
                self.auth.store.write("auth:school_connection", {**state, "active_target": target})
                if target != completed_target:
                    try:
                        with self.auth.authenticated_client("ids", target=target, cancelled=cancelled):
                            pass
                    except LoginRequired as error:
                        # Authentication records its own target-level pause; other services still get checked.
                        self.auth._failure("ids", target, error)
                    except Exception as error:
                        message = "该服务暂时无法连接，请检查校园网络后重试。" if isinstance(error, httpx.HTTPError) else "该服务暂时无法验证，请稍后重试。"
                        self.auth._record("ids", "error", target, message, checked_at=now())
                # A first connection may establish the owner. A later account change cancels the old job.
                if identity is None:
                    identity = self.auth.vault.get("auth:identity:ids").get("subject")
                    owner = self.auth.get_account_revision("ids")
                if cancelled.is_set() or self.auth.get_account_revision("ids") != owner:
                    return
                completed += 1
                current = self.snapshot()
                if current.get("job_id") != token:
                    return
                self.auth.store.write("auth:school_connection", {**current, "owner": owner, "completed": completed})
        with self.auth.locks["ids"]:
            current = self.snapshot()
            if not cancelled.is_set() and current.get("job_id") == token and self.auth.get_account_revision("ids") == owner:
                self.auth.store.write("auth:school_connection", {**current, "status": "complete", "active_target": None, "finished_at": now()})

    def resume(self):
        if self.auth.store.read("auth:school:auto_connect", False):
            try:
                self.start(reset=False)
            except LoginRequired:
                pass

    def close(self):
        self.closed = True
        self.cancel()
        self.executor.shutdown(wait=True, cancel_futures=True)
