"""Cancel preparation process trees and enforce a total AI task deadline offline."""
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import HTTPException
from backend.services.ai.harness import Harness, prepare


def alive(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        stat = Path(f'/proc/{pid}/stat')
        return not stat.exists() or stat.read_text().split()[2] != 'Z'
    except ProcessLookupError:
        return False


def check(root):
    cancelled = threading.Event()
    errors = []
    def check_cancelled():
        if cancelled.is_set():
            raise HTTPException(409, 'synthetic cancellation')

    pid_file = root / 'pids.txt'
    code = "import os,subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],creationflags=0x08000000 if os.name=='nt' else 0);Path(sys.argv[1]).write_text(str(os.getpid())+' '+str(p.pid));time.sleep(30)"
    def run():
        try:
            prepare([sys.executable, '-c', code, str(pid_file)], cwd=root, env=dict(os.environ), timeout=20, check_cancelled=check_cancelled)
        except HTTPException as error:
            errors.append(error.status_code)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        for _ in range(300):
            if pid_file.exists():
                break
            time.sleep(.01)
        assert pid_file.exists(), 'Preparation and its child must start'
    finally:
        cancelled.set();worker.join(8)
    assert not worker.is_alive() and errors == [409]
    assert all(not alive(int(pid)) for pid in pid_file.read_text().split()), 'Stop must reap the preparation process tree'
    try:
        prepare([sys.executable, '-c', 'import time;time.sleep(30)'], cwd=root, env=dict(os.environ), timeout=.05, check_cancelled=lambda:None)
        raise AssertionError('A stalled preparation must time out')
    except subprocess.TimeoutExpired:
        pass

    released = []
    @contextmanager
    def use_plugins(ids):
        try:
            yield [SimpleNamespace(info={'id':'synthetic'}, harness={'name':'synthetic','folder':root,'bundle':False})]
        finally:
            released.append(True)

    closed = threading.Event()
    class Runtime:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def close(self): closed.set()
        def run(self, *args, **kwargs):
            assert closed.wait(2), 'The total deadline must stop the runtime without a user event'
            raise TimeoutError()

    harness = Harness(SimpleNamespace(data=root, use_plugins=use_plugins))
    harness.run_timeout = .05
    with patch('backend.services.ai.harness.prepare'), patch('backend.services.ai.harness.resolve_bundled_launch_args', return_value=[sys.executable]), patch('backend.services.ai.harness.DeepSeekHarness', Runtime):
        try:
            harness.run('synthetic', None, ['synthetic'], 'synthetic', 'synthetic')
            raise AssertionError('An expired task must not report success')
        except HTTPException as error:
            assert error.status_code == 504
    assert released == [True] and closed.is_set()
    assert not list((root / 'runtime' / 'tmp').iterdir())


temporary = ROOT / '.codex' / 'tmp'
temporary.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='harness-cancel-', dir=temporary) as folder:
    check(Path(folder))
print('harness cancellation: preparation tree reaped, stage timeout, total task deadline and resource release passed')
