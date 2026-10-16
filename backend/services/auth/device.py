"""Dedicated IDS software device credentials, protected by the shared Vault."""
import json
from urllib.parse import urlsplit

import requests
from shanghaitech_ids_passkey import IDSClient, IDSConfig, PasskeyKeystore
from shanghaitech_ids_passkey._ids_api import build_anon_biometrics_id, build_nonce
from shanghaitech_ids_passkey._webauthn import create_registration_response

from .protocols import LoginRequired, VerificationRequired

BASE = "https://ids.shanghaitech.edu.cn"
PERSON_CENTER = BASE + "/personalInfo/personCenter/index.html#/accountsecurity"
DEVICE_NAME = "Campus 工作台 · 本机"


class IDSSession(requests.Session):
    def send(self, request, **kwargs):
        target = urlsplit(request.url)
        if target.scheme != "https" or target.hostname != "ids.shanghaitech.edu.cn" or target.port not in {None, 443} or target.username or target.password:
            raise LoginRequired("设备认证跳转超出学校 IDS 范围。")
        kwargs["verify"] = True
        kwargs.setdefault("timeout", 20)
        return super().send(request, **kwargs)


def checked_key(value):
    if value.get("base_url") != BASE or value.get("rp_id") != "ids.shanghaitech.edu.cn":
        raise LoginRequired("设备凭据的学校来源不匹配。")
    try:
        return PasskeyKeystore.from_dict(value)
    except Exception:
        raise LoginRequired("本机设备凭据无法读取，请重新连接。") from None


class DeviceCredential:
    def __init__(self, vault):
        self.vault = vault

    def status(self):
        value = self.vault.get("auth:device:ids")
        return {"configured": bool(value), "pending": bool(self.vault.get("auth:device-pending:ids")), "name": value.get("device_name", DEVICE_NAME)}

    def renew(self, client):
        # Keep the counter transaction open through assertion generation and
        # persist it even when a later HTTP step fails.
        with self.vault.transaction():
            value = self.vault.get("auth:device:ids")
            if not value:
                raise LoginRequired("请连接学校设备凭据，或在验证窗口重新登录。")
            key = checked_key(value)
            with IDSSession() as session:
                session.trust_env = False
                try:
                    IDSClient(key, config=IDSConfig(base_url=BASE, verify_tls=True, timeout=20), session=session).login()
                    for cookie in session.cookies:
                        client.cookies.jar.set_cookie(cookie)
                except Exception:
                    raise VerificationRequired("学校设备凭据未能续期，请在学校页面完成验证；本机凭据已保留。") from None
                finally:
                    self.vault.save("auth:device:ids", key.to_dict())
            return key.username

    @staticmethod
    def _json(client, method, path, **kwargs):
        response = client.request(method, BASE + path, follow_redirects=False, timeout=20, **kwargs)
        if response.status_code != 200:
            raise VerificationRequired("请先在学校账号安全页面完成身份验证。")
        try:
            value = response.json()
        except ValueError:
            raise VerificationRequired("学校返回了登录页面，请完成验证后重试。") from None
        if not isinstance(value, dict):
            raise VerificationRequired("学校没有返回设备验证结果。")
        return value

    def enroll(self, client):
        """Only called after the user explicitly confirms a new device binding."""
        with self.vault.transaction():
            if self.status()["configured"]:
                raise ValueError("已绑定本机设备，无需重复注册。")
            if self.status()["pending"]:
                raise VerificationRequired("上次绑定结果尚未确认，请先检查已有设备凭据。")
            recheck = self._json(client, "GET", "/personalInfo/common/isUserRecheckNecessary")
            if str(recheck.get("code")) != "0":
                raise VerificationRequired("请在学校账号安全页面点击绑定当前设备，并完成学校要求的验证，再返回本应用。")
            start = self._json(client, "POST", "/personalInfo/accountSecurity/startRegister", json={"n": build_nonce()})
            request = (start.get("datas") or {}).get("request") or {}
            options = request.get("publicKeyCredentialCreationOptions") or {}
            if (options.get("rp") or {}).get("id") != "ids.shanghaitech.edu.cn":
                raise VerificationRequired("学校设备绑定尚未准备好，请确认已开启学校的生物验证选项。")
            try:
                credential, metadata = create_registration_response(options, origin=BASE)
                username = request.get("username") or options["user"].get("name")
                key = PasskeyKeystore(username=username, anon_biometrics_id=build_anon_biometrics_id(),
                    device_name=DEVICE_NAME, base_url=BASE, **metadata)
            except Exception:
                raise VerificationRequired("学校设备挑战格式无法识别，本次未注册设备。") from None
            # A successful school registration must never leave its only private
            # key in memory; an uncertain response remains recoverable.
            self.vault.save("auth:device-pending:ids", key.to_dict())
            result = self._json(client, "POST", "/personalInfo/accountSecurity/finishRegister", json={
                "deviceName": DEVICE_NAME, "anonbiometricsd": key.anon_biometrics_id,
                "response": json.dumps({"requestId": request.get("requestId"), "credential": credential, "sessionToken": None}),
                "n": build_nonce(),
            })
            if str(result.get("code")) != "0":
                raise VerificationRequired("学校未确认设备绑定，待确认凭据已加密保留。")
            self.vault.save("auth:device:ids", key.to_dict())
            self.vault.delete("auth:device-pending:ids")
            return key.username

    def ready_to_enroll(self, client):
        result = self._json(client, "GET", "/personalInfo/common/isUserRecheckNecessary")
        return str(result.get("code")) == "0"

    def recover_pending(self):
        with self.vault.transaction():
            pending = self.vault.get("auth:device-pending:ids")
            key = checked_key(pending)
            with IDSSession() as session:
                session.trust_env = False
                try:
                    IDSClient(key, config=IDSConfig(base_url=BASE, verify_tls=True, timeout=20), session=session).login()
                except Exception:
                    raise VerificationRequired("学校仍未确认上次设备绑定，请在学校安全页面核对后再操作。") from None
                finally:
                    self.vault.save("auth:device-pending:ids", key.to_dict())
            self.vault.save("auth:device:ids", key.to_dict())
            self.vault.delete("auth:device-pending:ids")

    def forget(self):
        with self.vault.transaction():
            self.vault.delete("auth:device:ids")
            self.vault.delete("auth:device-pending:ids")
