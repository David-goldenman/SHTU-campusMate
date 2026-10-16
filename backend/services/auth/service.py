import threading
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import httpx

from ...core.paths import RUNTIME
from . import protocols
from .browser import VerificationBrowser
from .protocols import LoginRequired, VerificationRequired
from .device import DeviceCredential, PERSON_CENTER


def now():
    return datetime.now(timezone.utc).isoformat()


class AuthService:
    def __init__(self, vault, store, runtime_dir=RUNTIME):
        self.vault = vault
        self.store = store
        self.browser = VerificationBrowser(runtime_dir / 'auth')
        self.locks = {provider: threading.RLock() for provider in protocols.PROVIDERS}
        self.device = DeviceCredential(vault)
        self.setup_cancelled = threading.Event()
        self.setup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ids-device")
        self.setup_future = None
        if self.store.read("auth:device_setup", {}).get("status") == "waiting":
            self.store.write("auth:device_setup", {"status": "interrupted", "message": "上次设备连接已中断，请重新连接或检查待确认凭据。"})

    def _adopt_identity(self, provider, subject, *, migrate=False):
        """Change cache ownership only after a verified account actually changes."""
        if not isinstance(subject, (str, int)) or not str(subject).strip():
            return False
        subject = str(subject).strip().casefold()
        saved = self.vault.get("auth:identity:" + provider)
        accounts = dict(saved.get("accounts", {}))
        revision = accounts.get(subject)
        if revision is None:
            revision = self.store.read("auth:revision:" + provider, "initial") if migrate and not saved.get("subject") else secrets.token_hex(12)
            accounts[subject] = revision
        self.vault.save("auth:identity:" + provider, {"subject": subject, "accounts": accounts})
        self.store.write("auth:revision:" + provider, revision)
        if provider == "ids" and self.device.status()["configured"]:
            key = self.vault.get("auth:device:ids")
            self.store.write("auth:device_enabled", str(key.get("username", "")).strip().casefold() == subject)
        return True

    def _baseline_identity(self, provider):
        """Verify an upgraded installation's old session before replacing it."""
        if self.vault.get("auth:identity:" + provider).get("subject"):
            return
        state = self.vault.get("auth:session:" + provider)
        if not state:
            return
        target = "elrc" if provider == "ids" else protocols.checked_target(provider)
        try:
            with protocols.http_client(state) as client:
                subject = protocols.validate(client, provider, target, state)
                self._adopt_identity(provider, subject, migrate=True)
                self._save_session(provider, client, state)
        except (LoginRequired, RuntimeError, httpx.HTTPError, ValueError):
            pass  # An unverified old owner must never be assigned to a new login.

    def get_status(self, provider: str | None = None):
        if provider is None:
            return {"providers": self.providers()}
        protocols.checked_target(provider)
        credentials = self.vault.get("auth:credentials:" + provider)
        session = self.vault.get("auth:session:" + provider)
        saved = self.store.read("auth:state:" + provider, {})
        result = {
            "id": provider, "name": protocols.PROVIDERS[provider]["name"], "username": credentials.get("username", ""),
            "has_password": bool(credentials.get("password")), "has_session": bool(session),
            "account_revision": self.store.read("auth:revision:" + provider, "initial"),
            "identity_verified": bool(self.vault.get("auth:identity:" + provider).get("subject")),
            "session_revision": self.store.read("auth:session_revision:" + provider, "initial"),
            "status": saved.get("status", "login_required" if credentials or session else "not_connected"),
        }
        for key in ("message", "checked_at", "target"):
            if key in saved:
                result[key] = saved[key]
        if provider == "ids":
            result["targets"] = list(protocols.SERVICES)
            result["device"] = {**self.device.status(), "enabled": self.store.read("auth:device_enabled", True)}
            result["device"]["setup"] = self.store.read("auth:device_setup", {"status": "idle"})
        result["automatic_recovery"] = bool(provider != "coremail" and credentials.get("password")) or bool(provider == "ids" and result["device"]["configured"] and result["device"]["enabled"])
        return result

    def providers(self):
        return [self.get_status(provider) for provider in protocols.PROVIDERS]

    def _record(self, provider, status, target=None, message=None, blocked=False, checked_at=None):
        state = {"status": status, "blocked": blocked}
        if target is not None:
            state["target"] = target
        if message:
            state["message"] = message
        if checked_at:
            state["checked_at"] = checked_at
        self.store.write("auth:state:" + provider, state)

    def _failure(self, provider, target, error):
        status = "verification_required" if isinstance(error, VerificationRequired) else "login_required"
        self._record(provider, status, target, str(error), blocked=True)

    def _save_session(self, provider, client, previous):
        state = protocols.filtered_state(provider, protocols.session_state(client, previous))
        state["saved_at"] = now()
        self.vault.save("auth:session:" + provider, state)
        self.store.write("auth:session_revision:" + provider, secrets.token_hex(12))

    def save_credentials(self, provider: str, username: str, password: str):
        protocols.checked_target(provider)
        username = username.strip()
        if not username:
            raise ValueError("请填写账号。")
        with self.locks[provider]:
            self._baseline_identity(provider)
            self.store.write("auth:revision:" + provider, secrets.token_hex(12))
            identity = self.vault.get("auth:identity:" + provider)
            identity.pop("subject", None)
            self.vault.save("auth:identity:" + provider, identity)
            self.browser.close(provider)
            self.vault.save("auth:credentials:" + provider, {"username": username, "password": password})
            self.vault.delete("auth:session:" + provider)
            if provider == "ids":
                self.store.write("auth:device_enabled", False)
            self._record(provider, "login_required", message="账号已保存，请连接或完成浏览器验证。")
        return self.get_status(provider)

    def _login(self, provider, target, client, state):
        if provider == "ids" and self.device.status()["configured"] and self.store.read("auth:device_enabled", True):
            client.cookies.clear()
            subject = self.device.renew(client)
            verified = protocols.validate(client, provider, target, state)
            if str(verified).strip().casefold() != str(subject).strip().casefold():
                raise VerificationRequired("设备凭据与来源账号不一致，请重新连接学校账号。")
            return subject
        if provider == "coremail":
            raise VerificationRequired("学校邮箱需要在验证窗口登录并导入会话。")
        credentials = self.vault.get("auth:credentials:" + provider)
        if not credentials.get("password"):
            raise LoginRequired("请先保存账号密码，或打开验证窗口完成登录。")
        protocols.login(client, provider, credentials["username"], credentials["password"], target)
        return protocols.validate(client, provider, target, state)

    def login(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            self._baseline_identity(provider)
            state = self.vault.get("auth:session:" + provider)
            with protocols.http_client(state) as client:
                try:
                    subject = self._login(provider, target, client, state)
                except LoginRequired as error:
                    self._failure(provider, target, error)
                    raise
                self._save_session(provider, client, state)
                self._adopt_identity(provider, subject)
            self._record(provider, "ready", target, checked_at=now())
        return self.get_status(provider)

    def open_browser(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            self.browser.open(provider, protocols.browser_url(provider, target))
            self._record(provider, "verification_required", target, "请在验证窗口登录，完成后导入会话。", blocked=True)
        return self.get_status(provider)

    def import_session(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            self._baseline_identity(provider)
            state = protocols.filtered_state(provider, self.browser.state(provider))
            with protocols.http_client(state) as client:
                try:
                    subject = protocols.validate(client, provider, target, state)
                except LoginRequired as error:
                    self._failure(provider, target, error)
                    raise
                self._save_session(provider, client, state)
                if not self._adopt_identity(provider, subject):
                    self.store.write("auth:revision:" + provider, secrets.token_hex(12))
                    identity = self.vault.get("auth:identity:" + provider)
                    identity.pop("subject", None)
                    self.vault.save("auth:identity:" + provider, identity)
                    if provider == "ids":
                        self.store.write("auth:device_enabled", False)
            self.browser.close(provider)
            self._record(provider, "ready", target, checked_at=now())
        return self.get_status(provider)

    def open_device_browser(self):
        with self.locks["ids"]:
            self._baseline_identity("ids")
            self.browser.open("ids", PERSON_CENTER)
        return self.get_status("ids")

    def start_device_setup(self):
        with self.locks["ids"]:
            if self.device.status()["configured"] or self.device.status()["pending"]:
                raise ValueError("已有正式或待确认设备凭据，请检查现有凭据。")
            if self.setup_future is not None and not self.setup_future.done():
                return self.get_status("ids")
            self._baseline_identity("ids")
            self.browser.open("ids", PERSON_CENTER, device_setup=True)
            self.setup_cancelled.clear()
            self.store.write("auth:device_setup", {"status": "waiting", "message": "请在学校窗口完成登录和身份复核，应用会自动完成设备绑定。"})
            self.setup_future = self.setup_executor.submit(self._finish_device_setup)
        return self.get_status("ids")

    def _finish_device_setup(self):
        deadline = time.monotonic() + 600
        try:
            while not self.setup_cancelled.is_set() and time.monotonic() < deadline:
                with self.locks["ids"]:
                    if self.setup_cancelled.is_set():
                        return
                    state = protocols.filtered_state("ids", self.browser.state("ids"))
                    with protocols.http_client(state) as client:
                        try:
                            ready = self.device.ready_to_enroll(client)
                        except VerificationRequired:
                            ready = False
                    if ready and not self.setup_cancelled.is_set():
                        self.bind_device()
                        self.store.write("auth:device_setup", {"status": "ready", "message": "本机免密码登录已连接。"})
                        return
                self.setup_cancelled.wait(2)
            if not self.setup_cancelled.is_set():
                self.store.write("auth:device_setup", {"status": "error", "message": "学校验证等待已超时，请重新连接。"})
        except Exception as error:
            if not self.setup_cancelled.is_set():
                message = str(error) if isinstance(error, (LoginRequired, ValueError)) else "设备连接未完成，请检查学校窗口或待确认凭据后重试。"
                self.store.write("auth:device_setup", {"status": "error", "message": message})

    def _cancel_device_setup(self):
        self.setup_cancelled.set()
        if self.setup_future is not None:
            self.setup_future.result()
        self.store.delete("auth:device_setup")

    def bind_device(self):
        with self.locks["ids"]:
            self._baseline_identity("ids")
            state = protocols.filtered_state("ids", self.browser.state("ids"))
            with protocols.http_client(state) as client:
                subject = self.device.enroll(client)
                self._adopt_identity("ids", subject)
                self.store.write("auth:device_enabled", True)
                self.vault.delete("auth:credentials:ids")
                self.vault.delete("auth:session:ids")
                self._save_session("ids", client, state)
            self.browser.close("ids")
            self._record("ids", "login_required", "elrc", "本机设备已绑定，可检查连接并自动续期。")
        return self.refresh("ids", "elrc")

    def recover_device(self):
        with self.locks["ids"]:
            self.device.recover_pending()
            self.store.write("auth:device_enabled", True)
        return self.login("ids", "elrc")

    def forget_device(self):
        self._cancel_device_setup()
        with self.locks["ids"]:
            self.device.forget()
            self.store.delete("auth:device_enabled")
        return self.get_status("ids")

    @contextmanager
    def _client_lock(self, provider, cancelled):
        lock = self.locks[provider]
        while not lock.acquire(timeout=0.2):
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("来源读取已停止。")
        try:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("来源读取已停止。")
            yield
        finally:
            lock.release()

    @contextmanager
    def authenticated_client(self, provider: str, target: str | None = None, *, cancelled=None):
        target = protocols.checked_target(provider, target)
        with self._client_lock(provider, cancelled):
            state = self.vault.get("auth:session:" + provider)
            with protocols.http_client(state) as client:
                verified_existing = False
                try:
                    if not state:
                        raise LoginRequired("尚未保存登录会话。")
                    subject = protocols.validate(client, provider, target, state)
                    verified_existing = True
                except LoginRequired:
                    saved = self.store.read("auth:state:" + provider, {})
                    if saved.get("blocked"):
                        error_class = VerificationRequired if saved["status"] == "verification_required" else LoginRequired
                        raise error_class(saved.get("message", "自动登录已暂停，请主动连接或完成浏览器验证。")) from None
                    try:
                        subject = self._login(provider, target, client, state)
                    except LoginRequired as error:
                        self._failure(provider, target, error)
                        raise
                self._adopt_identity(provider, subject, migrate=verified_existing)
                self._record(provider, "ready", target, checked_at=now())
                try:
                    yield client
                except LoginRequired as error:
                    self._record(provider, "verification_required" if isinstance(error, VerificationRequired) else "login_required", target, str(error), blocked=isinstance(error, VerificationRequired))
                    raise
                finally:
                    self._save_session(provider, client, state)

    def refresh(self, provider: str, target: str | None = None):
        """Explicit recovery also clears a previous automatic-login pause."""
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            self._record(provider, "login_required", target, blocked=False)
            with self.authenticated_client(provider, target=target):
                pass
        return self.get_status(provider)

    def read_with_recovery(self, provider, operation, *, target=None, cancelled=None):
        """Retry one idempotent reader after a source detects expiry mid-request."""
        for attempt in range(2):
            try:
                with self.authenticated_client(provider, target=target, cancelled=cancelled) as client:
                    return operation(client)
            except VerificationRequired:
                raise
            except LoginRequired:
                if attempt or self.store.read("auth:state:" + provider, {}).get("blocked"):
                    raise
                self.login(provider, target)

    def session_parameters(self, provider: str):
        protocols.checked_target(provider)
        if provider != "coremail":
            return {}
        state = self.vault.get("auth:session:" + provider)
        if not state.get("sid"):
            raise VerificationRequired("请先完成学校邮箱浏览器验证。")
        return {"sid": state["sid"]}

    def forget(self, provider: str):
        protocols.checked_target(provider)
        if provider == "ids":
            self._cancel_device_setup()
        with self.locks[provider]:
            self.browser.close(provider)
            self.vault.delete("auth:credentials:" + provider)
            self.vault.delete("auth:session:" + provider)
            self.vault.delete("auth:identity:" + provider)
            if provider == "ids":
                self.device.forget()
                self.store.delete("auth:device_enabled")
            self.store.delete("auth:state:" + provider)
            self.store.write("auth:revision:" + provider, secrets.token_hex(12))
        return self.get_status(provider)

    def clear_all(self):
        for provider in protocols.PROVIDERS:
            self.forget(provider)

    def close(self):
        self.setup_cancelled.set()
        self.setup_executor.shutdown(wait=True, cancel_futures=True)
        self.browser.close_all()
