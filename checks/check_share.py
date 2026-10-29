"""Phone access stays opt-in and requires the pairing code."""
import asyncio
import sys
import tempfile
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx

from backend.core import share
from backend.core.store import Store
from backend.main import create_app


class MemoryVault:
    transaction = staticmethod(nullcontext)
    def __init__(self):
        self.values = {}

    def get(self, key):
        return deepcopy(self.values.get(key, {}))

    def save(self, key, value):
        self.values[key] = deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)

    def delete_prefix(self, prefix):
        self.values = {key: value for key, value in self.values.items() if not key.startswith(prefix)}

    def clear(self):
        self.values.clear()


def ignores_browser(app):
    app.state.auth.browser = SimpleNamespace(close=lambda provider: None, forget=lambda provider: None, close_all=lambda: None)
    return app


async def check(root):
    modules, data = root / "modules", root / "private"
    modules.mkdir()
    data.mkdir()
    store, vault = Store(data / "settings.sqlite3"), MemoryVault()
    host, port = "192.168.1.23:17666", 17666

    assert share.address(host, port)
    assert share.address("10.0.0.5:17666", port)
    assert share.address("campusmate.local:17666", port)
    assert share.address(f"[fd00::12]:{port}", port)
    for rejected in ("192.168.1.23:17667", "192.168.1.23", "8.8.8.8:17666", "example.com:17666", "", "192.168.1.23:"):
        assert not share.address(rejected, port), rejected
    assert all("127.0.0.1" not in url for url in share.urls(port))

    closed = ignores_browser(create_app(active_port=port, store=store, vault=vault, modules_root=modules, data_dir=data))
    async with closed.router.lifespan_context(closed):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(closed), base_url=f"http://127.0.0.1:{port}") as client:
            assert (await client.get("/api/v1/bootstrap", headers={"Host": host})).status_code == 403
            assert (await client.get("/api/v1/bootstrap", headers={"Host": f"127.0.0.1:{port}"})).status_code == 200

    shared = ignores_browser(create_app(active_port=port, store=Store(data / "settings.sqlite3"), vault=vault, modules_root=modules, data_dir=data, share=True))
    pin = share.code(Store(data / "settings.sqlite3"))
    assert len(pin) == 8 and pin == share.code(Store(data / "settings.sqlite3")), "The pairing code must persist."
    async with shared.router.lifespan_context(shared):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(shared), base_url=f"http://127.0.0.1:{port}") as client:
            unpaired = await client.get("/api/v1/bootstrap", headers={"Host": host})
            assert unpaired.status_code == 403 and "配对码" in unpaired.text
            assert (await client.get("/api/v1/bootstrap", headers={"Host": host}, cookies={share.COOKIE: "00000000"})).status_code == 403
            assert (await client.get(f"/api/v1/bootstrap?pair={pin}", headers={"Host": "8.8.8.8:17666"})).status_code == 403
            assert (await client.get("/api/v1/bootstrap", headers={"Host": host, "Sec-Fetch-Site": "cross-site"}, cookies={share.COOKIE: pin})).status_code == 403
            redirect = await client.get(f"/api/v1/bootstrap?pair={pin}", headers={"Host": host})
            cookie = redirect.headers["set-cookie"]
            assert redirect.status_code == 303 and redirect.headers["location"] == "/"
            assert f"{share.COOKIE}={pin}" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
            bootstrap = await client.get("/api/v1/bootstrap", headers={"Host": host}, cookies={share.COOKIE: pin})
            assert bootstrap.status_code == 200 and bootstrap.json()["csrf_token"]
            token = bootstrap.json()["csrf_token"]
            assert (await client.put("/api/v1/settings", json={"port": 17667}, headers={"Host": host}, cookies={share.COOKIE: pin})).status_code == 403
            saved = await client.put("/api/v1/settings", json={"port": 17667}, headers={"Host": host, "X-Framework-Token": token}, cookies={share.COOKIE: pin})
            assert saved.status_code == 200 and saved.json()["restart_required"] is True
            assert (await client.get("/api/v1/bootstrap", cookies={share.COOKIE: pin})).status_code == 200
    print("share: loopback default, pairing code, cookie handoff and token rules passed")


if __name__ == "__main__":
    temporary = PROJECT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="share-check-", dir=temporary) as directory:
        asyncio.run(check(Path(directory)))
