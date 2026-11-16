"""The presentation cache's ownership check must not aggregate or fetch data."""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checks.module_support import load, sandbox


def external(request):
    raise AssertionError('An ownership check must not contact school services')


async def other_module(*args, **kwargs):
    raise AssertionError('An ownership check must not assemble another module')


for name in ('courses', 'dashboard', 'assignments', 'timetable'):
    package = load(name)
    with sandbox(name, external) as context:
        context.api = other_module
        app = FastAPI()
        app.include_router(package.create_router(context))
        with TestClient(app) as client:
            first = client.get('/view-state')
            assert first.status_code == 200
            assert set(first.json()) == {'account_revision'}
            assert first.json()['account_revision']
            context.auth.revision = 'synthetic-other-account'
            second = client.get('/view-state')
            assert second.status_code == 200
            assert second.json()['account_revision'] != first.json()['account_revision']
        package.stop(context) if hasattr(package, 'stop') else None

print('view state: four local-only ownership checks; no external calls, aggregation or account details; account switching passed')
