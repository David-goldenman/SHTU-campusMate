import json
import shutil
import subprocess
import time

from ...core.paths import PROJECT, RUNTIME
from ...core.vault import windows_path, windows_tool
from .protocols import PROVIDERS


class VerificationBrowser:
    def __init__(self, directory=RUNTIME / 'auth'):
        self.launchers = {}
        self.directory = directory

    def _directory(self, provider):
        if provider not in PROVIDERS:
            raise ValueError("认证提供方不存在。")
        return self.directory / provider

    def _command(self):
        return [windows_tool("node"), windows_path(PROJECT / "scripts" / "browser.mjs")]

    def _run(self, action, provider, **options):
        payload = {"action": action, "profile": windows_path(self._directory(provider)), **options}
        result = subprocess.run(self._command(), input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True, timeout=40)
        if result.returncode:
            raise RuntimeError("验证窗口尚未启动或已经关闭，请重新打开。")
        return json.loads(result.stdout)

    def open(self, provider, url, *, device_setup=False):
        process = self.launchers.get(provider)
        if device_setup and process is not None:
            # Enrollment keeps its CDP document guide attached through school redirects.
            self.close(provider)
            process = None
        if process is not None and process.poll() is None:
            return self._run("open", provider, url=url, device_setup=device_setup)
        self.close(provider)
        process = subprocess.Popen(self._command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.launchers[provider] = process
        process.stdin.write(json.dumps({"action": "open", "profile": windows_path(self._directory(provider)), "url": url, "keep_alive": True, "device_setup": device_setup}))
        process.stdin.close()
        line = process.stdout.readline()
        if not line:
            process.wait(timeout=5)
            raise RuntimeError("验证窗口未能启动，请检查 Windows Node 与 Edge。")
        return json.loads(line)

    def state(self, provider):
        return self._run("state", provider)

    def close(self, provider):
        directory = self._directory(provider)
        if directory.exists():
            try:
                self._run("close", provider)
            except RuntimeError:
                pass  # A manually closed window has no debugging endpoint.
        process = self.launchers.pop(provider, None)
        if process is not None:
            process.wait(timeout=8)
            if process.stdout:
                process.stdout.close()
        if directory.exists():
            for attempt in range(20):
                try:
                    shutil.rmtree(directory)
                    break
                except OSError:
                    if attempt == 19:
                        raise RuntimeError("验证窗口已关闭，但临时登录目录仍被占用，请关闭验证窗口后重试。") from None
                    time.sleep(0.1)

    def close_all(self):
        for provider in PROVIDERS:
            self.close(provider)
