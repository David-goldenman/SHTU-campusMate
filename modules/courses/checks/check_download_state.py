"""Background preflight returns only account identity, without querying sources."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.services.campus.analysis import account_revision
from checks.module_support import load, sandbox

package = load('courses')
with sandbox('courses') as context:
    async def no_source_requests(*args, **kwargs):
        raise AssertionError('Download state preflight must stay local')

    context.api = no_source_requests
    expected = account_revision(context)
    app = FastAPI()
    app.include_router(package.create_router(context))
    with TestClient(app) as client:
        response = client.get('/view-state')
        assert response.status_code == 200, response.text
        assert response.json() == {'account_revision': expected}
print('PASS: background preflight exists, exposes only current account revision and makes no source requests')
