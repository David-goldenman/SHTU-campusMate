"""Exercise installed modules through real lifecycle and public APIs, with no accounts."""
import asyncio
import ast
import shutil
import sys
import tempfile
import threading
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx
from backend.core.store import Store
from backend.main import create_app
from checks.check_framework import MemoryVault


def boundaries():
    # Dependency direction is an architectural constraint, checked independently of behavior.
    for path in (PROJECT / "backend").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(name == "modules" or name.startswith("modules.") for name in imports), path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "api" and node.args and isinstance(node.args[0], ast.Constant):
                raise AssertionError(f"Business module API selection belongs to modules: {path}")


async def check(root):
    module_root = root / "modules"
    shutil.copytree(PROJECT / "modules", module_root)
    data = root / "private"
    data.mkdir()
    app = create_app(active_port=17668, store=Store(data / "state.sqlite3"), vault=MemoryVault(), modules_root=module_root, data_dir=data)
    manager = app.state.modules
    before = set(threading.enumerate())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:17668") as client:
            initial = (await client.get("/api/v1/bootstrap")).json()
            client.headers["X-Framework-Token"] = initial["csrf_token"]
            installed = initial["modules"]
            assert installed and all(item["status"] == "ready" for item in installed), installed
            assert not {"pypdf", "pypdfium2"}.intersection(sys.modules), "Document engines must load on demand, not during application startup"
            ids = [item["id"] for item in installed]

            async def toggle(module_id, enabled):
                response = await client.put("/api/v1/modules/" + module_id, json={"enabled": enabled})
                assert response.status_code == 200, (module_id, response.text)
                result = next(item for item in response.json()["modules"] if item["id"] == module_id)
                assert result["status"] == ("ready" if enabled else "disabled"), result

            # Full composition reaches the public context endpoint used by both consumers.
            assert (await client.get("/api/v1/modules/assistant/context")).status_code == 200
            assert (await manager.call_api("courses", "/context", method="POST", body={})).status_code == 200
            for item in installed:
                module_id = item["id"]
                if manager.entries[module_id].context:
                    manager.entries[module_id].context.store.write("lifecycle-fixture", "preserve")
                others = {key: entry.info["revision"] for key, entry in manager.entries.items() if key != module_id}
                await toggle(module_id, False)
                assert (await manager.call_api(module_id)).status_code == 404
                if item["frontend_url"]:
                    assert (await client.get(item["frontend_url"])).status_code == 404
                assert others == {key: entry.info["revision"] for key, entry in manager.entries.items() if key != module_id}
                await toggle(module_id, True)
                if manager.entries[module_id].context:
                    assert manager.entries[module_id].context.store.read("lifecycle-fixture") == "preserve"

            await toggle("courses", False)
            for module_id, route in (("assistant", "/context"), ("dashboard", "/snapshot"), ("assignments", "/snapshot")):
                assert (await manager.call_api(module_id, route)).status_code == 409
            assert (await manager.call_api("notifications", "/generate", method="POST", body={})).status_code == 409
            await toggle("courses", True)
            assert (await manager.call_api("assistant", "/context")).status_code == 200

            for module_id in ids:
                await toggle(module_id, False)
            assert not [t for t in threading.enumerate() if t not in before and t.name.startswith("campus-")]
            # Each real module can start alone. Optional dependencies may report 409.
            for module_id in ids:
                await toggle(module_id, True)
                entry = manager.entries[module_id]
                if entry.app:
                    assert (await manager.call_api(module_id, "/openapi.json")).status_code == 200
                    route = "/profile" if module_id == "academic-assistant" else "/context" if module_id == "assistant" else "/modes" if module_id == "education" else "/snapshot"
                    response = await manager.call_api(module_id, route)
                    assert response.status_code in {200, 404, 409}, (module_id, response.status_code, response.text)
                await toggle(module_id, False)
            # Remove only the synthetic copies' manifests, then exercise a genuinely empty registry.
            for path in module_root.glob("*/module.json"):
                path.unlink()
            empty = (await client.post("/api/v1/modules/reload")).json()
            assert empty["modules"] == [] and [c["id"] for c in empty["categories"]] == ["settings"]
            assert (await client.get("/")).status_code == 200
            assert (await client.get("/api/v1/settings")).status_code == 200
            assert (await client.get("/api/v1/auth/providers")).status_code == 200
    assert not [t for t in threading.enumerate() if t not in before and t.name.startswith("campus-")]
    print(f"module boundaries: {len(installed)} modules integrated, independently started, stopped, restored and removed; dependencies degrade; workers cleaned")


if __name__ == "__main__":
    boundaries()
    temporary = PROJECT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="boundaries-", dir=temporary) as directory:
        asyncio.run(check(Path(directory)))
