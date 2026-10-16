"""Synthetic module checks; all files remain in the project's .codex directory."""
import copy
import importlib.util
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx

from backend.core.store import Store

PROJECT = Path(__file__).resolve().parents[1]


class Memory:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return copy.deepcopy(self.values.get(key, {}))

    def save(self, key, value):
        self.values[key] = copy.deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)


class Auth:
    def __init__(self, handler):
        self.transport = httpx.MockTransport(handler)
        self.revision = "synthetic-account-one"

    def get_status(self, provider):
        return {"username": "synthetic@example.edu", "has_session": True, "account_revision": self.revision}

    @contextmanager
    def authenticated_client(self, provider, target=None, *, cancelled=None):
        with httpx.Client(transport=self.transport, follow_redirects=True) as client:
            yield client

    def session_parameters(self, provider):
        return {"sid": "synthetic-sid"}

    def read_with_recovery(self, provider, operation, *, target=None, cancelled=None):
        with self.authenticated_client(provider, target=target, cancelled=cancelled) as client:
            return operation(client)


class AI:
    def __init__(self):
        self.result = {"content": {"text": "合成回答", "citations": []}, "model": "synthetic", "usage": {}}

    def generate(self, **kwargs):
        return copy.deepcopy(self.result)

    def chat(self, **kwargs):
        return copy.deepcopy(self.result)

    def run(self, **kwargs):
        return {**copy.deepcopy(self.result), "content": json.dumps(self.result["content"]), "tools": [{"id": "synthetic", "name": "order_deadlines", "is_error": False}]}

    def settings(self):
        return {"enabled": True, "key_saved": True, "model": "synthetic"}


def load(module):
    path = PROJECT / "modules" / module / "server" / "__init__.py"
    name = "check_module_" + module
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=[str(path.parent)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return package


@contextmanager
def sandbox(module, handler=lambda request: httpx.Response(200, json={})):
    directory = PROJECT / ".codex" / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=module + "-", dir=directory) as temporary:
        root = Path(temporary)
        store = Store(root / "state.sqlite3", "module:" + module)

        async def api(module_id, path="/snapshot", **kwargs):
            return httpx.Response(404, json={"detail": "Module not installed"})

        context = SimpleNamespace(id=module, store=store, secrets=Memory(), data_dir=root, auth=Auth(handler), ai=AI(), api=api)
        try:
            yield context
        finally:
            store.close()
