import json
import os
import shutil
import subprocess
import threading
from copy import deepcopy
from pathlib import Path

from .paths import DATA, PROJECT


def windows_path(path: Path) -> str:
    if os.name == "nt":
        return str(path)
    return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()


def windows_tool(name: str) -> str:
    executable = shutil.which(name if os.name == "nt" else name + ".exe")
    if not executable:
        raise RuntimeError(f"需要 Windows {name}，请使用 Windows 或启用了 Windows 互操作的 WSL。")
    return executable


def protect(text: str, action: str) -> str:
    result = subprocess.run(
        [windows_tool("powershell"), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", windows_path(PROJECT / "scripts" / "dpapi.ps1"), action],
        input=text, text=True, encoding="utf-8", capture_output=True, timeout=20,
    )
    if result.returncode:
        raise RuntimeError("Windows 用户密钥无法处理此凭据，请在原 Windows 账号下运行或重新配置。")
    return result.stdout.strip("\ufeff\r\n")


class Vault:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else DATA / "vault.dpapi"
        self.lock = threading.RLock()
        self._values = json.loads(protect(self.path.read_text(encoding="ascii"), "unprotect")) if self.path.exists() else {}

    def get(self, key: str) -> dict:
        with self.lock:
            return deepcopy(self._values.get(key, {}))

    def save(self, key: str, value: dict):
        with self.lock:
            self._write({**self._values, key: deepcopy(value)})

    def delete(self, key: str):
        with self.lock:
            if key in self._values:
                self._write({k: value for k, value in self._values.items() if k != key})

    def delete_prefix(self, prefix: str):
        with self.lock:
            values = {k: value for k, value in self._values.items() if not k.startswith(prefix)}
            if len(values) != len(self._values):
                self._write(values)

    def clear(self):
        with self.lock:
            if self._values:
                self._write({})

    def _write(self, values: dict):
        encrypted = protect(json.dumps(values, ensure_ascii=False), "protect")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".next")
        temporary.write_text(encrypted, encoding="ascii")
        temporary.replace(self.path)
        self._values = values
