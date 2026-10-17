"""Run the same complete regression suite in Windows CI and local WSL."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.core.vault import windows_path, windows_tool


def run(command, label):
    print(f"\n>>> {label}", flush=True)
    subprocess.run(command, cwd=PROJECT, check=True)


def main():
    temporary = PROJECT / ".codex" / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    os.environ.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(temporary)
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError("Node.js 22+ is required to run frontend checks.")

    # Discovery makes new core/module checks part of the required gate automatically.
    python_checks = sorted((PROJECT / "checks").glob("check_*.py"))
    python_checks += sorted((PROJECT / "modules").glob("*/checks/check_*.py"))
    for path in python_checks:
        run([sys.executable, str(path)], path.relative_to(PROJECT))

    javascript_checks = ("check_frontend.mjs", "check_device_guide.mjs", "check_browser_network.mjs", "check_appearance.mjs", "check_campus_moments.mjs", "check_password_generator.mjs", "check_observatory_contrast.mjs")
    for name in javascript_checks:
        run([node, str(Path("checks") / name)], name)
    run([windows_tool("powershell"), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", windows_path(PROJECT / "checks" / "check_launcher.ps1")], "Windows launcher")

    sources = sorted(path for folder in ("web", "modules", "scripts", "checks")
                     for path in (PROJECT / folder).rglob("*") if path.suffix in {".js", ".mjs"})
    for path in sources:
        run([node, "--check", str(path.relative_to(PROJECT))], "JavaScript syntax: " + str(path.relative_to(PROJECT)))
    print(f"\nPASS: {len(python_checks)} Python checks, {len(javascript_checks)} JavaScript checks, Windows launcher and {len(sources)} JavaScript syntax checks", flush=True)


if __name__ == "__main__":
    main()
