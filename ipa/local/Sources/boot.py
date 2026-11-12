"""iOS entry point: run the real campusMate backend on 127.0.0.1.

The desktop backend assumes Windows for credential storage and for the browser
and Node helpers. On iOS there is no subprocess, so this entry:

* points ``backend.core.paths.DATA`` at a writable sandbox directory
  (CAMPUS_DATA_DIR, set by the Swift launcher);
* replaces the DPAPI helper with a pass-through: the app sandbox is already
  protected at rest, and a Keychain-backed implementation is still on the
  roadmap;
* starts uvicorn on a loopback port chosen here and writes it to argv[1].

Everything is logged to ``<data>/boot.log`` before any third-party import, so
a startup failure is diagnosable from the device without a debugger.
"""

import os
import pathlib
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path(os.environ.get("CAMPUS_DATA_DIR") or (ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

LOG = open(DATA / "boot.log", "a", buffering=1, encoding="utf-8")
sys.stdout = LOG
sys.stderr = LOG
sys.path.insert(0, str(ROOT))


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def free_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def prepare():
    import backend.core.paths as paths

    paths.DATA = DATA
    (DATA / "runtime").mkdir(parents=True, exist_ok=True)

    import backend.core.vault as vault_module

    # No PowerShell/DPAPI on iOS: keep the values inside the app sandbox. The
    # files are covered by iOS data protection; Keychain is the follow-up.
    vault_module.protect = lambda text, action: text
    vault_module.windows_tool = lambda name: name


def main():
    port_file = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    log(f"boot: data={DATA} python={sys.version.split()[0]} executable={sys.executable}")

    prepare()
    log("boot: paths and vault patched")

    from backend.main import create_app

    port = free_port()
    app = create_app(active_port=port, data_dir=DATA)
    log(f"boot: app created on port {port}")
    if port_file:
        port_file.write_text(str(port), encoding="utf-8")

    import uvicorn

    log("boot: serving")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        log("boot failed:\n" + traceback.format_exc())
        raise
