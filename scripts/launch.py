"""Windows launcher: reuse an installed interpreter; never install dependencies."""
import argparse
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
from datetime import datetime
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tomllib
from urllib.request import ProxyHandler, build_opener
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / ".codex" / "launcher"
STATE = CONTROL / "server.json"
LOGS = ROOT / ".codex" / "logs"
HTTP = build_opener(ProxyHandler({}))


def identity(pid):
    """A PID alone can be reused: also compare its creation time and image."""
    if os.name != "nt":
        raise RuntimeError("此启动器用于 Windows；WSL 可继续使用 run.sh。")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        status = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value != 259:
            return None
        created, ended, system, user = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *map(ctypes.byref, (created, ended, system, user))):
            return None
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return None
        return {
            "created": (created.dwHighDateTime << 32) | created.dwLowDateTime,
            "image": os.path.normcase(image.value),
        }
    finally:
        kernel.CloseHandle(handle)


def read_state():
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("root") != str(ROOT) or not re.fullmatch(r"[a-f0-9]{32}", state.get("instance", "")):
            return None
        if not isinstance(state.get("pid"), int) or not isinstance(state.get("port"), int):
            return None
        return state
    except (OSError, ValueError, TypeError):
        return None


def owned(state):
    return bool(state and identity(state["pid"]) == state.get("identity"))


def save_state(state):
    temporary = STATE.with_suffix(".next")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(STATE)


@contextmanager
def launcher_lock():
    import msvcrt
    CONTROL.mkdir(parents=True, exist_ok=True)
    with (CONTROL / "start.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + 15
        while True:
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("另一个启动/停止操作正在执行，请稍后再试。")
                time.sleep(0.15)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)



def timezone_environment():
    """Windows may lack IANA data; reuse an existing Conda data directory."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, reset_tzpath
    try:
        ZoneInfo("Asia/Shanghai")
        return {}
    except ZoneInfoNotFoundError:
        pass
    homes = [
        Path(os.environ.get("CONDA_PREFIX") or "D:/anaconda"),
        Path.home() / "anaconda3",
        Path.home() / "miniconda3",
        Path("D:/anaconda"),
        Path("C:/ProgramData/anaconda3"),
    ]
    registry = Path.home() / ".conda" / "environments.txt"
    if registry.is_file():
        homes.extend(Path(line.strip()) for line in registry.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    for home in homes:
        directory = home / "Lib" / "site-packages" / "tzdata" / "zoneinfo"
        if (directory / "Asia" / "Shanghai").is_file():
            reset_tzpath([str(directory)])
            ZoneInfo("Asia/Shanghai")
            return {"PYTHONTZPATH": str(directory)}
    raise RuntimeError("当前环境缺少 IANA 时区数据，请自行补装 tzdata；启动器不会下载。")


def check_runtime():
    if sys.version_info < (3, 12):
        raise RuntimeError("需要已有的 Python 3.12 或以上版本。")
    missing = []
    requirements = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    for requirement in requirements:
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(>=|==)([^ ,;]+)", requirement)
        git = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*@\s*git\+(https://[^\s#]+)@([a-fA-F0-9]{40})", requirement)
        if not match and not git:
            raise RuntimeError("依赖声明已变化，请维护者更新启动检查：" + requirement)
        package = (match or git)[1]
        try:
            distribution = importlib.metadata.distribution(package)
        except importlib.metadata.PackageNotFoundError:
            missing.append(requirement)
            continue
        if git:
            # PEP 610 records the repository and exact commit used by pip/uv.
            try:
                origin = json.loads(distribution.read_text("direct_url.json") or "{}")
                vcs = origin.get("vcs_info", {})
                matches_source = (origin.get("url") == git[2] and vcs.get("vcs") == "git"
                                  and vcs.get("commit_id", "").lower() == git[3].lower())
            except (ValueError, TypeError, AttributeError):
                matches_source = False
            if not matches_source:
                missing.append(requirement)
            continue
        _, operator, expected = match.groups()
        installed = distribution.version
        version = lambda text: tuple(int(part) for part in re.match(r"\d+(?:\.\d+)*", text)[0].split("."))
        if operator == "==" and installed != expected or operator == ">=" and version(installed) < version(expected):
            missing.append(requirement)
    if missing:
        raise RuntimeError(
            "当前环境缺少依赖或版本不符：\n  " + "\n  ".join(missing) +
            "\n请在选定环境补齐后重试。启动器不会自动安装。\n当前 Python：" + sys.executable
        )
    for name in ("fastapi", "uvicorn", "deepseek_harness", "deepseek_harness_runtime",
                 "filelock", "requests", "shanghaitech_ids_passkey"):
        if importlib.util.find_spec(name) is None:
            raise RuntimeError("当前环境无法找到模块 " + name + "，请检查已有环境。")


def saved_port():
    database = ROOT / ".private" / "settings.sqlite3"
    if not database.exists():
        return 16666
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT value FROM state WHERE namespace='core' AND key='settings'").fetchone()
    return int(json.loads(row[0])["port"]) if row else 16666


def ready(port):
    try:
        with HTTP.open(f"http://127.0.0.1:{port}/api/v1/bootstrap", timeout=1) as response:
            value = json.loads(response.read(1024 * 1024))
            return isinstance(value.get("modules"), list) and bool(value.get("csrf_token")) and "categories" in value
    except (OSError, ValueError):
        return False


def port_busy(port):
    with socket.socket() as client:
        client.settimeout(0.5)
        return client.connect_ex(("127.0.0.1", port)) == 0


def show_browser(port, no_browser):
    url = f"http://127.0.0.1:{port}/"
    print("网页已就绪：" + url, flush=True)
    if not no_browser:
        try:
            if not webbrowser.open(url, new=2):
                print("浏览器未自动打开，请手动打开上面的地址。", flush=True)
        except OSError:
            print("请在浏览器中打开上面的地址。", flush=True)
    print("关闭网页不会停止后台；双击 stop.cmd 可以停止。", flush=True)


def start(port, no_browser):
    with launcher_lock():
        state = read_state()
        if owned(state):
            if port is not None and port != state["port"]:
                raise RuntimeError(f"本目录已在端口 {state['port']} 运行；请先 stop.cmd 再改端口。")
            if not ready(state["port"]):
                raise RuntimeError("本目录后台仍在运行但尚未就绪，请查看日志：" + state.get("log", ""))
            show_browser(state["port"], no_browser)
            return
        check_runtime()
        timezone = timezone_environment()
        port = saved_port() if port is None else port
        if not 1024 <= port <= 65535:
            raise RuntimeError("端口应在 1024 到 65535 之间。")
        if port_busy(port):
            raise RuntimeError(
                f"端口 {port} 已被其他程序占用，本次没有打开或停止它。\n"
                "可使用 run.cmd --port 17666 选择其他端口。"
            )
        LOGS.mkdir(parents=True, exist_ok=True)
        temporary = ROOT / ".codex" / "tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        instance = uuid.uuid4().hex
        log = LOGS / ("server-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + instance[:6] + ".log")
        env = {
            **os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".codex" / "pycache"),
            "TEMP": str(temporary), "TMP": str(temporary), "TMPDIR": str(temporary),
        }
        env.update(timezone)
        print("正在启动校园工作台，使用：" + sys.executable, flush=True)
        with log.open("wb") as output:
            process = subprocess.Popen(
                [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()),
                 "--serve", "--port", str(port), "--instance", instance],
                cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        state = {
            "root": str(ROOT), "pid": process.pid, "identity": identity(process.pid),
            "instance": instance, "port": port, "log": str(log),
        }
        if not state["identity"]:
            raise RuntimeError("后台启动后立即退出，请查看日志：" + str(log))
        save_state(state)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                if read_state() == state:
                    STATE.unlink(missing_ok=True)
                detail = log.read_text(encoding="utf-8", errors="replace")[-5000:]
                raise RuntimeError("后台启动失败，日志：" + str(log) + "\n" + detail)
            if ready(port):
                show_browser(port, no_browser)
                print("日志：" + str(log), flush=True)
                return
            time.sleep(0.3)
        stop_file = CONTROL / ("stop-" + instance)
        stop_file.touch()
        raise RuntimeError("等待网页启动超时，已请求停止本次后台。日志：" + str(log))


def stop():
    with launcher_lock():
        state = read_state()
        if not owned(state):
            print("本目录没有可确认的后台进程，无需停止。", flush=True)
            return
        (CONTROL / ("stop-" + state["instance"])).touch()
        print("正在停止本目录的校园工作台…", flush=True)
        deadline = time.monotonic() + 20
        while owned(state):
            if time.monotonic() >= deadline:
                raise RuntimeError("后台仍在结束当前任务，请稍后重试；没有强制终止其他进程。")
            time.sleep(0.2)
        print("后台已停止。", flush=True)


def serve(port, instance):
    if not re.fullmatch(r"[a-f0-9]{32}", instance or ""):
        raise RuntimeError("启动实例标识无效。")
    sys.path.insert(0, str(ROOT))
    import uvicorn
    from backend.main import create_app
    server = uvicorn.Server(uvicorn.Config(create_app(active_port=port), host="127.0.0.1", port=port, access_log=False))
    stop_file = CONTROL / ("stop-" + instance)
    finished = threading.Event()

    def watch():
        while not finished.wait(0.2):
            if stop_file.exists():
                server.should_exit = True
                return

    monitor = threading.Thread(target=watch, name="campus-launcher-stop", daemon=True)
    monitor.start()
    try:
        server.run()
    finally:
        finished.set()
        monitor.join()
        stop_file.unlink(missing_ok=True)
        state = read_state()
        if state and state["instance"] == instance:
            STATE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="校园工作台 Windows 启动器；不下载环境或依赖。")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--instance", help=argparse.SUPPRESS)
    options = parser.parse_args()
    try:
        if options.serve:
            serve(options.port, options.instance)
        elif options.check:
            check_runtime()
            timezone_environment()
            print("环境检查通过：" + sys.executable)
        elif options.stop:
            stop()
        else:
            start(options.port, options.no_browser)
        return 0
    except (RuntimeError, OSError, ValueError, sqlite3.Error) as error:
        print("无法完成操作：" + str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

