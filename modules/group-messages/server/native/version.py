"""Read Windows executable version resources without reading process memory."""

import ctypes
import re
import subprocess
from ctypes import wintypes as wt
from dataclasses import dataclass
from pathlib import Path

from .crypto import NativeError
from .process import available, discover_processes, open_weixin

# This is evidence of first enrollment on one machine, not a version allowlist.
TESTED_ENROLLMENT_VERSIONS = ("4.1.15.13",)


@dataclass(frozen=True)
class ClientVersion:
    executable: str
    version: str


def file_version(path: Path) -> str:
    """Read VS_FIXEDFILEINFO from a local executable's Windows resource."""
    if not available():
        raise NativeError("wechat_live_windows_required")
    if not path.is_absolute() or str(path).startswith("\\\\") or not path.is_file():
        raise NativeError("wechat_live_version_unavailable")
    lib = ctypes.WinDLL("version", use_last_error=True)
    lib.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.DWORD)]
    lib.GetFileVersionInfoSizeW.restype = wt.DWORD
    lib.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    lib.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wt.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wt.UINT),
    ]
    size = lib.GetFileVersionInfoSizeW(str(path), None)
    if not 52 <= size <= 8 * 1024 * 1024:
        raise NativeError("wechat_live_version_unavailable")
    buffer = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), wt.UINT()
    if (
        not lib.GetFileVersionInfoW(str(path), 0, size, buffer)
        or not lib.VerQueryValueW(
            buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)
        )
        or length.value < 52
    ):
        raise NativeError("wechat_live_version_unavailable")
    info = ctypes.cast(pointer, ctypes.POINTER(wt.DWORD))
    if info[0] != 0xFEEF04BD:
        raise NativeError("wechat_live_version_unavailable")
    major, minor = int(info[2]), int(info[3])
    value = f"{major >> 16}.{major & 65535}.{minor >> 16}.{minor & 65535}"
    if value == "0.0.0.0" or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value):
        raise NativeError("wechat_live_version_unavailable")
    return value


def process_version(pid: int) -> ClientVersion:
    """Verify ownership and image name, then read the executable resource only."""
    kernel, handle = open_weixin(pid, memory=False)
    try:
        name, size = ctypes.create_unicode_buffer(32768), wt.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise NativeError("wechat_live_version_unavailable")
        path = Path(name.value).resolve()
        return ClientVersion(str(path), file_version(path))
    finally:
        kernel.CloseHandle(handle)


def observe_version(executable: str) -> ClientVersion:
    """Prefer current-user running images; never silently choose mixed versions."""
    try:
        return _observe_version(executable)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeError("wechat_live_version_unavailable") from exc


def _observe_version(executable: str) -> ClientVersion:
    clients = {process_version(int(item["pid"])) for item in discover_processes()}
    if len({client.version for client in clients}) > 1:
        raise NativeError("wechat_live_versions_ambiguous")
    if clients:
        return next(
            (item for item in clients if item.executable == executable),
            min(clients, key=lambda item: item.executable),
        )
    # A stopped client can still have been replaced by an updater in place.
    if not executable:
        raise NativeError("wechat_live_version_unavailable")
    path = Path(executable).resolve()
    return ClientVersion(str(path), file_version(path))
