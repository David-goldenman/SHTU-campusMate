"""Offline integration check; fixtures exist only inside .codex/tmp."""
import asyncio
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx

from backend.core.store import Store
from backend.main import create_app


class MemoryVault:
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


def fixture(root, module_id, value):
    directory = root / module_id
    (directory / "server").mkdir(parents=True)
    (directory / "web").mkdir()
    (directory / "module.json").write_text(json.dumps({"id": module_id, "name": module_id, "version": "0.1.0", "category": "courses", "api_version": 1}))
    (directory / "web" / "index.js").write_text("export function mount(container) { container.textContent = 'fixture'; }\n")
    (directory / "server" / "helpers.py").write_text(f"VALUE = '{value}'\n")
    (directory / "server" / "__init__.py").write_text('''from fastapi import APIRouter
from .helpers import VALUE

def create_router(context):
    router = APIRouter()

    @router.get('/state')
    def state():
        return {'version': VALUE, 'value': context.store.read('value'), 'has_secret': bool(context.secrets.get('test'))}

    @router.put('/state')
    def save():
        context.store.write('value', context.id)
        context.secrets.save('test', {'value': 'synthetic-private-value'})
        return {'saved': True}

    return router

def stop(context):
    context.store.write('stopped', True)

def authorize_write(context, request):
    return request.url.path == '/api/v1/modules/' + context.id + '/state' and request.headers.get('authorization') == 'Bearer synthetic-' + context.id
''')
    return directory


async def check(root):
    modules, data = root / "modules", root / "private"
    modules.mkdir()
    data.mkdir()
    store, vault = Store(data / "settings.sqlite3"), MemoryVault()
    app = create_app(active_port=17666, store=store, vault=vault, modules_root=modules, data_dir=data)
    app.state.auth.browser = SimpleNamespace(close=lambda provider: None, close_all=lambda: None)
    messages = []

    async def send(message):
        messages.append(message)

    await app.state.modules({"type": "websocket"}, None, send)
    assert messages == [{"type": "websocket.close", "code": 1008}]
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:17666") as client:
            initial = (await client.get("/api/v1/bootstrap")).json()
            assert [item["id"] for item in initial["categories"]] == ["dashboard", "mail", "timetable", "courses", "assignments", "notifications", "assistant", "settings"]
            assert initial["modules"] == []
            assert all(not item["has_password"] and not item["has_session"] for item in (await client.get("/api/v1/auth/providers")).json()["providers"])
            assert (await client.get("/api/v1/ai/settings")).json() == {"enabled": False, "model": "deepseek-flash", "key_saved": False}
            assert (await client.put("/api/v1/settings", json={"port": 17667})).status_code == 403
            assert (await client.get("/api/v1/bootstrap", headers={"Host": "untrusted.example"})).status_code == 403
            assert (await client.get("/api/v1/bootstrap", headers={"Origin": "https://untrusted.example"})).status_code == 403
            client.headers["X-Framework-Token"] = initial["csrf_token"]
            assert (await client.put("/api/v1/settings", json={"port": 6666})).status_code == 422
            assert (await client.put("/api/v1/settings", json={"port": 17667})).json()["restart_required"] is True
            private_marker = "synthetic-secret-marker-" * 200
            invalid = await client.put("/api/v1/auth/gradescope/credentials", json={"username": "fixture", "password": private_marker})
            assert invalid.status_code == 422 and private_marker not in invalid.text and '"input"' not in invalid.text
            alpha = fixture(modules, "alpha", "one")
            fixture(modules, "beta", "two")
            discovered = (await client.post("/api/v1/modules/reload")).json()["modules"]
            assert len(discovered) == 2 and all(item["status"] == "ready" for item in discovered), discovered
            first = next(item for item in discovered if item["id"] == "alpha")
            assert (await client.get(first["frontend_url"])).status_code == 200
            traversal = first["frontend_url"].split("web/")[0] + "web/%2e%2e/server/__init__.py"
            assert (await client.get(traversal)).status_code == 404
            assert (await client.get("/api/v1/modules/alpha/state")).json()["version"] == "one"
            assert (await app.state.modules.entries["beta"].context.api("alpha", "/state")).json()["version"] == "one"
            try:
                await app.state.modules.read_api("alpha", "/%2e%2e/beta/state")
                raise AssertionError("Module API traversal must be rejected")
            except ValueError:
                pass
            assert (await client.put("/api/v1/modules/alpha/state")).status_code == 200
            assert (await client.get("/api/v1/modules/beta/state")).json()["value"] is None
            assert (await client.get("/api/v1/modules/beta/state")).json()["has_secret"] is False
            csrf_token = client.headers.pop("X-Framework-Token")
            assert (await client.put("/api/v1/modules/alpha/state", headers={"Authorization": "Bearer synthetic-alpha"})).status_code == 200
            assert (await client.put("/api/v1/modules/beta/state", headers={"Authorization": "Bearer synthetic-alpha"})).status_code == 403
            assert (await client.put("/api/v1/settings", json={"port": 17667}, headers={"Authorization": "Bearer synthetic-alpha"})).status_code == 403
            assert (await client.put("/api/v1/modules/alpha/state", headers={"Authorization": "Bearer synthetic-alpha", "Origin": "https://untrusted.example"})).status_code == 403
            client.headers["X-Framework-Token"] = csrf_token
            (alpha / "server" / "helpers.py").write_text("VALUE = 'new'\n")
            updated = (await client.post("/api/v1/modules/reload")).json()["modules"]
            second = next(item for item in updated if item["id"] == "alpha")
            assert first["frontend_url"] != second["frontend_url"]
            assert (await client.get(first["frontend_url"])).status_code == 404
            assert (await client.get("/api/v1/modules/alpha/state")).json() == {"version": "new", "value": "alpha", "has_secret": True}
            disabled = await client.put("/api/v1/modules/alpha", json={"enabled": False})
            assert disabled.status_code == 200
            assert (await client.get("/api/v1/modules/alpha/state")).status_code == 404
            assert (await app.state.modules.read_api("alpha", "/state")).status_code == 404
            assert (await client.get(second["frontend_url"])).status_code == 404
            assert (await client.get("/api/v1/modules/beta/state")).status_code == 200
            await client.put("/api/v1/modules/alpha", json={"enabled": True})
            assert (await client.get("/api/v1/modules/alpha/state")).json()["value"] == "alpha"
            assert (await client.get("/api/v1/modules/alpha/openapi.json")).json()["paths"]["/state"]
            active = app.state.modules.entries["alpha"]
            original_stop = active.package.stop

            def stop_failure(context):
                raise RuntimeError("synthetic cleanup failure")

            active.package.stop = stop_failure
            assert (await client.put("/api/v1/modules/alpha", json={"enabled": False})).status_code == 409
            assert active.context is not None
            active.package.stop = original_stop
            assert (await client.put("/api/v1/modules/alpha", json={"enabled": False})).status_code == 200
            await client.put("/api/v1/modules/alpha", json={"enabled": True})
            fixture(modules, "reload", "reserved")
            broken = modules / "broken"
            broken.mkdir()
            (broken / "module.json").write_text('{"id":"broken"}')
            listed = (await client.post("/api/v1/modules/reload")).json()["modules"]
            assert next(item for item in listed if item["id"] == "broken")["status"] == "error"
            assert next(item for item in listed if item["id"] == "reload")["status"] == "error"
            assert (await client.get("/api/v1/modules/alpha/state")).status_code == 200
            active = app.state.modules.entries["alpha"]
            active.requests = 1
            assert (await client.put("/api/v1/modules/alpha", json={"enabled": False})).status_code == 409
            active.requests = 0
            assert (await client.post("/api/v1/data/clear", json={"scope": "all", "confirmation": "wrong"})).status_code == 422
            await client.put("/api/v1/ai/settings", json={"enabled": True, "api_key": "synthetic-api-key"})
            assert vault.get("ai:deepseek")
            cleared = await client.post("/api/v1/data/clear", json={"scope": "credentials", "confirmation": "CLEAR"})
            assert cleared.status_code == 200 and vault.values == {}
            assert (await client.get("/api/v1/modules/alpha/state")).json()["value"] == "alpha"
            assert (await client.get("/api/v1/ai/settings")).json()["enabled"] is False
            await client.post("/api/v1/data/clear", json={"scope": "all", "confirmation": "CLEAR"})
            assert (await client.get("/api/v1/settings")).json()["port"] == 16666
            assert (await client.get("/api/v1/modules/alpha/state")).json()["value"] is None
            (alpha / "module.json").unlink()
            await client.post("/api/v1/modules/reload")
            assert (await client.get("/api/v1/modules/alpha/state")).status_code == 404
            assert (await client.get("/api/openapi.json")).status_code == 200
    print("framework: blank shell, scoped storage, security, hot reload, disable/remove and reset passed")


if __name__ == "__main__":
    temporary = PROJECT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="framework-check-", dir=temporary) as directory:
        asyncio.run(check(Path(directory)))
