import threading
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import httpx

from ...core.paths import RUNTIME
from . import imap as imap_access
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
        # Keep the IMAP-over-web priority true for installations upgraded from an
        # earlier version where both credential sets may already be present.
        imap = self.vault.get("auth:imap:coremail")
        if imap.get("username") and imap.get("password") and (self.vault.get("auth:session:coremail") or self.vault.get("auth:credentials:coremail")):
            self._drop_official_mail()

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

    def get_account_revision(self, provider: str):
        """Read the current ownership epoch without opening credentials or sessions."""
        protocols.checked_target(provider)
        return self.store.read("auth:revision:" + provider, "initial")

    def get_status(self, provider: str | None = None):
        if provider is None:
            return {"providers": self.providers()}
        protocols.checked_target(provider)
        credentials = self.vault.get("auth:credentials:" + provider)
        session = self.vault.get("auth:session:" + provider)
        saved = self.store.read("auth:state:" + provider, {})
        imap = self.vault.get("auth:imap:" + provider) if provider == "coremail" else {}
        result = {
            "id": provider, "name": protocols.PROVIDERS[provider]["name"], "username": credentials.get("username", ""),
            "has_password": bool(credentials.get("password")), "has_session": bool(session),
            "account_revision": self.get_account_revision(provider),
            "identity_verified": bool(self.vault.get("auth:identity:" + provider).get("subject")),
            "session_revision": self.store.read("auth:session_revision:" + provider, "initial"),
            "status": saved.get("status", "ready" if imap.get("username") and imap.get("password") else "login_required" if credentials or session else "not_connected"),
        }
        for key in ("message", "checked_at", "target"):
            if key in saved:
                result[key] = saved[key]
        if provider == "ids":
            result["targets"] = list(protocols.SERVICES)
            result["device"] = {**self.device.status(), "enabled": self.store.read("auth:device_enabled", True)}
            result["device"]["setup"] = self.store.read("auth:device_setup", {"status": "idle"})
        if provider == "coremail":
            result["imap"] = {
                "configured": bool(imap.get("username") and imap.get("password")),
                "host": imap.get("host", imap_access.IMAP_HOST), "port": imap.get("port", imap_access.DEFAULT_PORT),
                "ssl": imap.get("ssl", True), "username": imap.get("username", ""),
                "password_saved": bool(imap.get("password")), "verified_at": imap.get("verified_at"),
            }
        result["automatic_recovery"] = bool(provider != "coremail" and credentials.get("password")) or bool(provider == "coremail" and imap.get("password")) or bool(provider == "ids" and result["device"]["configured"] and result["device"]["enabled"])
        return result

    def providers(self):
        return [self.get_status(provider) for provider in protocols.PROVIDERS]

    def imap_enabled(self, provider: str = "coremail") -> bool:
        protocols.checked_target(provider)
        if provider != "coremail":
            return False
        saved = self.vault.get("auth:imap:" + provider)
        return bool(saved.get("username") and saved.get("password"))

    def _drop_official_mail(self):
        """IMAP is the preferred mailbox transport; never retain its web session."""
        self.browser.forget("coremail")
        self.vault.delete("auth:credentials:coremail")
        self.vault.delete("auth:session:coremail")

    def save_imap(self, username: str, password: str, port=None, secure=True):
        provider = "coremail"
        username = (username or "").strip()
        if not username:
            raise ValueError("请填写学校邮箱账号。")
        settings = imap_access.checked_settings(port, secure)
        with self.locks[provider]:
            previous = self.vault.get("auth:imap:" + provider)
            password = password or previous.get("password", "")
            if not password:
                raise ValueError("请填写学校邮箱的客户端专用密码。")
            imap_access.verify(username, password, settings["port"], settings["ssl"])
            self._drop_official_mail()
            self.vault.delete("auth:identity:" + provider)
            self.store.write("auth:revision:" + provider, secrets.token_hex(12))
            self.vault.save("auth:imap:" + provider, {
                "host": settings["host"], "port": settings["port"], "ssl": settings["ssl"],
                "username": username, "password": password, "verified_at": now(),
            })
            self._adopt_identity(provider, username.casefold())
            self.store.write("auth:session_revision:" + provider, secrets.token_hex(12))
            self._record(provider, "ready", message="已使用 IMAP 登录学校邮箱。", checked_at=now())
        return self.get_status(provider)

    def check_imap(self):
        provider = "coremail"
        with self.locks[provider]:
            saved = self.vault.get("auth:imap:" + provider)
            if not saved.get("username") or not saved.get("password"):
                raise VerificationRequired("请先填写邮箱账号和客户端专用密码，使用 IMAP 登录。")
            try:
                imap_access.verify(saved["username"], saved["password"], saved.get("port"), saved.get("ssl", True))
            except LoginRequired as error:
                self._record(provider, "login_required", message=str(error), blocked=True)
                raise
            if not self.vault.get("auth:identity:" + provider).get("subject"):
                self._adopt_identity(provider, saved["username"].casefold())
            self._record(provider, "ready", message="IMAP 连接正常。", checked_at=now())
        return self.get_status(provider)

    @contextmanager
    def imap_connection(self, provider: str = "coremail"):
        """Yield a logged-in, read-only IMAP mailbox; credentials stay in Vault."""
        protocols.checked_target(provider)
        if provider != "coremail":
            raise ValueError("只有学校邮箱支持 IMAP。")
        saved = self.vault.get("auth:imap:" + provider)
        if not saved.get("username") or not saved.get("password"):
            raise VerificationRequired("请先使用 IMAP 登录学校邮箱。")
        try:
            mailbox = imap_access.connect(saved["username"], saved["password"], saved.get("port"), saved.get("ssl", True))
        except LoginRequired as error:
            self._record(provider, "login_required", message=str(error), blocked=True)
            raise
        try:
            yield mailbox
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass

    def forget_imap(self):
        provider = "coremail"
        with self.locks[provider]:
            self._drop_official_mail()
            self.vault.delete("auth:imap:" + provider)
            self.vault.delete("auth:identity:" + provider)
            self.store.delete("auth:state:" + provider)
            self.store.write("auth:revision:" + provider, secrets.token_hex(12))
        return self.get_status(provider)

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
        if provider == "coremail" and self.imap_enabled(provider):
            raise VerificationRequired("学校邮箱已使用 IMAP 登录。如需改用官方网页，请先删除 IMAP 登录。")
        username = username.strip()
        if not username:
            raise ValueError("请填写账号。")
        with self.locks[provider]:
            self._baseline_identity(provider)
            previous = self.vault.get('auth:credentials:' + provider)
            changed = previous.get('username', '').casefold() != username.casefold()
            if changed:
                self.store.write("auth:revision:" + provider, secrets.token_hex(12))
                identity = self.vault.get("auth:identity:" + provider)
                identity.pop("subject", None)
                self.vault.save("auth:identity:" + provider, identity)
                self.browser.forget(provider)
                self.vault.delete("auth:session:" + provider)
                if provider == "ids":
                    self.store.write("auth:device_enabled", False)
                self._record(provider, "login_required", message="账号已保存，请连接或完成浏览器验证。")
            else:
                self.browser.close(provider)
            self.vault.save("auth:credentials:" + provider, {"username": username, "password": password})
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

    def login(self, provider: str, target: str | None = None, *, force=False):
        target = protocols.checked_target(provider, target)
        if provider == "coremail" and self.imap_enabled(provider):
            return self.check_imap()
        with self.locks[provider]:
            self._baseline_identity(provider)
            state = self.vault.get("auth:session:" + provider)
            with protocols.http_client(state) as client:
                try:
                    try:
                        if not state or force:
                            raise LoginRequired("尚未保存会话。")
                        subject = protocols.validate(client, provider, target, state)
                    except LoginRequired:
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
        if provider == "coremail" and self.imap_enabled(provider):
            raise VerificationRequired("学校邮箱已使用 IMAP 登录。如需改用官方网页，请先删除 IMAP 登录。")
        with self.locks[provider]:
            self.browser.open(provider, protocols.browser_url(provider, target))
            self._record(provider, "verification_required", target, "请在验证窗口登录，完成后导入会话。", blocked=True)
        return self.get_status(provider)

    def import_session(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        if provider == "coremail" and self.imap_enabled(provider):
            self.browser.close(provider)
            return self.get_status(provider)
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
        if provider == "coremail" and self.imap_enabled(provider):
            raise VerificationRequired("学校邮箱已使用 IMAP 登录，网页邮箱会话不再使用。")
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
        if provider == "coremail" and self.imap_enabled(provider):
            return self.check_imap()
        with self.locks[provider]:
            saved = self.store.read('auth:state:' + provider, {})
            self.store.write('auth:state:' + provider, {**saved, 'blocked': False})
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
                self.login(provider, target, force=True)

    def session_parameters(self, provider: str):
        protocols.checked_target(provider)
        if provider != "coremail":
            return {}
        if self.imap_enabled(provider):
            raise VerificationRequired("学校邮箱已使用 IMAP 登录，网页邮箱参数不再使用。")
        state = self.vault.get("auth:session:" + provider)
        if not state.get("sid"):
            raise VerificationRequired("请先完成学校邮箱浏览器验证。")
        return {"sid": state["sid"]}

    def forget(self, provider: str):
        protocols.checked_target(provider)
        if provider == "ids":
            self._cancel_device_setup()
        with self.locks[provider]:
            self.browser.forget(provider)
            self.vault.delete("auth:credentials:" + provider)
            self.vault.delete("auth:session:" + provider)
            self.vault.delete("auth:imap:" + provider)
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
