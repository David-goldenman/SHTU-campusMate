# PyInstaller spec — Campus Framework onedir (B 版：源码本身 frozen-aware，无需补丁)
#
# B2 后：
#   - backend/core/paths.py 已 frozen-aware（is_frozen()/ensure_dirs()，路径分三类管理）
#   - 无补丁层：直接拿源码 backend/ 跑 Analysis
#   - PyInstaller 中文路径 silent fail 由 build_mirror.py（D 盘 ASCII 镜像）绕开

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# backend 下非 py 资源（catalog.json、package.json 等），frozen 时 catalog.py 用 __file__ 找同 dir
_backend_data = collect_data_files('backend', includes=['**/*.json', '**/*.yaml', '**/*.yml', '**/*.toml', '**/*.txt', '**/*.md', '**/*.sql'])

# mirror 模式下，spec 放在 mirror/src/ 下，SPECPATH = src/，等于 PROJECT_ROOT
# dev 模式下，spec 放在 packaging/ 下，SPECPATH/.. = PROJECT_ROOT
# 用相对位置自适应两种位置：
if os.path.exists(os.path.join(SPECPATH, 'backend')):
    # mirror 模式：SPECPATH 就是 PROJECT_ROOT
    PROJECT_ROOT = os.path.abspath(SPECPATH)
else:
    # dev 模式：SPECPATH 是 packaging/，PROJECT_ROOT 是上一级
    PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

block_cipher = None

# ── collect_all ──
# shanghaitech_ids_passkey 是 git 直装，含内嵌 exe/dll；deepseek_harness 同。
# uvicorn 包含 multiprocess 子进程模块，collect_submodules 必须。
datas  = []
binaries = []
for pkg in (
    'shanghaitech_ids_passkey',      # webauthn passkey SDK（git 直装）
    'shanghaitech_compute_auth',     # compute auth SDK（git 直装）
    'deepseek_harness',              # DeepSeek Harness python SDK
    'deepseek_harness_runtime',      # DeepSeek Harness 预编译 .exe runtime（win-x64）
):
    try:
        d, b, h = collect_all(pkg)
        datas    += d
        binaries += b
    except Exception:
        pass  # 若包未装，不阻塞；确保 PyInstaller 至少把 backend 自身打包

hidden_imports = (
    collect_submodules('uvicorn')
    + collect_submodules('fastapi')
    + collect_submodules('pydantic')
    + collect_submodules('backend')
    + [
        'filelock',
        'httpx', 'httpx._transports', 'httpx._transports.default',
        'passlib', 'passlib.handlers', 'passlib.handlers.pbkdf2',
        'sqlite3', '_sqlite3',
        'asyncio', 'asyncio.windows_events', 'asyncio.windows_utils',
    ]
)
# 注：modules/ 不作为 hidden imports，也不嵌入 _internal。
# modules 是运行时通过 paths.MODULES 在文件系统动态加载的（设计如此，方便用户自定义模块），
# 部署时由 build_mirror.sync_dist() 拷贝到 exe 旁。

# 静态资源（走 sys._MEIPASS，frozen 下 paths.WEB / paths.SCRIPTS 会指向这里）
datas += [
    (os.path.join(PROJECT_ROOT, 'web'),      'web'),
    (os.path.join(PROJECT_ROOT, 'scripts'),  'scripts'),
]
datas += _backend_data

# bootstrap 包装：让 backend/main.py 以 package 模式启动（保证 from .core.xxx 可用）
_bootstrap_path = os.path.join(SPECPATH, '_bootstrap_entry.py')
with open(_bootstrap_path, 'w', encoding='utf-8') as _f:
    _f.write(
        "import sys, os\n"
        "# PyInstaller bootloader 把 _bootstrap_entry.py 直接当顶层 script 跑；\n"
        "# backend 是真 package，要走 python -m backend.main 才能触发 relative import。\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "from backend.main import main\n"
        "main()\n"
    )

a = Analysis(
    [_bootstrap_path],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CampusFramework',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed：无控制台黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CampusFramework',
)
