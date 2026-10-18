"""Exercise the Windows launcher without accounts, downloads or the user's data."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.config import Settings
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def free_port():
    for _ in range(32):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        try:
            return Settings(port=port).port
        except ValueError:
            continue
    raise RuntimeError("No browser-compatible test port is available.")


def check(project):
    def command(*arguments, good=True):
        result = subprocess.run(
            [PS, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(project / "run-local.ps1"), "--python", sys.executable, *map(str, arguments)],
            cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=65,
        )
        if good:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout
        return result.stdout + result.stderr

    state_file = project / ".private" / "runtime" / "launcher" / "server.json"
    command("--check")
    port = free_port()
    try:
        command("-Port", port, "-NoBrowser")
        first = json.loads(state_file.read_text(encoding="utf-8"))
        assert first["root"] == str(project) and first["port"] == port
        assert not (project / ".codex").exists(), "Application runtime belongs in .private/runtime"
        cache = project / ".private" / "runtime" / "cache" / "python"
        assert any(cache.rglob("main.cpython-*.pyc")), "Startup imports must populate the runtime bytecode cache"
        assert all(not any((project / folder).rglob("__pycache__")) for folder in ("backend", "modules", "scripts")), "Bytecode must stay in the private runtime"
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with http.open(f"http://127.0.0.1:{port}/api/v1/bootstrap", timeout=3) as response:
            value = json.loads(response.read())
        expected = {path.parent.name for path in (project / "modules").glob("*/module.json")}
        assert {item["id"] for item in value["modules"]} == expected
        for route in ("/api/v1/modules/courses/snapshot", "/api/v1/modules/dashboard/snapshot"):
            with http.open(f"http://127.0.0.1:{port}" + route, timeout=3) as response:
                snapshot = json.loads(response.read())
                assert response.status == 200 and "data" in snapshot
        assert all(item["status"] == "ready" for item in value["modules"]), [
            (item["id"], item["status"], item.get("error")) for item in value["modules"]
        ]
        with http.open(f"http://127.0.0.1:{port}/", timeout=3) as response:
            assert "校园工作台" in response.read().decode("utf-8")
        with http.open(f"http://127.0.0.1:{port}/assets/app.js", timeout=3) as response:
            assert b"bootstrap" in response.read()
        command("--no-browser")
        again = json.loads(state_file.read_text(encoding="utf-8"))
        assert first["pid"] == again["pid"] and first["instance"] == again["instance"]
        with http.open(f"http://127.0.0.1:{port}/api/v1/health", timeout=3) as response:
            assert json.loads(response.read())["launch_id"] == first["instance"]
        foreground = {"launch_id": first["instance"], "port": port, "pid": first["pid"]}
        try:
            state_file.write_text(json.dumps(foreground), encoding="utf-8")
            command("--no-browser")
            assert "无需停止" in command("--stop")
            assert json.loads(state_file.read_text(encoding="utf-8")) == foreground
        finally:
            state_file.write_text(json.dumps(first), encoding="utf-8")
        assert command("--port", free_port(), "--no-browser", good=False)
    finally:
        command("--stop")
    assert not state_file.exists()
    command("--stop")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        busy = listener.getsockname()[1]
        result = command("--port", busy, "--no-browser", good=False)
        assert "已被其他程序占用" in result, result
        assert listener.getsockname()[1] == busy and not state_file.exists()

    # A forged/stale PID record must never stop a process with another creation time.
    state_file.write_text(json.dumps({
        "root": str(project), "pid": os.getpid(), "port": port,
        "instance": "a" * 32, "identity": {"created": 0, "image": "wrong"},
    }), encoding="utf-8")
    assert "无需停止" in command("--stop")
    print("PASS: existing runtime, paths with spaces, ready page/assets, Shanghai time zone, course/dashboard data, installed modules, reuse, graceful stop, busy port and stale PID protection")


if __name__ == "__main__":
    if os.name != "nt":
        print("SKIP: optional Windows launcher is exercised by native Windows CI")
        raise SystemExit(0)
    temporary = ROOT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="launcher-check-", dir=temporary) as directory:
        project = Path(directory) / "校园 work space"
        assert project.resolve().is_relative_to(temporary.resolve())
        project.mkdir()
        for folder in ("backend", "modules", "web", "scripts"):
            shutil.copytree(ROOT / folder, project / folder, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("run-local.ps1", "run.cmd", "stop.cmd", "pyproject.toml"):
            shutil.copyfile(ROOT / name, project / name)
        check(project)
