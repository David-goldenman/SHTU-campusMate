"""Offline AI contract check; only synthetic credentials and HTTP responses."""
import asyncio
import copy
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI, HTTPException

from backend.services.ai import AIService, create_router
from backend.services.ai.routes import AISettings


class Memory:
    def __init__(self):
        self.values = {}

    def read(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def write(self, key, value):
        self.values[key] = copy.deepcopy(value)

    def get(self, key):
        return self.read(key, {})

    def save(self, key, value):
        self.write(key, value)

    def delete(self, key):
        self.values.pop(key, None)


def main():
    store, vault, requests = Memory(), Memory(), []
    mode = "text"

    def remote(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-ai-check-key"
        assert "synthetic-ai-check-key" not in str(payload)
        assert payload["model"] == "deepseek-flash"
        assert payload["thinking"] == {"type": "disabled"}
        if mode == "error":
            return httpx.Response(401, text="synthetic-private-provider-body")
        if mode == "network":
            raise httpx.ConnectError("synthetic-private-network-error", request=request)
        content = {"text": "资料摘要"} if mode == "json" else "资料摘要"
        if mode in {"json", "bad-json"}:
            assert payload["response_format"] == {"type": "json_object"}
            assert "JSON" in payload["messages"][0]["content"]
            content = json.dumps(content, ensure_ascii=False)
        else:
            assert "response_format" not in payload
        if mode == "bad-json":
            content = "[1, 2]"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content}}], "usage": {"total_tokens": 12}})

    service = AIService(vault, store, transport=httpx.MockTransport(remote))
    assert service.settings() == {"enabled": False, "model": "deepseek-flash", "key_saved": False}
    try:
        service.generate("总结资料")
        raise AssertionError("Unconfigured AI must stop")
    except HTTPException as error:
        assert error.status_code == 409
    configured = service.save_settings(AISettings(enabled=True, api_key="synthetic-ai-check-key"))
    assert configured["key_saved"] and "synthetic" not in str(configured)
    assert "synthetic" not in str(store.values)
    answer = service.generate("总结资料", "调用方选择的正文")
    assert answer == {"content": "资料摘要", "model": "deepseek-flash", "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 12}}
    assert json.loads(requests[-1]["messages"][-1]["content"])["context"] == "调用方选择的正文"
    mode = "json"
    assert service.chat([{"role": "user", "content": "分类资料"}], "json")["content"] == {"text": "资料摘要"}
    for failure in ("error", "network", "bad-json"):
        mode = failure
        try:
            service.chat([{"role": "user", "content": "总结资料"}], "json" if failure == "bad-json" else "text")
            raise AssertionError("Provider failure must stop")
        except HTTPException as error:
            assert error.status_code == 502 and "synthetic" not in error.detail

    async def routes():
        nonlocal mode
        app = FastAPI()
        app.include_router(create_router(service), prefix="/api/v1")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            settings = await client.get("/api/v1/ai/settings")
            assert settings.json()["key_saved"] and "synthetic" not in settings.text
            mode = "text"
            result = await client.post("/api/v1/ai/generate", json={"prompt": "总结资料", "context": "示例正文"})
            assert result.status_code == 200 and result.json()["content"] == "资料摘要"
            assert (await client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "你好"}]})).status_code == 200
            assert (await client.post("/api/v1/ai/chat", json={"messages": []})).status_code == 422
            assert (await client.post("/api/v1/ai/chat", json={"messages": [{"role": "tool", "content": "x"}]})).status_code == 422
            assert (await client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "x" * 120000}, {"role": "user", "content": "x"}]})).status_code == 422
            assert (await client.post("/api/v1/ai/generate", json={"prompt": "总结", "format": "html"})).status_code == 422
            assert (await client.put("/api/v1/ai/settings", json={"api_key": "key with spaces"})).status_code == 400
            assert (await client.put("/api/v1/ai/settings", json={"enabled": True, "delete_key": True})).status_code == 400
            deleted = await client.put("/api/v1/ai/settings", json={"enabled": False, "delete_key": True})
            assert deleted.status_code == 200 and not deleted.json()["key_saved"]
            assert not vault.get("ai:deepseek")
    asyncio.run(routes())
    print("PASS: AI settings, secret boundary, text/JSON generation, chat and safe provider errors")


if __name__ == "__main__":
    main()
