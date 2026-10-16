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
    study = directory / "modules" / "study"
    shutil.copytree(PROJECT / "modules" / "academic-assistant" / "harness", study / "harness")
    (study / "module.json").write_text(json.dumps({**manifest, "id": "study", "name": "学习工具"}), encoding="utf-8")
    requests, workspaces, started, release = [], [], threading.Event(), threading.Event()
    live, streamed, streaming = [], threading.Event(), False
    cancelling, release_cancel = False, threading.Event()
    items = [{"id": "late", "title": "实验", "due_at": "2026-10-21T12:00:00+08:00"},
             {"id": "early", "title": "阅读", "due_at": "2026-10-20T12:00:00+08:00"}]

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == '/tools/query':
                assert self.headers.get('Authorization') == 'Bearer synthetic-tool-token'
                assert body == {'area': 'assignments', 'pending': True}
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'items': [{'source_id': 'synthetic:assignment', 'text': '合成作业'}]}).encode())
                return
            requests.append((body, self.headers.get("Authorization")))
            study_task = any(tool['function']['name'] == 'study_query' for tool in body['tools'])
            first = not any(message["role"] == "tool" for message in body["messages"])
            if first:
                started.set()
                release.wait(120)
                calls = [{"index": index, "id": "call-" + str(index), "type": "function", "function": {
                    "name": "order_deadlines", "arguments": json.dumps({"items": value})}}
                         for index, value in enumerate((items, [{**items[0], "due_at": "tomorrow"}]))]
                if study_task:
                    calls = [{'index': 0, 'id': 'study-call', 'type': 'function', 'function': {'name': 'study_query', 'arguments': json.dumps({'area': 'assignments', 'pending': True})}}]
                    calls.append({'index': 1, 'id': 'skill-call', 'type': 'function', 'function': {'name': 'skill', 'arguments': json.dumps({'name': 'campus-planning'})}})
                delta, finish = {"tool_calls": calls}, "tool_calls"
            else:
                if study_task:
                    output = json.loads(next(message['content'] for message in body['messages'] if message['role'] == 'tool'))
                    artifact = workspaces[-1] / output['workspace_file']
                    saved = artifact.read_text(encoding='utf-8')
                    assert json.loads(saved)['arguments']['area'] == 'assignments' and 'synthetic-tool-token' not in saved
                delta, finish = {"content": "已读取合成作业" if study_task else "已按截止时间整理"}, "stop"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for change, reason in ((delta, None), ({}, finish)):
                chunk = {"id": "synthetic", "object": "chat.completion.chunk", "model": body["model"],
                         "choices": [{"index": 0, "delta": change, "finish_reason": reason}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
                if streaming and study_task and not first and reason is None:
                    if cancelling:
                        release_cancel.wait(15)
                        return
                    else:
                        assert streamed.wait(10), 'Live frame must arrive before the model response ends'
            self.wfile.write(b"data: [DONE]\n\n")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = Store(directory / "state.sqlite3")
    app = create_app(active_port=17666, store=store, vault=MemoryVault(), modules_root=plugin.parent.parent, data_dir=directory / "private")

    def runtime(**options):
        workspaces.append(Path(options['cwd']))
        assert workspaces[-1].is_relative_to(directory / 'private' / 'runtime' / 'tmp')
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
                        assert payload['thinking']['type'] == 'enabled' and payload['reasoning_effort'] == 'low'
                        assert [tool["function"]["name"] for tool in payload["tools"]] == ["order_deadlines"]
                    package.pop("dsh")
                    package["main"] = "../outside.js"
                    (plugin / "package.json").write_text(json.dumps(package), encoding="utf-8")
                    (plugin.parent / "outside.js").write_text("export function apply() {}", encoding="utf-8")
                    refreshed = (await client.post("/api/v1/modules/reload")).json()["modules"]
                    assert refreshed[0]["status"] == "error" and "harness 目录" in refreshed[0]["error"]
                    streaming = True

                    def on_event(frame):
                        live.append(frame)
                        if frame['type'] == 'chunk' and frame['chunk']['type'] == 'text-delta':
                            streamed.set()

                    result = await asyncio.to_thread(app.state.ai.run, prompt='读取待完成作业', plugins=['study'], on_event=on_event,
                                                    plugin_env={'CAMPUS_PLUGIN_STUDY_URL': f'http://127.0.0.1:{server.server_port}', 'CAMPUS_PLUGIN_STUDY_TOKEN': 'synthetic-tool-token'})
                    assert result['content'] == '已读取合成作业' and result['tools'][0]['is_error'] is False
                    assert any(tool['name'] == 'skill' and not tool['is_error'] for tool in result['tools'])
                    assert {tool['function']['name'] for tool in requests[-1][0]['tools']} == {'skill', 'study_query', 'study_search', 'study_document', 'study_course_search', 'study_remember', 'study_navigate', 'study_finish'}
                    assert 'synthetic-tool-token' not in json.dumps(requests[-2:])
                    assert not any(path.exists() for path in workspaces)
                    assert any(frame['type'] == 'chunk' and frame['chunk']['type'] == 'text-delta' for frame in live)
                    cancelling, cancelled = True, threading.Event()

                    def cancel_on_text(frame):
                        if frame['type'] == 'chunk' and frame['chunk']['type'] == 'text-delta':
                            cancelled.set()

                    try:
                        await asyncio.wait_for(asyncio.to_thread(app.state.ai.run, prompt='停止合成流式任务', plugins=['study'],
                            on_event=cancel_on_text, cancel_event=cancelled,
                            plugin_env={'CAMPUS_PLUGIN_STUDY_URL': f'http://127.0.0.1:{server.server_port}', 'CAMPUS_PLUGIN_STUDY_TOKEN': 'synthetic-tool-token'}), 12)
                        raise AssertionError('Cancelled runtime must stop')
                    except Exception as error:
                        assert getattr(error, 'status_code', None) == 409, repr(error)
                    finally:
                        release_cancel.set()
                    assert cancelled.is_set() and not any(path.exists() for path in workspaces)
    finally:
        release_cancel.set()
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
