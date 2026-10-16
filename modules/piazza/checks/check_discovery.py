"""Synthetic checks for course discovery, term matching and cache preservation."""
import asyncio
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI

from backend.core.store import Store
from backend.main import runtime_error
from modules.piazza.server import create_router
from modules.piazza.server.courses import course_catalog, school_reference

FALL = {"id": "2026-2027-1", "name": "2026-2027学年秋季"}
SPRING = {"id": "2026-2027-2", "name": "2026-2027学年春季"}
ROWS = [
    {"id": "current", "name": "Current course", "course_number": "TEST101", "term": "Fall 2026", "status": "inactive", "prof_hash": "must-not-leak"},
    {"id": "old-active", "name": "Old active course", "term": "Spring 2026", "status": "active"},
    {"id": "no-term", "name": "Course with no term", "status": "active", "start_date": "2026-09-01"},
    {"id": "other", "name": "Other term", "term": "Other"},
    {"id": "future", "name": "Next term", "term": "Spring 2027"},
]


def check_terms():
    courses = course_catalog({"networks": ROWS}, school_reference(FALL))
    states = {course["id"]: course["semester_state"] for course in courses}
    assert states == {"current": "current", "old-active": "other", "no-term": "unknown", "other": "unknown", "future": "other"}
    assert all(course["semester_state"] == "unknown" for course in course_catalog({"networks": ROWS}, None))
    assert school_reference(SPRING)["year"] == 2027
    assert school_reference({"id": "wrong", "name": FALL["name"]}) is None
    assert "must-not-leak" not in json.dumps(courses)
    assert len(course_catalog({"networks": [ROWS[0], ROWS[0]]}, school_reference(FALL))) == 1
    print("PASS term matching: official term, active!=current, unknown terms, spring year, safe fields, deduplication")


async def check_api(directory):
    broken = False

    def upstream(request):
        payload = json.loads(request.content)
        assert payload == {"method": "user.status", "params": {}}
        assert request.url.host == "piazza.com"
        return httpx.Response(200, json={"result": {"networks": {} if broken else ROWS, "sid": "must-not-leak", "email": "must-not-leak"}})

    @contextmanager
    def authenticated(provider):
        assert provider == "piazza"
        with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
            yield client

    store = Store(directory / "settings.sqlite3")
    store.write("courses", [{"id": "manual", "name": "Keep selected"}])
    app = FastAPI(exception_handlers={RuntimeError: runtime_error})
    app.include_router(create_router(SimpleNamespace(store=store, auth=SimpleNamespace(authenticated_client=authenticated))))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.get('/catalog')).json()["courses"] == []
        response = await client.post('/discover', json={"current_semester": FALL})
        assert response.status_code == 200, response.text
        assert "must-not-leak" not in response.text
        assert response.json()["courses"][0]["id"] == "current"
        assert (await client.get('/courses')).json()["courses"] == [{"id": "manual", "name": "Keep selected"}]
        before = (await client.get('/catalog')).json()
        broken = True
        assert (await client.post('/discover', json={"current_semester": FALL})).status_code == 400
        assert (await client.get('/catalog')).json() == before
    store.close()
    print("PASS discovery API: scoped auth, safe output, cached catalog, preserved selections, malformed-response preservation")


if __name__ == '__main__':
    check_terms()
    target = ROOT / '.codex' / 'tmp'
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target, prefix='piazza-discovery-') as directory:
        asyncio.run(check_api(Path(directory)))
