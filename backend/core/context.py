import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import Store


class ModuleSecrets:
    def __init__(self, vault, module_id):
        self._vault = vault
        self._key = "module:" + module_id
        self._lock = threading.RLock()

    def get(self, key: str) -> dict:
        with self._lock:
            return dict(self._vault.get(self._key).get(key, {}))

    def save(self, key: str, value: dict):
        with self._lock:
            values = self._vault.get(self._key)
            values[key] = value
            self._vault.save(self._key, values)

    def delete(self, key: str):
        with self._lock:
            values = self._vault.get(self._key)
            values.pop(key, None)
            self._vault.save(self._key, values)


@dataclass(frozen=True)
class ModuleContext:
    id: str
    store: Store
    secrets: ModuleSecrets
    data_dir: Path
    auth: Any
    ai: Any
