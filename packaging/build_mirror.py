"""
PyInstaller 中文路径 bug 的绕法：
1. 把 backend/ + packaging/campus_framework.spec 镜像到 D:\\hackthon-build\\mirror\\src
   （英文纯 ASCII，venv 通过 PYTHONPATH 指回项目原位置）
2. 在镜像里运行 PyInstaller（spec 里 PROJECT_ROOT 被替换为镜像路径）
3. 产出 dist/CampusFramework/
4. 拷贝回项目根 dist/（可选）

这样 PyInstaller 完全不用看到任何非 ASCII 路径。

【B2 后】不再需要 patches/：backend/core/paths.py 本身已 frozen-aware。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
MIRROR = Path("D:\\hackthon-build\\mirror")
MIRROR_SRC = MIRROR / "src"          # ASCII 源码目录（PyInstaller cwd 用）
MIRROR_DIST = MIRROR / "dist"        # distpath
MIRROR_WORK = MIRROR / "build"       # workpath


def echo(msg: str, color: str = "") -> None:
    colors = {"red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
              "cyan": "\033[96m", "gray": "\033[90m", "reset": "\033[0m"}
    c = colors.get(color, "")
    reset = colors["reset"] if c else ""
    print(f"{c}{msg}{reset}", flush=True)


def mirror_sources(venv_python: Path) -> None:
    """把 backend/ + spec 复制到 ASCII 镜像。【B2 后】直接拷贝源码，无需补丁。"""
    echo(f"mirroring sources -> {MIRROR_SRC}", "cyan")
    if MIRROR_SRC.exists():
        shutil.rmtree(MIRROR_SRC)
    MIRROR_SRC.mkdir(parents=True)

    # backend 框架代码（B2 后：paths.py 本身 frozen-aware，无需补丁）
    shutil.copytree(PROJECT / "backend", MIRROR_SRC / "backend")
    echo(f"  + backend/", "gray")

    # spec 直接拷贝（B 版 spec 通过判断 SPECPATH/backend 是否存在自适应 mirror/dev 两种位置）
    spec_src = PROJECT / "packaging" / "campus_framework.spec"
    spec_dst = MIRROR_SRC / "campus_framework.spec"
    shutil.copy2(spec_src, spec_dst)
    echo(f"  + campus_framework.spec", "gray")

    # 运行时资源（模块/前端/脚本）也复制（PyInstaller collect_all 会扫描）
    # 但这些不嵌入 _internal，做完 freeze 后由最终 dist 拼装
    for dirname in ("modules", "web", "scripts", "bin"):
        src = PROJECT / dirname
        dst = MIRROR_SRC / dirname
        if src.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            echo(f"  + {dirname}/", "gray")

    # README/LICENSE
    for name in ("README.md", "LICENSE"):
        src = PROJECT / name
        if src.exists():
            shutil.copy2(src, MIRROR_SRC / name)

    # 不要复制 .private (venv 在那)，用 PYTHONPATH 找它
    echo(f"  done: {MIRROR_SRC}", "green")


def run_pyinstaller(venv_python: Path) -> int:
    """在 ASCII 镜像里跑 PyInstaller。"""
    echo(f"run PyInstaller in {MIRROR_SRC} ...", "cyan")
    if MIRROR_DIST.exists():
        shutil.rmtree(MIRROR_DIST)
    if MIRROR_WORK.exists():
        shutil.rmtree(MIRROR_WORK)
    MIRROR_DIST.mkdir(parents=True)
    MIRROR_WORK.mkdir(parents=True)

    env = os.environ.copy()
    # venv 的项目根还是原项目，所以 PyInstaller 能解析依赖
    # 关键是 cwd/spec/workpath/distpath 都是 ASCII
    env["VIRTUAL_ENV"] = str(venv_python.parent.parent)
    env["PYTHONPATH"] = str(PROJECT)  # 让 PyInstaller 找到项目 venv 与依赖

    cmd = [
        str(venv_python), "-m", "PyInstaller",
        "--noconfirm",
        "--distpath", str(MIRROR_DIST),
        "--workpath", str(MIRROR_WORK),
        str(MIRROR_SRC / "campus_framework.spec"),
    ]

    log = MIRROR_WORK / "pyinstaller.log"
    with open(log, "wb") as f:
        proc = subprocess.run(cmd, cwd=str(MIRROR_SRC), stdout=f, stderr=subprocess.STDOUT, env=env)

    if proc.returncode != 0:
        echo(f"✗ PyInstaller failed (exit {proc.returncode})", "red")
        with open(log, "r", encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines()[-30:]:
                echo(f"  {line}", "red")
        echo(f"log: {log}", "gray")
        return proc.returncode

    echo(f"✓ PyInstaller done", "green")
    return 0


def sync_dist(project_dist: Path) -> int:
    """
    把镜像的 dist/CampusFramework 拷贝回项目根 dist/，并补上 modules/。

    modules 是运行时动态加载的 Python 包（paths.MODULES 在 frozen 下 = exe 旁 modules/）。
    PyInstaller 不会把 modules 嵌入 _internal（它不是 datas/binaries），
    需要 post-freeze 由本函数补到 dist/CampusFramework/modules/。
    """
    src = MIRROR_DIST / "CampusFramework"
    if not src.exists() or not (src / "CampusFramework.exe").exists():
        echo(f"✗ {src} 不存在或不完整", "red")
        return 1

    echo(f"sync -> {project_dist}", "cyan")
    if project_dist.exists():
        shutil.rmtree(project_dist)
    shutil.copytree(src, project_dist)

    # 运行时 FILESYSTEM 资源：frozen 下 paths.PROJECT = exe 所在 dir，
    # modules/ 和 bin/ 都走 PROJECT 寻址（PROJECT/modules, PROJECT/bin/...），
    # 所以必须放在 exe 旁（不能进 _internal）。
    for name in ("modules", "bin"):
        src_dir = MIRROR_SRC / name
        dst_dir = project_dist / name
        if src_dir.exists():
            echo(f"  + {name}/ -> exe 旁", "gray")
            shutil.copytree(src_dir, dst_dir,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data"))

    total = sum(f.stat().st_size for f in project_dist.rglob("*") if f.is_file())
    echo(f"  size: {total // 1024 // 1024} MB", "green")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sync-back", action="store_true", help="只产出镜像 dist，不拷回项目")
    args = ap.parse_args()

    venv_python = PROJECT / ".private" / "runtime" / "windows" / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        echo(f"✗ venv python 不存在: {venv_python}", "red")
        return 1

    mirror_sources(venv_python)
    r = run_pyinstaller(venv_python)
    if r != 0:
        return r

    if not args.no_sync_back:
        return sync_dist(PROJECT / "dist" / "CampusFramework")
    else:
        echo(f"产物在: {MIRROR_DIST / 'CampusFramework'}", "cyan")
        return 0


if __name__ == "__main__":
    sys.exit(main())
