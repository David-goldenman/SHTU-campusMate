"""Exercise the official runtime and native plugins against a local synthetic LLM."""
import asyncio
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import httpx
from deepseek_harness import DeepSeekHarness

from backend.core.store import Store
from backend.main import create_app
from checks.check_framework import MemoryVault


async def check(directory):
    plugin = directory / "modules" / "planner" / "harness"
    shutil.copytree(PROJECT / "modules" / "deadlines" / "harness", plugin)
    manifest = {"id": "planner", "name": "截止时间整理", "version": "0.1.0", "category": "assistant", "api_version": 1}
    (plugin.parent / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    requests, started, release = [], threading.Event(), threading.Event()
    items = [{"id": "late", "title": "实验", "due_at": "2026-10-21T12:00:00+08:00"},
             {"id": "early", "title": "阅读", "due_at": "2026-10-20T12:00:00+08:00"}]

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((body, self.headers.get("Authorization")))
            first = not any(message["role"] == "tool" for message in body["messages"])
            if first:
                started.set()
                release.wait(120)
                calls = [{"index": index, "id": "call-" + str(index), "type": "function", "function": {
                    "name": "order_deadlines", "arguments": json.dumps({"items": value})}}
                         for index, value in enumerate((items, [{**items[0], "due_at": "tomorrow"}]))]
                delta, finish = {"tool_calls": calls}, "tool_calls"
            else:
                delta, finish = {"content": "已按截止时间整理"}, "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for change, reason in ((delta, None), ({}, finish)):
                chunk = {"id": "synthetic", "object": "chat.completion.chunk", "model": body["model"],
                         "choices": [{"index": 0, "delta": change, "finish_reason": reason}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(directory / "state.sqlite3")
    app = create_app(active_port=17666, store=store, vault=MemoryVault(), modules_root=plugin.parent.parent, data_dir=directory / "private")

    def runtime(**options):
        return DeepSeekHarness(**{**options, "base_url": f"http://127.0.0.1:{server.server_port}/v1"})

    try:
        with patch("backend.services.ai.harness.DeepSeekHarness", runtime):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:17666") as client:
                    body = {"prompt": "整理所选事项", "context": json.dumps(items), "plugins": ["planner"]}
                    assert (await client.post("/api/v1/ai/run", json=body)).status_code == 403
                    client.headers["X-Framework-Token"] = (await client.get("/api/v1/bootstrap")).json()["csrf_token"]
                    assert (await client.post("/api/v1/ai/run", json=body)).status_code == 409
                    await client.put("/api/v1/ai/settings", json={"enabled": True, "api_key": "synthetic-harness-key"})
                    assert (await client.post("/api/v1/ai/run", json={**body, "plugins": []})).status_code == 422
                    assert (await client.post("/api/v1/ai/run", json={**body, "plugins": ["planner", "planner"]})).status_code == 422
                    assert (await client.get("/api/v1/ai/plugins")).json()["plugins"][0]["status"] == "ready"
                    pending = asyncio.create_task(client.post("/api/v1/ai/run", json=body))
                    try:
                        assert await asyncio.to_thread(started.wait, 120), "Native runtime did not reach the synthetic model"
                        assert (await client.put("/api/v1/modules/planner", json={"enabled": False})).status_code == 409
                        assert (await client.post("/api/v1/modules/reload")).status_code == 409
                        assert (await client.post("/api/v1/data/clear", json={"scope": "modules", "confirmation": "CLEAR"})).status_code == 409
                    finally:
                        release.set()
                    response = await pending
                    assert response.status_code == 200, response.text
                    result = response.json()
                    assert result["content"] == "已按截止时间整理"
                    assert [tool["is_error"] for tool in result["tools"]] == [False, True], result
                    tool_results = [message for message in requests[1][0]["messages"] if message["role"] == "tool"]
                    assert [item["id"] for item in json.loads(tool_results[0]["content"])] == ["early", "late"]
                    assert "有效截止时间" in tool_results[1]["content"]
                    await client.put("/api/v1/modules/planner", json={"enabled": False})
                    assert (await client.post("/api/v1/ai/run", json=body)).status_code == 404
                    package = json.loads((plugin / "package.json").read_text(encoding="utf-8"))
                    package.update(version="0.1.1", dsh={"bundle": {"patch": "cordis.patch.yml"}})
                    (plugin / "package.json").write_text(json.dumps(package), encoding="utf-8")
                    (plugin / "cordis.patch.yml").write_text(json.dumps([{"insert": [{"id": "campus-planner", "name": "campus-deadlines"}]}]), encoding="utf-8")
                    source = (plugin / "index.js").read_text(encoding="utf-8")
                    (plugin / "index.js").write_text(source.replace("按明确截止时间从早到晚排列", "版本二：按明确截止时间从早到晚排列"), encoding="utf-8")
                    await client.put("/api/v1/modules/planner", json={"enabled": True})
                    response = await client.post("/api/v1/ai/run", json=body)
                    assert response.status_code == 200, response.text
                    assert requests[2][0]["tools"][0]["function"]["description"].startswith("版本二：")
                    assert len(requests) == 4
                    for payload, authorization in requests:
                        assert authorization == "Bearer synthetic-harness-key"
                        assert "synthetic-harness-key" not in json.dumps(payload)
                        assert [tool["function"]["name"] for tool in payload["tools"]] == ["order_deadlines"]
                    package.pop("dsh")
                    package["main"] = "../outside.js"
                    (plugin / "package.json").write_text(json.dumps(package), encoding="utf-8")
                    (plugin.parent / "outside.js").write_text("export function apply() {}", encoding="utf-8")
                    refreshed = (await client.post("/api/v1/modules/reload")).json()["modules"]
                    assert refreshed[0]["status"] == "error" and "harness 目录" in refreshed[0]["error"]
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    temporary = PROJECT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-harness-", dir=temporary) as directory:
        asyncio.run(check(Path(directory)))
    print("PASS: official runtime, native tools/bundles, tool validation, lifecycle locks, hot updates and credential boundary")
