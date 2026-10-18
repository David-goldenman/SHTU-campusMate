"""Desktop backend starts with isolated data and stops when its host closes stdin."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
temporary = PROJECT / ".codex" / "tmp"
temporary.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="desktop-", dir=temporary) as name:
    root = Path(name)
    data = root / ".private"
    node = shutil.which("node") or shutil.which("node.exe")
    subprocess.run([node, "-e", """
const assert = require('node:assert/strict');
const path = require('node:path');
const {dataPaths, backendEnvironment} = require('./packaging/electron/portable.cjs');
const root = process.argv[1];
const paths = dataPaths(root);
for (const value of Object.values(paths)) {
  const relative = path.relative(root, value);
  assert(!relative.startsWith('..') && !path.isAbsolute(relative));
}
assert.throws(() => dataPaths(root, path.dirname(root)));
const env = backendEnvironment(root, path.join(root, 'runtime'), {SystemRoot:'C:\\\\Windows', APPDATA:'original-user-profile'});
assert.equal(env.APPDATA, 'original-user-profile');
assert.equal(env.CAMPUS_DATA_DIR, paths.data);
assert.equal(env.pnpm_config_offline, 'true');
assert.equal(env.PYTHONPATH, '');
assert(!path.relative(root, env.PNPM_HOME).startsWith('..'));
""", str(root)], cwd=PROJECT, check=True)

    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    env = {**os.environ, "CAMPUS_DATA_DIR": str(data), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    env.update({key: str(root) for key in ("TEMP", "TMP", "TMPDIR")})
    # Preparation commands must not wait on the desktop host's open control pipe.
    probe = (
        "import os,sys; from pathlib import Path; "
        "from backend.services.ai.harness import prepare; "
        "prepare([sys.executable, '-c', 'import sys; assert not sys.stdin.read()'], "
        "cwd=Path.cwd(), env=dict(os.environ), timeout=3, check_cancelled=lambda:None)"
    )
    host = subprocess.Popen([sys.executable, "-B", "-c", probe], cwd=PROJECT, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert host.wait(timeout=10) == 0, host.stderr.read().decode("utf-8")
    finally:
        host.stdin.close()
        if host.poll() is None:
            host.terminate()
            host.wait(timeout=5)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with (root / "backend.log").open("wb") as log:
        process = subprocess.Popen([sys.executable, "-B", "-u", str(PROJECT / "packaging/electron/server.py"),
            "--port", str(port), "--launch-id", "desktop-check"],
            cwd=PROJECT, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError((root / "backend.log").read_text(encoding="utf-8"))
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("Desktop backend did not start")
            assert health["launch_id"] == "desktop-check"
            with opener.open(f"http://127.0.0.1:{port}/api/v1/bootstrap", timeout=5) as response:
                bootstrap = json.load(response)
            assert {"courses", "timetable", "academic-assistant"}.issubset({m["id"] for m in bootstrap["modules"]})
            assert (data / "settings.sqlite3").is_file()
            process.stdin.close()
            assert process.wait(timeout=20) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
print("Desktop paths, independent startup, module bootstrap and graceful shutdown passed")

