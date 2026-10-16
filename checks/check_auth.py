import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.paths import PROJECT
from backend.core.store import Store
from backend.core.vault import Vault
from backend.services.auth import AuthService, LoginRequired, VerificationRequired, create_router
from backend.services.auth import protocols


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return deepcopy(self.values.get(key, {}))

    def save(self, key, value):
        self.values[key] = deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)


def cookie(name="session", value="synthetic-cookie", domain="www.gradescope.com", **options):
    return {"name": name, "value": value, "domain": domain, "path": "/", "secure": True, "httpOnly": True,
            "sameSite": "Lax", "expires": 4102444800, "domain_specified": False, **options}


def check_cookies():
    state = {"cookies": [cookie(path="/private"), cookie(name="expired", expires=1)]}
    with protocols.http_client(state) as client:
        assert client.build_request("GET", "http://www.gradescope.com/private").headers.get("cookie") is None
        assert client.build_request("GET", "https://www.gradescope.com/public").headers.get("cookie") is None
        assert client.build_request("GET", "https://other.example/private").headers.get("cookie") is None
        assert client.build_request("GET", "https://www.gradescope.com/private").headers["cookie"] == "session=synthetic-cookie"
        exported = protocols.session_state(client)["cookies"][0]
        assert all(exported[key] == state["cookies"][0][key] for key in ("secure", "httpOnly", "sameSite", "expires", "domain_specified", "path"))
    filtered = protocols.filtered_state("gradescope", {"cookies": [cookie(), cookie(domain="gradescope.com.attacker.example")], "sid": "synthetic-sid", "pages": []})
    assert len(filtered["cookies"]) == 1 and "sid" not in filtered and "pages" not in filtered
    original_client = httpx.Client
    sent = []
    transport = httpx.MockTransport(lambda request: (sent.append(request.headers.get("cookie")), httpx.Response(200))[1])
    with patch.object(protocols.httpx, "Client", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs)):
        with protocols.http_client({"cookies": [cookie()]}) as client:
            client.get("https://child.www.gradescope.com/")
            client.get("https://www.gradescope.com/")
            client.get("http://www.gradescope.com/")
    assert sent == [None, "session=synthetic-cookie", None]
    try:
        protocols.checked_target("ids", "https://attacker.example")
        raise AssertionError("Arbitrary login destinations must be rejected")
    except ValueError:
        pass


def check_vault(directory):
    path = directory / "synthetic.dpapi"
    vault = Vault(path)
    value = {"password": "synthetic-password-中文", "cookies": [cookie()]}
    vault.save("auth:synthetic", value)
    assert "synthetic-password" not in path.read_text(encoding="ascii")
    assert Vault(path).get("auth:synthetic") == value
    encrypted = path.read_bytes()
    with patch("backend.core.vault.protect", side_effect=RuntimeError("synthetic encryption failure")):
        try:
            vault.save("auth:synthetic", {"password": "synthetic-replacement"})
            raise AssertionError("A failed encryption must not replace the saved value")
        except RuntimeError:
            pass
    assert vault.get("auth:synthetic") == value and path.read_bytes() == encrypted
    with patch("backend.core.vault.protect", side_effect=AssertionError("Unchanged values must not be encrypted again")):
        vault.delete("missing")
        vault.delete_prefix("missing:")
    copy = vault.get("auth:synthetic")
    copy["cookies"][0]["value"] = "changed"
    assert vault.get("auth:synthetic") == value
    vault.save("module:synthetic:key", {"key": "synthetic-key"})
    vault.delete_prefix("auth:")
    assert not vault.get("auth:synthetic") and vault.get("module:synthetic:key")
    vault.clear()
    assert not Vault(path).get("module:synthetic:key")
    with patch("backend.core.vault.protect", side_effect=AssertionError("An empty Vault must not be encrypted again")):
        vault.clear()
    assert not path.with_suffix(".next").exists()


def check_service(directory):
    vault = MemoryVault()
    store = Store(directory / "state.sqlite3")
    service = AuthService(vault, store)
    server = {"posts": 0, "expired": False, "reject": False}

    def respond(request):
        if request.url.path == "/login" and request.method == "POST":
            server["posts"] += 1
            if server["reject"]:
                return httpx.Response(401, text='<form action="/login"></form>')
            server["expired"] = False
            return httpx.Response(200, text="signed in", headers={"set-cookie": "session=synthetic-cookie; Secure; HttpOnly; SameSite=Lax; Path=/"})
        if request.url.path == "/login":
            return httpx.Response(200, text='<form action="/login"><input type="hidden" name="authenticity_token" value="synthetic"></form>')
        if request.url.path == "/account":
            logged_in = "session=synthetic-cookie" in request.headers.get("cookie", "") and not server["expired"]
            return httpx.Response(200, text='<div id="account-show"></div>' if logged_in else '<form action="/login"></form>')
        return httpx.Response(200, json={"synthetic": True}, headers={"set-cookie": "rotated=synthetic-rotated; Secure; HttpOnly; Path=/"})

    original_client = httpx.Client
    original_factory = protocols.http_client
    transport = httpx.MockTransport(respond)

    def factory(state=None):
        with patch.object(protocols.httpx, "Client", side_effect=lambda **kwargs: original_client(transport=transport, **kwargs)):
            return original_factory(state)

    class Browser:
        def __init__(self):
            self.closed = 0

        def close(self, provider):
            self.closed += 1

        def close_all(self):
            self.closed += 1

        def open(self, provider, url):
            assert url == "https://www.gradescope.com/login"

        def state(self, provider):
            return {"cookies": [cookie(), cookie(domain="attacker.example")], "sid": "synthetic-private-sid", "pages": ["synthetic-private-url"]}

    service.browser = Browser()
    assert all(row["status"] == "not_connected" for row in service.providers())
    service.save_credentials("gradescope", "synthetic@example.edu", "synthetic-password")
    with patch.object(protocols, "http_client", side_effect=factory):
        with service.authenticated_client("gradescope") as client:
            assert client.get("https://www.gradescope.com/synthetic").json()["synthetic"]
        assert server["posts"] == 1
        assert any(c["name"] == "rotated" for c in vault.get("auth:session:gradescope")["cookies"])
        status = service.get_status("gradescope")
        assert status["status"] == "ready" and status["checked_at"] and status["has_session"]
        server["expired"] = True
        with service.authenticated_client("gradescope"):
            pass
        assert server["posts"] == 2
        server.update(expired=True, reject=True)
        for _ in range(2):
            try:
                with service.authenticated_client("gradescope"):
                    raise AssertionError("Rejected logins must not yield a client")
            except LoginRequired:
                pass
        assert server["posts"] == 3 and service.get_status("gradescope")["status"] == "login_required"
        server.update(expired=False, reject=False)
        service.login("gradescope")
        assert server["posts"] == 4
        service.open_browser("gradescope")
        service.import_session("gradescope")
        saved = vault.get("auth:session:gradescope")
        assert len(saved["cookies"]) == 1 and "sid" not in saved and "pages" not in saved
        assert service.browser.closed >= 2 and service.get_status("gradescope")["status"] == "ready"
        service.save_credentials("piazza", "synthetic@example.edu", "synthetic-password")
        with patch.object(protocols, "login", side_effect=VerificationRequired("需要验证")) as attempt:
            for _ in range(2):
                try:
                    with service.authenticated_client("piazza"):
                        raise AssertionError("Verification must finish before acquiring a client")
                except VerificationRequired:
                    pass
            assert attempt.call_count == 1
        app = FastAPI()
        app.include_router(create_router(service), prefix="/api/v1")
        with TestClient(app) as web:
            response = web.get("/api/v1/auth/providers")
            assert response.status_code == 200 and len(response.json()["providers"]) == 4
            assert web.get("/api/v1/auth/gradescope/status").json()["id"] == "gradescope"
            assert web.get("/api/v1/auth/missing/status").status_code == 404
            assert not any(value in response.text for value in ("synthetic-password", "synthetic-cookie", "synthetic-private-sid"))
        vault.save("ai:settings", {"key": "synthetic-ai-key"})
        service.clear_all()
        assert all(not row["has_session"] and not row["has_password"] for row in service.providers())
        assert vault.get("ai:settings")["key"] == "synthetic-ai-key"
        service.close()
    store.close()


def main():
    (PROJECT / ".codex").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="auth-check-", dir=PROJECT / ".codex") as temporary:
        directory = Path(temporary)
        check_cookies()
        check_vault(directory)
        check_service(directory)
    print(json.dumps({"auth": "passed", "credentials": "synthetic", "network": "mocked", "encryption": "Windows DPAPI"}))


if __name__ == "__main__":
    main()
