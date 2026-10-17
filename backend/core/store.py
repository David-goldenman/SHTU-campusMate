import json
import sqlite3
import threading
from pathlib import Path

from .paths import DATA


class Store:
    """Non-secret JSON values, separated by owner namespace."""

    def __init__(self, path: Path | None = None, namespace: str = "core"):
        self.path = path or DATA / "settings.sqlite3"
        self.namespace = namespace
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (namespace TEXT, key TEXT, value TEXT NOT NULL, PRIMARY KEY(namespace, key))")

    def read(self, key: str, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM state WHERE namespace=? AND key=?", (self.namespace, key)).fetchone()
        return json.loads(row[0]) if row else default

    def write(self, key: str, value):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?, ?)", (self.namespace, key, json.dumps(value, ensure_ascii=False)))

    def delete(self, key: str):
        with self.lock, self.db:
            self.db.execute("DELETE FROM state WHERE namespace=? AND key=?", (self.namespace, key))

    def clear(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM state WHERE namespace=?", (self.namespace,))

    def clear_modules(self):
        with self.lock, self.db:
            self.db.execute("DELETE FROM state WHERE namespace LIKE 'module:%'")
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def for_module(self, module_id: str):
        return Store(self.path, "module:" + module_id)

    def export_modules(self):
        with self.lock:
            return self.db.execute("SELECT namespace, key, value FROM state WHERE namespace LIKE 'module:%' ORDER BY namespace, key").fetchall()

    def restore_modules(self, rows):
        with self.lock, self.db:
            self.db.execute("DELETE FROM state WHERE namespace LIKE 'module:%'")
            self.db.executemany('INSERT INTO state VALUES (?, ?, ?)', rows)

    def close(self):
        with self.lock:
            self.db.close()
