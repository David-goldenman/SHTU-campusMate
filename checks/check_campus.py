import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from backend.services.auth import LoginRequired
from backend.services.campus import Remote, Source, SourceError, timestamp
from backend.services.campus.data import validate_bundle
from checks.module_support import sandbox


def check_remote():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, json={"results": [], "paging": {"nextPage": "/data"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        remote = Remote(client, threading.Event(), ["example.edu"])
        assert remote.json("GET", "https://example.edu/data")["results"] == [] and len(calls) == 2
        try:
            list(remote.pages("https://example.edu/data"))
            raise AssertionError("Repeated pagination must stop")
        except SourceError:
            pass
        try:
            remote.json("GET", "https://other.example/data")
            raise AssertionError("Foreign pagination hosts must be rejected")
        except SourceError:
            pass
    for response, expected in [(httpx.Response(200, text="bad-json"), SourceError), (httpx.Response(401), LoginRequired), (httpx.Response(503), SourceError)]:
        with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
            try:
                Remote(client, threading.Event(), ["example.edu"]).json("GET", "https://example.edu/data")
                raise AssertionError("Malformed or failed API responses must be exposed")
            except expected:
                pass
    assert timestamp("2026-10-01T08:00:00") == "2026-10-01T08:00:00+08:00"
    assert timestamp("not-a-date") is None
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403))) as client:
        from fastapi import HTTPException
        try:
            Remote(client, threading.Event(), ["example.edu"]).json("GET", "https://example.edu/data")
            raise AssertionError("Course permission errors must remain distinct from login expiry")
        except HTTPException as error:
            assert error.status_code == 403


def check_source():
    with sandbox("source") as context:
        source = Source(context, "ids", ["example.edu"], lambda remote, previous: {"courses": [{"id": "source:1", "source": "source", "title": "Synthetic"}]})
        source.run()
        assert source.snapshot()["status"] == "ready"
        original = source.snapshot()["data"]

        def failure(remote, previous):
            raise SourceError("Synthetic API failure")

        source.fetch = failure
        source.run()
        assert source.snapshot()["status"] == "error" and source.snapshot()["data"] == original
        source.fetch = lambda remote, previous: {"courses": "malformed"}
        source.run()
        assert source.snapshot()["data"] == original
        context.auth.revision = "synthetic-account-two"
        assert source.snapshot()["data"]["courses"] == []
        entered = threading.Event()

        def blocking(remote, previous):
            entered.set()
            remote.cancelled.wait(3)
            remote.check()

        source.fetch = blocking
        assert source.sync()["queued"] is True
        assert entered.wait(2)
        assert source.sync()["queued"] is False
        assert source.snapshot()["status"] == "syncing"
        source.close()
        assert source.future.done()
    assert validate_bundle({"courses": [{"id": "x:1", "source": "x"}]})["courses"]


def check_download():
    import asyncio
    from backend.services.campus.files import download
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"Location": "https://foreign.example/file"})
        return httpx.Response(200, content=b"%PDF-synthetic", headers={"Content-Type": "application/pdf"})

    with sandbox("files", handler) as context:
        response = download(context, "ids", ["example.edu"], lambda remote: ("https://example.edu/file", "synthetic.pdf"), threading.Event())
        assert Path(response.path).read_bytes() == b"%PDF-synthetic"
        asyncio.run(response.background())
        assert not Path(response.path).exists()
        with context.auth.authenticated_client("ids") as client:
            try:
                Remote(client, threading.Event(), ["example.edu"]).request("GET", "https://example.edu/redirect")
                raise AssertionError("Foreign redirects must not be followed")
            except LoginRequired:
                pass
        assert not any("foreign.example" in url for url in calls)


if __name__ == "__main__":
    check_remote()
    check_source()
    check_download()
    print("campus: retries, pagination bounds, malformed JSON, cache preservation, account isolation and worker cleanup passed")
