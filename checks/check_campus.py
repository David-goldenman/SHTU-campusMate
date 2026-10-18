import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

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
        expired = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        saved = context.store.read(source.snapshot_key)
        context.store.write(source.snapshot_key, {**saved, "updated_at": expired})
        entered, release, calls = threading.Event(), threading.Event(), []

        def refresh(remote, previous):
            calls.append(previous)
            entered.set()
            assert release.wait(3)
            remote.check()
            return original

        source.fetch = refresh
        cached = source.snapshot()
        assert cached["status"] == "syncing" and cached["data"] == original
        assert entered.wait(2)
        assert source.sync()["queued"] is False and source.snapshot()["status"] == "syncing"
        release.set()
        source.future.result(timeout=5)
        assert len(calls) == 1 and source.snapshot()["status"] == "ready"

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
        context.store.write(source.snapshot_key, {"owner": source.owner(), "data": original, "updated_at": expired})
        context.store.write(source.sync_key, {"owner": source.owner(), "status": "ready"})
        assert source.snapshot()["status"] == "cached", "A stopped source can expose cached data without queuing work"
    assert validate_bundle({"courses": [{"id": "x:1", "source": "x"}]})["courses"]


def check_background_refresh():
    entered, release = threading.Event(), threading.Event()
    with sandbox('background') as context, patch('backend.services.campus.source.REFRESH_SECONDS', .02):
        source = Source(context, 'ids', ['example.edu'], lambda remote, previous: previous)
        try:
            source.run()
            saved = context.store.read(source.snapshot_key)
            def refresh(remote, previous):
                entered.set()
                assert release.wait(3)
                return previous
            source.fetch = refresh
            context.store.write(source.snapshot_key, {**saved, 'updated_at': (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()})
            assert entered.wait(2), 'Expired connected caches refresh without a mounted page'
            assert source.snapshot()['status'] == 'syncing'
            assert source.sync()['queued'] is False
            release.set()
            source.future.result(timeout=2)
            assert source.snapshot()['status'] == 'ready'
        finally:
            release.set()
            source.close()
        assert not source.refresh_thread.is_alive()


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
        assert Path(response.path).is_relative_to(context.data_dir / 'tmp' / 'downloads')
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


def check_auth_cancellation():
    from backend.services.auth import AuthService
    from checks.module_support import Memory
    with sandbox("auth-cancel") as context:
        auth = AuthService(Memory(), context.store, runtime_dir=context.data_dir / 'runtime')
        cancelled, finished = threading.Event(), threading.Event()

        def waiting():
            try:
                with auth.authenticated_client("ids", cancelled=cancelled):
                    raise AssertionError("Cancelled acquisition must not enter the client")
            except RuntimeError:
                finished.set()

        with auth.locks["ids"]:
            worker = threading.Thread(target=waiting)
            worker.start()
            cancelled.set()
            assert finished.wait(2)
            worker.join()


if __name__ == "__main__":
    check_remote()
    check_source()
    check_background_refresh()
    check_download()
    check_auth_cancellation()
    print("campus: retries, pagination bounds, malformed JSON, cache preservation, account isolation and worker cleanup passed")
