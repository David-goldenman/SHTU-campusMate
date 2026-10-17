"""Synthetic diagnostics: evidence, no credentials, deadlines, coalescing and local API."""
import asyncio
import json
import os
import socket
import ssl
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend.core.store import Store
from backend.main import create_app
from backend.services.auth import network, protocols


DNS = {"status": "ok", "addresses": ["10.15.1.1"], "kinds": ["private"]}
OK = {"status": "reachable", "reachable": True, "http_status": 200, "elapsed_ms": 1}
FAIL = {"status": "timeout", "reachable": False, "elapsed_ms": 1}


async def probe(url):
    client = network.probe_client()
    if client is None:
        return await network.probe(url, None)
    async with client:
        client.cookies.set('must-not-send', 'synthetic', domain='ids.shanghaitech.edu.cn')
        return await network.probe(url, client)


async def checks():
    assert network.address_kind("198.18.1.2") == "synthetic"
    assert network.address_kind("10.15.44.85") == "private"
    assert network.address_kind("127.0.0.1") == "special"
    assert network.address_kind("2001:4860:4860::8888") == "public"
    assert network.diagnosis(DNS, OK, FAIL)["code"] == "proxy"
    # A successful anonymous probe must not promise sync when the application
    # cannot initialize its configured environment proxy.
    with patch.dict(os.environ, {"HTTPS_PROXY": "invalid-proxy://127.0.0.1:9"}):
        try:
            with protocols.http_client():
                raise AssertionError("Invalid proxy scheme unexpectedly initialized")
        except protocols.NetworkConfigurationError:
            pass
        assert network.probe_client("invalid-proxy://127.0.0.1:9") is None
    finding = network.diagnosis(DNS, OK, {**FAIL, "status": "configuration_error"})
    assert finding["code"] == "proxy_configuration" and "可继续同步" not in " ".join(finding["actions"])
    finding = network.diagnosis(DNS, {**OK, "status": "login_required", "http_status": 401}, FAIL)
    assert "登录" in " ".join(finding["actions"])
    for status, code in (("tls_error", "tls"), ("configuration_error", "configuration")):
        assert network.diagnosis({**DNS, "status": "dns_timeout"}, {**FAIL, "status": status}, None)["code"] == code
    finding = network.diagnosis(DNS, FAIL, None)
    assert finding["code"] == "campus_route" and finding["confidence"] == "suspected"
    assert "无法" in finding["message"] and "服务故障" in " ".join(finding["actions"])
    assert network.diagnosis(DNS, FAIL, OK)["code"] == "direct_route"
    assert network.diagnosis({**DNS, "kinds": ["synthetic"]}, FAIL, None)["code"] == "dns_proxy"
    assert network.diagnosis({**DNS, "status": "dns_timeout"}, FAIL, OK)["code"] == "dns"
    assert network.diagnosis(DNS, {**FAIL, "status": "tls_error"}, None)["code"] == "tls"
    for code, status, expected in [(401, "login_required", "reachable"), (403, "access_denied", "access"),
                                   (503, "service_error", "service")]:
        assert network.diagnosis(DNS, {**OK, "status": status, "http_status": code}, None)["code"] == expected
    assert network.diagnosis({**DNS, "kinds": ["public"]}, FAIL, None)["confidence"] == "unknown"

    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", AsyncMock(side_effect=socket.gaierror("private DNS details"))):
        assert (await network.resolve("school.example", 443))["status"] == "dns_error"
    async def hang(*args, **kwargs):
        await asyncio.sleep(60)
    with patch.object(loop, "getaddrinfo", hang), patch.object(network, "DNS_TIMEOUT", 0.01):
        assert (await network.resolve("school.example", 443))["status"] == "dns_timeout"

    seen = []
    def transport(**options):
        assert options["trust_env"] is True and options["retries"] == 0
        async def respond(request):
            seen.append(str(request.url))
            assert request.method == "GET" and "cookie" not in request.headers and "authorization" not in request.headers
            return httpx.Response(302, headers={"location": "https://untrusted.example/private-ticket"})
        return httpx.MockTransport(respond)
    with patch.object(network.httpx, "AsyncHTTPTransport", transport):
        result = await probe("https://ids.shanghaitech.edu.cn/authserver/login")
        assert result["reachable"] and result["http_status"] == 302 and len(seen) == 1
        assert "private-ticket" not in json.dumps(result)

    for error, expected in [(httpx.ConnectTimeout("secret://user:password"), "timeout"),
                            (httpx.ProxyError("secret proxy credentials"), "proxy_error"),
                            (httpx.RemoteProtocolError("private response"), "protocol_error")]:
        async def fail(request):
            raise error
        with patch.object(network.httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(fail)):
            result = await probe("https://ids.shanghaitech.edu.cn/")
            assert result["status"] == expected and "secret" not in json.dumps(result)
    try:
        try:
            raise ssl.SSLCertVerificationError("private CA info")
        except ssl.SSLError as error:
            raise httpx.ConnectError("connection failed") from error
    except httpx.ConnectError as error:
        assert network.error_kind(error) == "tls_error"
    with patch.object(network.httpx, "AsyncHTTPTransport", side_effect=ValueError("secret malformed proxy")):
        assert (await probe("https://ids.shanghaitech.edu.cn/"))["status"] == "configuration_error"
    with patch.object(network.httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(hang)), \
         patch.object(network, "PROBE_TIMEOUT", 0.01):
        assert (await probe("https://ids.shanghaitech.edu.cn/"))["status"] == "timeout"
        task = asyncio.create_task(probe("https://ids.shanghaitech.edu.cn/"))
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
            raise AssertionError("Probe cancellation was swallowed")
        except asyncio.CancelledError:
            pass

    async def fake_probe(url, client):
        return FAIL if client is None else OK
    original_client = network.probe_client
    def fake_client(proxy=None):
        return None if proxy else original_client()
    with patch.object(network, "resolve", AsyncMock(return_value=DNS)), \
         patch.object(network, "probe_client", side_effect=fake_client), \
         patch.object(network, "probe", AsyncMock(side_effect=fake_probe)) as probe_mock, \
         patch.object(network, "getproxies", return_value={"https": "http://user:secret@proxy.example:7890"}):
        diagnostics = network.NetworkDiagnostics()
        assert diagnostics.snapshot()["checked_at"] is None
        first, second = await asyncio.gather(diagnostics.check(), diagnostics.check())
        assert first == second and probe_mock.await_count == 12
        assert first["reachable_count"] == 6 and first["vpn_status"] == first["campus_location"] == "unknown"
        assert any(item["id"] == "ecourse" for item in first["services"])
        assert all(item["diagnosis"]["code"] == "proxy" for item in first["services"])
        assert "secret" not in json.dumps(first) and "proxy.example" not in json.dumps(first)
        diagnostics.completed -= 10
        await diagnostics.check()
        assert probe_mock.await_count == 24


asyncio.run(checks())

temporary = PROJECT / ".codex" / "tmp"
temporary.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=temporary) as directory:
    root = Path(directory)
    (root / "modules").mkdir()
    app = create_app(store=Store(root / "store.sqlite3"), modules_root=root / "modules", data_dir=root)
    with TestClient(app, base_url="http://127.0.0.1:16666") as client, \
         patch.object(network.NetworkDiagnostics, "check", AsyncMock(return_value={"checked_at": "synthetic", "services": []})) as check:
        assert client.get("/api/v1/auth/network").json() == {"checked_at": None, "services": []}
        assert check.await_count == 0
        assert client.post("/api/v1/auth/network/check").status_code == 403
        assert client.post("/api/v1/auth/network/explain", json={"failures": []}).status_code == 403
        token = client.get("/api/v1/bootstrap").json()["csrf_token"]
        response = client.post("/api/v1/auth/network/check", headers={"X-Framework-Token": token})
        assert response.status_code == 200 and check.await_count == 1
        assert client.get("/api/v1/auth/network", headers={"Origin": "https://untrusted.example"}).status_code == 403

print("network diagnostics: DNS, proxy, VPN uncertainty, TLS, HTTP states, anonymity, cancellation, bounds and API passed")
