"""Explicit Windows-only, current-user Weixin process reads; never injection.

Config.Cipher layout adapted from TANGandXUE/wcdb-key-tool (MIT).
Copyright (c) 2025 CloudDreamAI / TANGandXUE; see WCDB_LICENSE.txt.
No debugger, token privilege change, process write, remote thread or network API.
"""

import ctypes
import json
import os
import re
import struct
import subprocess
import threading
from collections.abc import Iterator
from ctypes import wintypes as wt
from pathlib import Path
from typing import Any

from .crypto import PAGE, NativeError, checkpoint, verifies
from .paths import local_folder

NAME = b"com.Tencent.WCDB.Config.Cipher"
MASK = bytes.fromhex("d2c7442458020000004889442450488b450048844c2448488944254048584c24")
LITERAL = re.compile(rb"[xX]'([0-9a-fA-F]{64,192})'")
MAX_ADDRESS = 0x800000000000


def available() -> bool:
    return os.name == "nt" and struct.calcsize("P") == 8


def account_root(value: str) -> Path:
    root = local_folder(value)
    if root.name != "db_storage" and (root / "db_storage").is_dir():
        child = local_folder(str(root / "db_storage"))
        if not child.is_relative_to(root):
            raise NativeError("wechat_live_account_invalid")
        root = child
    if root.name != "db_storage" or not (root / "message").is_dir():
        raise NativeError("wechat_live_account_invalid")
    return root


def source_files(root: Path) -> list[Path]:
    paths = sorted((root / "message").glob("message_*.db"))
    paths = [p for p in paths if re.fullmatch(r"message_\d+\.db", p.name)]
    if not paths or len(paths) > 100:
        raise NativeError("wechat_live_account_invalid")
    paths.insert(0, root / "contact/contact.db")
    for path in paths:
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise NativeError("wechat_live_account_invalid")
        wal = path.with_name(path.name + "-wal")
        if wal.exists() and not wal.resolve().is_relative_to(root):
            raise NativeError("wechat_live_account_invalid")
    return paths


def discover_folders() -> list[str]:
    if not available():
        return []
    roots = [Path.home() / "Documents", Path.home() / "Documents/WeChat Files"]
    config = Path(os.environ.get("APPDATA", "")) / "Tencent/xwechat/config"
    for item in sorted(config.glob("*.ini"))[:30]:
        with item.open("rb") as stream:
            raw = stream.read(4096)
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                text = raw.decode(encoding).strip().strip('"')
                candidate = Path(text)
                if candidate.is_absolute() and candidate.is_dir():
                    roots.append(candidate)
                    break
            except (UnicodeError, ValueError, OSError):
                continue
    found: list[str] = []
    for root in roots:
        base = root if root.name == "xwechat_files" else root / "xwechat_files"
        for path in base.glob("*/db_storage"):
            try:
                verified = account_root(str(path))
                if str(verified) not in found:
                    found.append(str(verified))
            except (RuntimeError, OSError):
                continue
    return found[:20]


def windows_api() -> tuple[Any, Any]:
    if not available():
        raise NativeError("wechat_live_windows_required")
    kernel: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi: Any = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.GetCurrentProcess.restype = wt.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wt.HANDLE,
        wt.DWORD,
        wt.LPWSTR,
        ctypes.POINTER(wt.DWORD),
    ]
    kernel.ReadProcessMemory.argtypes = [
        wt.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.VirtualQueryEx.argtypes = [
        wt.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    kernel.VirtualQueryEx.restype = ctypes.c_size_t
    advapi.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
    advapi.GetTokenInformation.argtypes = [
        wt.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wt.DWORD,
        ctypes.POINTER(wt.DWORD),
    ]
    advapi.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return kernel, advapi


def same_user(kernel: Any, advapi: Any, process: Any) -> bool:
    buffers = []
    for handle in (kernel.GetCurrentProcess(), process):
        token = wt.HANDLE()
        if not advapi.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):
            return False
        try:
            size = wt.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not 0 < size.value <= 65536:
                return False
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi.GetTokenInformation(
                token, 1, buffer, size, ctypes.byref(size)
            ):
                return False
            buffers.append(buffer)
        finally:
            kernel.CloseHandle(token)
    return bool(
        advapi.EqualSid(
            ctypes.c_void_p.from_buffer(buffers[0]),
            ctypes.c_void_p.from_buffer(buffers[1]),
        )
    )


def open_weixin(pid: int, *, memory: bool) -> tuple[Any, Any]:
    kernel, advapi = windows_api()
    # PROCESS_QUERY_LIMITED_INFORMATION, optionally QUERY_INFORMATION + VM_READ.
    access = 0x1000 | (0x0410 if memory else 0)
    handle = kernel.OpenProcess(access, False, pid)
    if not handle:
        raise NativeError("wechat_live_process_access_denied")
    name, size = ctypes.create_unicode_buffer(32768), wt.DWORD(32768)
    if (
        not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))
        or Path(name.value).name.lower() != "weixin.exe"
        or not same_user(kernel, advapi, handle)
    ):
        kernel.CloseHandle(handle)
        raise NativeError("wechat_live_process_invalid")
    return kernel, handle


def discover_processes() -> list[dict[str, Any]]:
    if not available():
        return []
    # Weixin.exe also hosts OCR, utility and player processes. Query metadata
    # only; a --type argument identifies a helper, regardless of its memory use.
    command = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);"
        "ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process "
        "-Filter \"Name = 'Weixin.exe'\" | "
        "Select-Object ProcessId,CommandLine,WorkingSetSize)"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        check=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    found = []
    for row in json.loads(result.stdout):
        command_line = row.get("CommandLine")
        if not command_line or re.search(r'(?:^|\s)"?--type(?=[=\s"]|$)', command_line, re.I):
            continue
        pid = int(row["ProcessId"])
        try:
            kernel, handle = open_weixin(pid, memory=False)
            kernel.CloseHandle(handle)
            found.append(
                {
                    "pid": pid,
                    "name": "微信主实例 · 本机当前用户",
                    "memory_kb": int(row.get("WorkingSetSize") or 0) // 1024,
                }
            )
        except NativeError:
            continue
    return sorted(found, key=lambda item: item["memory_kb"], reverse=True)


class Region(ctypes.Structure):
    _fields_ = [
        ("base", ctypes.c_void_p),
        ("allocation", ctypes.c_void_p),
        ("allocation_protect", wt.DWORD),
        ("partition", wt.WORD),
        ("size", ctypes.c_size_t),
        ("state", wt.DWORD),
        ("protect", wt.DWORD),
        ("kind", wt.DWORD),
    ]


def candidates(blob: bytes) -> Iterator[bytes]:
    """Decode bounded Config.Cipher key candidates; never log or persist candidates."""
    if not 0 < len(blob) <= 1024:
        return
    decoded = bytes(value ^ MASK[i % len(MASK)] for i, value in enumerate(blob))
    for match in LITERAL.finditer(decoded):
        value = match.group(1)
        starts = {0, max(0, len(value) - 64), *range(0, len(value) - 63, 32)}
        for start in starts:
            key = bytes.fromhex(value[start : start + 64].decode("ascii"))
            if len(key) == 32:
                yield key


def capture_keys(
    root: Path, pid: int, cancel: threading.Event, deadline: float
) -> dict[str, str]:
    """One explicit scan of one selected current-user process; no debug fallback."""
    pending: dict[str, bytes] = {}
    for path in source_files(root):
        with path.open("rb") as stream:
            page = stream.read(PAGE)
        if len(page) != PAGE or page.startswith(b"SQLite format"):
            raise NativeError("wechat_live_format_unsupported")
        pending[path.relative_to(root).as_posix()] = page
    keys: dict[str, str] = {}
    seen: set[bytes] = set()
    kernel, handle = open_weixin(pid, memory=True)
    try:

        def read(address: int, size: int) -> bytes:
            checkpoint(cancel, deadline)
            if not 0x10000 <= address < MAX_ADDRESS or not 0 < size <= 2 * 1024**2:
                return b""
            buffer = ctypes.create_string_buffer(size)
            count = ctypes.c_size_t()
            kernel.ReadProcessMemory(handle, address, buffer, size, ctypes.byref(count))
            return buffer.raw[: count.value]

        regions: list[tuple[int, int]] = []
        address = 0
        while address < MAX_ADDRESS:
            checkpoint(cancel, deadline)
            region = Region()
            if not kernel.VirtualQueryEx(
                handle, address, ctypes.byref(region), ctypes.sizeof(region)
            ):
                break
            base = int(region.base or 0)
            if (
                region.state == 0x1000
                and region.protect in {2, 4, 8, 0x20, 0x40, 0x80}
                and region.size > 0
            ):
                regions.append((base, region.size))
            address = base + region.size
            if address <= base:
                break

        def chunks() -> Iterator[tuple[int, bytes]]:
            for base, length in regions:
                tail = b""
                for offset in range(0, length, 2 * 1024**2):
                    part = read(base + offset, min(2 * 1024**2, length - offset))
                    if not part:
                        tail = b""
                        continue
                    yield base + offset - len(tail), tail + part
                    tail = part[-256:]

        def verify(key: bytes) -> None:
            checkpoint(cancel, deadline)
            if key in seen or len(key) != 32:
                return
            seen.add(key)
            for relative, page in list(pending.items()):
                if verifies(key, page):
                    keys[relative] = key.hex()
                    del pending[relative]

        needles = set()
        for base, data in chunks():
            position = data.find(NAME)
            while position >= 0:
                needles.add(base + position)
                position = data.find(NAME, position + 1)
            for match in LITERAL.finditer(data):
                verify(bytes.fromhex(match.group(1)[:64].decode("ascii")))
            if not pending:
                return keys
        if len(needles) > 256:
            raise NativeError("wechat_live_format_unsupported")
        patterns = [struct.pack("<QQ", pointer, len(NAME)) for pointer in needles]
        for base, data in chunks():
            for pattern in patterns:
                position = data.find(pattern)
                while position >= 0:
                    node = read(base + position - 16, 64)
                    if len(node) == 64:
                        pointer = struct.unpack_from("<Q", node, 40)[0]
                        obj = read(pointer + 136, 24)
                        if len(obj) == 24:
                            data_ptr, length = struct.unpack_from("<QQ", obj, 8)
                            if 0 < length <= 1024:
                                for key in candidates(read(data_ptr, length)):
                                    verify(key)
                    position = data.find(pattern, position + 1)
                    if not pending:
                        return keys
        # Partial key sets must never appear as a fully connected account.
        raise NativeError("wechat_live_keys_incomplete")
    finally:
        kernel.CloseHandle(handle)
