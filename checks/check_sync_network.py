"""Sync failures retain safe evidence, respect account changes, and explain current probes."""
import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.auth import LoginRequired, network
from backend.services.auth.routes import create_router
from backend.services.campus import Source, SourceError
from checks.module_support import load, sandbox


URL = "https://eams.shanghaitech.edu.cn/private?ticket=synthetic-secret"
DNS = {"status": "ok", "addresses": ["10.15.1.1"], "kinds": ["private"]}
OK = {"status": "reachable", "reachable": True, "http_status": 200}
FAIL = {"status": "timeout", "reachable": False}
now = datetime.now(timezone.utc)
marker = network.failure_context(httpx.ConnectTimeout("synthetic-secret", request=httpx.Request("GET", URL)), "timetable")
assert marker["host"] == "eams.shanghaitech.edu.cn"
assert "synthetic-secret" not in json.dumps(marker) and "/private" not in json.dumps(marker)
assert network.failure_context(ValueError("parsing"), "timetable") is None
assert network.failure_context(httpx.ConnectError("x", request=httpx.Request("GET", "https://other.example/private")), "elrc")["host"] is None

mode, calls = "success", 0
def respond(request):
    global calls
    calls += 1
    if mode in {"network", "partial", "account"} or mode == "retry" and calls == 1:
        raise httpx.ConnectTimeout("synthetic-secret", request=request)
    if mode == "permission":
        return httpx.Response(403)
    if mode == "login":
        return httpx.Response(401)
    return httpx.Response(200, json={})

with sandbox("sync-network", respond) as context:
    def fetch(remote, previous):
        try:
            remote.json("GET", URL)
        except SourceError:
            if mode == "account":
                context.auth.revision = "new-account"
            if mode != "partial":
                raise
            return {**previous, "issues": ["One resource unavailable"]}
        return {"courses": [{"id": "synthetic:1", "source": "synthetic", "title": "Cached course"}]}
    source = Source(context, "ids", ["eams.shanghaitech.edu.cn"], fetch, network_target="timetable")
    try:
        source.run()
        original = source.snapshot()["data"]
        for mode in ("network", "partial"):
            source.run()
            result = source.snapshot()
            assert result["status"] == ("partial" if mode == "partial" else "error")
            assert result["data"]["courses"] == original["courses"]
            assert result["network_failure"]["kind"] == "timeout"
            assert "synthetic-secret" not in json.dumps(result)
        for mode in ("permission", "login", "retry", "success"):
            calls = 0
            source.run()
            result = source.snapshot()
            assert "network_failure" not in result
            assert result["status"] == ("error" if mode == "permission" else "login_required" if mode == "login" else "ready")
        with patch.object(context.auth, "read_with_recovery", side_effect=httpx.ConnectError("Synthetic auth failure", request=httpx.Request("GET", "https://ids.shanghaitech.edu.cn/authserver/login"))):
            source.run()
            assert source.snapshot()["network_failure"]["host"] == "ids.shanghaitech.edu.cn"
        with patch.object(context.auth, "read_with_recovery", side_effect=ValueError("Synthetic parser failure")):
            source.run()
            assert "network_failure" not in source.snapshot() and source.snapshot()["data"]["courses"] == original["courses"]
        mode = "success"
        source.run()
        mode = "account"
        source.run()
        assert source.snapshot()["data"]["courses"] == [] and "network_failure" not in source.snapshot()
        assert context.store.read(source.sync_key)["status"] == "ready", "Old account failure must not overwrite state"
    finally:
        source.close()

services = [{"id": key, "name": name, "host": httpx.URL(url).host, "dns": DNS, "direct": OK, "proxy": FAIL,
             "diagnosis": network.diagnosis(DNS, OK, FAIL)} for key, name, url in network.TARGETS_TO_CHECK]
report = {"checked_at": now.isoformat(), "services": services}
explanation = network.explain_failure(marker, report)
assert explanation["diagnosis"]["code"] == "sync_connection", "An unrelated proxy failure is not the cause of a direct sync failure"
for kind, code in (("tls_error", "tls"), ("dns_error", "dns"), ("configuration_error", "configuration"), ("proxy_error", "proxy")):
    services[1]["dns"] = {**DNS, "kinds": ["synthetic"], "status": "dns_timeout"}
    assert network.explain_failure({**marker, "kind": kind}, report)["diagnosis"]["code"] == code
services[0].update(direct=FAIL, diagnosis=network.diagnosis(DNS, FAIL, None))
assert network.explain_failure({**marker, "host": services[0]["host"]}, report)["entry"]["id"] == "ids"

async def caching():
    diagnostics = network.NetworkDiagnostics()
    with patch.object(network, "probe_client", return_value=None), patch.object(network, "getproxies", return_value={}), \
         patch.object(network, "check_target", AsyncMock(return_value={"direct": OK})) as probe:
        first = await diagnostics.check()
        await diagnostics.check(after=now - timedelta(seconds=1))
        assert probe.await_count == 5
        await diagnostics.check(after=datetime.fromisoformat(first["checked_at"]) + timedelta(microseconds=1))
        assert probe.await_count == 10, "A new failure must not reuse a pre-failure probe"
asyncio.run(caching())

app = FastAPI()
app.include_router(create_router(None))
with TestClient(app) as client, patch.object(network.NetworkDiagnostics, "check", AsyncMock(return_value=report)) as probe:
    for invalid in ([], [marker] * 7, [{**marker, "target": "other"}], [{**marker, "kind": "parse"}]):
        assert client.post("/auth/network/explain", json={"failures": invalid}).status_code == 422
    result = client.post("/auth/network/explain", json={"failures": [{**marker, "host": "untrusted.example", "at": "2099-01-01T00:00:00"}]})
    assert result.status_code == 200 and result.json()["reports"][0]["entry"]["id"] == "timetable"
    assert probe.call_args.kwargs["after"] <= datetime.now(timezone.utc)

elrc = load("elrc")
with sandbox("elrc-inline", lambda request: (_ for _ in ()).throw(httpx.ConnectError("synthetic-secret", request=request))) as context:
    app = FastAPI()
    app.include_router(elrc.create_router(context))
    try:
        with TestClient(app) as client:
            response = client.post("/discover", json={"semester": "current"})
            assert response.status_code == 502 and response.json()["detail"]["network_failure"]["target"] == "elrc"
            with patch.object(elrc.ContentLibrary, "course", return_value={"id": "synthetic"}):
                response = client.post("/courses/synthetic/sync", json={"force": False})
                assert response.status_code == 502 and response.json()["detail"]["network_failure"]["kind"] == "connection_error"
                assert client.get("/sync").json()["network_failure"]["id"] == response.json()["detail"]["network_failure"]["id"]
                assert "synthetic-secret" not in response.text
            with patch.object(context.auth, "authenticated_client", side_effect=LoginRequired("Login needed")):
                try:
                    client.post("/discover", json={"semester": "current"})
                    raise AssertionError("Login failure should not become a network error")
                except LoginRequired:
                    pass
    finally:
        elrc.stop(context)

print("sync diagnostics: typed whole/partial failures, retry recovery, cache/account isolation, evidence precedence, bounded API and native ELRC passed")
