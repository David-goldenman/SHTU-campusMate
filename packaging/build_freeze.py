"""
内部调 PyInstaller 并手动拷贝 dist。

为什么不用 PowerShell `Start-Process -Wait` + `shutil.move` 调 PyInstaller COLLECT？
  1. PowerShell 5.1 对包含中文的路径 native command 会 NativeCommandError
  2. PyInstaller 6 在含中文的项目根下 COLLECT `shutil.move` silent fail
     （EXE 生成到 build/ 完事，没被复制到 dist/）

这个脚本兼容任何路径（中文也行），PowerShell 只调本脚本即可。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def echo(msg: str, color: str = "") -> None:
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "cyan": "\033[96m", "gray": "\033[90m", "reset": "\033[0m",
    }
    c = colors.get(color, "")
    reset = colors["reset"] if c else ""
    print(f"{c}{msg}{reset}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(PROJECT / "packaging" / "campus_framework.spec"))
    ap.add_argument("--dist", default=str(PROJECT / "dist"))
    ap.add_argument("--work", default=str(PROJECT / "build"))
    ap.add_argument("--name", default="campus_framework")
    args = ap.parse_args()

    spec = Path(args.spec).resolve()
    dist_root = Path(args.dist).resolve()
    work_root = Path(args.work).resolve()
    dist_app_dir = dist_root / "CampusFramework"
    build_internal = work_root / args.name  # build/campus_framework/

    echo(f"  spec:      {spec}", "gray")
    echo(f"  dist:      {dist_root}", "gray")
    echo(f"  work:      {work_root}", "gray")

    if not spec.exists():
        echo(f"  ✗ spec 不存在: {spec}", "red")
        return 1

    # ── 清旧产物 ──
    # 不要清 dist（PyInstaller COLLECT 自己会写），但要清 build
    if work_root.exists():
        echo(f"  clear {work_root}", "gray")
        shutil.rmtree(work_root)
    # dist 只清 onedir 目录，不要清 dist-installer（如果存在）
    if dist_app_dir.exists():
        echo(f"  clear {dist_app_dir}", "gray")
        shutil.rmtree(dist_app_dir)
    dist_app_dir.mkdir(parents=True, exist_ok=True)

    # ── 跑 PyInstaller ──
    echo("  run PyInstaller ...", "cyan")
    log_dir = work_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "pyinstaller.stdout.log"
    err_log = log_dir / "pyinstaller.stderr.log"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(dist_root),
        "--workpath", str(work_root),
        str(spec),
    ]

    with open(out_log, "wb") as fout, open(err_log, "wb") as ferr:
        proc = subprocess.run(cmd, stdout=fout, stderr=ferr, cwd=str(PROJECT))

    if proc.returncode != 0:
        echo(f"  ✗ PyInstaller 失败 (exit {proc.returncode})", "red")
        echo(f"--- 最后 30 行 stderr ---", "red")
        try:
            with open(err_log, "r", encoding="utf-8", errors="replace") as f:
                for line in f.read().splitlines()[-30:]:
                    echo(f"  {line}", "red")
        except Exception:
            pass
        echo(f"完整日志: {log_dir}", "gray")
        return proc.returncode

    echo(f"  PyInstaller exit 0 (log: {log_dir})", "green")
    echo("--- PyInstaller tail ---", "gray")
    try:
        with open(out_log, "r", encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines()[-10:]:
                echo(f"  {line}", "gray")
    except Exception:
        pass

    # ── 检测 COLLECT 是否真的把产物放进了 dist ──
    # PyInstaller 6 在中文 distpath 下 COLLECT silent fail（completed 但 dist 空）
    # 所以**不**信 COLLECT，总是从 build/<name>/ 手动同步到 dist/CampusFramework/
    exe_in_build = build_internal / "CampusFramework.exe"
    exe_in_dist = dist_app_dir / "CampusFramework.exe"

    def dist_populated() -> bool:
        return (
            exe_in_dist.exists()
            and (dist_app_dir / "_internal").is_dir()
            and sum(1 for _ in (dist_app_dir / "_internal").rglob("*")) > 50
        )

    if not build_internal.exists():
        echo(f"  ✗ build/{args.name}/ 不存在，PyInstaller 没产出 build 目录", "red")
        return 1
    if not exe_in_build.exists():
        echo(f"  ✗ build/{args.name}/CampusFramework.exe 不存在", "red")
        return 1

    # 总是手动同步：以 build/<name>/ 为 truth，重建 dist/CampusFramework/
    echo(f"  sync {build_internal} -> {dist_app_dir}", "cyan")
    if dist_app_dir.exists():
        shutil.rmtree(dist_app_dir)
    dist_app_dir.mkdir(parents=True, exist_ok=True)

    # build/<name>/ 是 PyInstaller 运行时产物目录
    # 我们只挑最终需要的：CampusFramework.exe + 所有顶层二进制/资源/_internal
    skip_names = {
        "Analysis-00.toc", "PKG-00.toc", "PYZ-00.toc",
        "COLLECT-00.toc", "EXE-00.toc",
        "warn-campus_framework.txt",
        "xref-campus_framework.html",
        "localpycs",  # bytecode cache 目录
        "logs",
    }
    for entry in build_internal.iterdir():
        if entry.name in skip_names:
            continue
        dst = dist_app_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dst)
        else:
            shutil.copy2(entry, dst)

    if dist_populated():
        echo(f"  ✓ sync 完成: {dist_app_dir}", "green")
    else:
        echo(f"  ✗ sync 后 dist 仍不完整", "red")
        return 1

    # ── 报告 ──
    total = 0
    for entry in dist_app_dir.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    total_mb = round(total / 1024 / 1024, 1)
    echo(f"  最终 dist 大小: {total_mb} MB ({dist_app_dir})", "green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
