import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import protocols
from .browser import VerificationBrowser
from .protocols import LoginRequired, VerificationRequired


def now():
    return datetime.now(timezone.utc).isoformat()


class AuthService:
    def __init__(self, vault, store):
        self.vault = vault
        self.store = store
        self.browser = VerificationBrowser()
        self.locks = {provider: threading.RLock() for provider in protocols.PROVIDERS}

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
            "status": saved.get("status", "login_required" if credentials or session else "not_connected"),
        }
        for key in ("message", "checked_at", "target"):
            if key in saved:
                result[key] = saved[key]
        if provider == "ids":
            result["targets"] = list(protocols.SERVICES)
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

    def save_credentials(self, provider: str, username: str, password: str):
        protocols.checked_target(provider)
        username = username.strip()
        if not username:
            raise ValueError("请填写账号。")
        with self.locks[provider]:
            self.browser.close(provider)
            self.vault.save("auth:credentials:" + provider, {"username": username, "password": password})
            self.vault.delete("auth:session:" + provider)
            self._record(provider, "login_required", message="账号已保存，请连接或完成浏览器验证。")
        return self.get_status(provider)

    def _login(self, provider, target, client, state):
        if provider == "coremail":
            raise VerificationRequired("学校邮箱需要在验证窗口登录并导入会话。")
        credentials = self.vault.get("auth:credentials:" + provider)
        if not credentials.get("password"):
            raise LoginRequired("请先保存账号密码，或打开验证窗口完成登录。")
        protocols.login(client, provider, credentials["username"], credentials["password"], target)
        protocols.validate(client, provider, target, state)

    def login(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            state = self.vault.get("auth:session:" + provider)
            with protocols.http_client(state) as client:
                try:
                    self._login(provider, target, client, state)
                except LoginRequired as error:
                    self._failure(provider, target, error)
                    raise
                self._save_session(provider, client, state)
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
            state = protocols.filtered_state(provider, self.browser.state(provider))
            with protocols.http_client(state) as client:
                try:
                    protocols.validate(client, provider, target, state)
                except LoginRequired as error:
                    self._failure(provider, target, error)
                    raise
                self._save_session(provider, client, state)
            self.browser.close(provider)
            self._record(provider, "ready", target, checked_at=now())
        return self.get_status(provider)

    @contextmanager
    def authenticated_client(self, provider: str, target: str | None = None):
        target = protocols.checked_target(provider, target)
        with self.locks[provider]:
            state = self.vault.get("auth:session:" + provider)
            with protocols.http_client(state) as client:
                try:
                    if not state:
                        raise LoginRequired("尚未保存登录会话。")
                    protocols.validate(client, provider, target, state)
                except LoginRequired:
                    saved = self.store.read("auth:state:" + provider, {})
                    if saved.get("blocked"):
                        error_class = VerificationRequired if saved["status"] == "verification_required" else LoginRequired
                        raise error_class(saved.get("message", "自动登录已暂停，请主动连接或完成浏览器验证。")) from None
                    try:
                        self._login(provider, target, client, state)
                    except LoginRequired as error:
                        self._failure(provider, target, error)
                        raise
                self._record(provider, "ready", target, checked_at=now())
                try:
                    yield client
                except LoginRequired as error:
                    self._failure(provider, target, error)
                    raise
                finally:
                    self._save_session(provider, client, state)

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
        with self.locks[provider]:
            self.browser.close(provider)
            self.vault.delete("auth:credentials:" + provider)
            self.vault.delete("auth:session:" + provider)
            self.store.delete("auth:state:" + provider)
        return self.get_status(provider)

    def clear_all(self):
        for provider in protocols.PROVIDERS:
            self.forget(provider)

    def close(self):
        self.browser.close_all()
