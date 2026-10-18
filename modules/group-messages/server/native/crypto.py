"""Read-only WCDB/SQLCipher4 snapshots, including committed SQLite WAL frames.

Format: https://sqlite.org/fileformat2.html#walformat
WCDB constants: TANGandXUE/wcdb-key-tool (MIT, WCDB_LICENSE.txt).
No original database is opened by SQLite, locked, checkpointed, or modified.
"""

import ctypes
import hashlib
import hmac
import os
import shutil
import sqlite3
import struct
import threading
import time
from contextlib import closing
from ctypes import wintypes as wt
from pathlib import Path
from typing import Any

PAGE = 4096
RESERVE = 80
HEADER = b"SQLite format 3\x00"


class NativeError(RuntimeError):
    """Public code only; never include keys, memory contents or database text."""


def checkpoint(cancel: threading.Event, deadline: float) -> None:
    if cancel.is_set():
        raise NativeError("wechat_live_cancelled")
    if time.monotonic() > deadline:
        raise NativeError("wechat_live_timeout")


def mac_key(key: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", key, bytes(x ^ 0x3A for x in salt), 2, 32)


def authentic(page: bytes, number: int, secret: bytes) -> bool:
    if len(page) != PAGE:
        return False
    start = 16 if number == 1 else 0
    expected = hmac.digest(
        secret, page[start : PAGE - 64] + struct.pack("<I", number), "sha512"
    )
    return hmac.compare_digest(expected, page[-64:])


def verifies(key: bytes, page: bytes) -> bool:
    return len(key) == 32 and authentic(page, 1, mac_key(key, page[:16]))


class AESCBC:
    """One Windows CNG key handle per database, not one handle per page."""

    def __init__(self, key: bytes) -> None:
        if os.name != "nt" or len(key) != 32:
            raise NativeError("wechat_live_windows_required")
        self.lib: Any = ctypes.WinDLL("bcrypt", use_last_error=True)
        self.algorithm, self.key = wt.HANDLE(), wt.HANDLE()
        self.lib.BCryptOpenAlgorithmProvider.argtypes = [
            ctypes.POINTER(wt.HANDLE),
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            wt.ULONG,
        ]
        self.lib.BCryptSetProperty.argtypes = [
            wt.HANDLE,
            ctypes.c_wchar_p,
            ctypes.c_char_p,
            wt.ULONG,
            wt.ULONG,
        ]
        self.lib.BCryptGenerateSymmetricKey.argtypes = [
            wt.HANDLE,
            ctypes.POINTER(wt.HANDLE),
            ctypes.c_void_p,
            wt.ULONG,
            ctypes.c_char_p,
            wt.ULONG,
            wt.ULONG,
        ]
        self.lib.BCryptDestroyKey.argtypes = [wt.HANDLE]
        self.lib.BCryptCloseAlgorithmProvider.argtypes = [wt.HANDLE, wt.ULONG]
        self.lib.BCryptDecrypt.argtypes = [
            wt.HANDLE,
            ctypes.c_char_p,
            wt.ULONG,
            ctypes.c_void_p,
            ctypes.c_char_p,
            wt.ULONG,
            ctypes.c_char_p,
            wt.ULONG,
            ctypes.POINTER(wt.ULONG),
            wt.ULONG,
        ]
        try:
            self._check(
                self.lib.BCryptOpenAlgorithmProvider(
                    ctypes.byref(self.algorithm), "AES", None, 0
                )
            )
            mode = "ChainingModeCBC\0".encode("utf-16-le")
            self._check(
                self.lib.BCryptSetProperty(
                    self.algorithm, "ChainingMode", mode, len(mode), 0
                )
            )
            self._check(
                self.lib.BCryptGenerateSymmetricKey(
                    self.algorithm, ctypes.byref(self.key), None, 0, key, 32, 0
                )
            )
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(status: int) -> None:
        if status != 0:
            raise NativeError("wechat_live_crypto_failed")

    def decrypt(self, value: bytes, iv: bytes) -> bytes:
        output = ctypes.create_string_buffer(len(value))
        vector = ctypes.create_string_buffer(iv, len(iv))
        length = wt.ULONG()
        self._check(
            self.lib.BCryptDecrypt(
                self.key,
                value,
                len(value),
                None,
                vector,
                len(iv),
                output,
                len(output),
                ctypes.byref(length),
                0,
            )
        )
        return output.raw[: length.value]

    def close(self) -> None:
        if self.key:
            self.lib.BCryptDestroyKey(self.key)
            self.key = wt.HANDLE()
        if self.algorithm:
            self.lib.BCryptCloseAlgorithmProvider(self.algorithm, 0)
            self.algorithm = wt.HANDLE()


def checksum(
    value: bytes, endian: str, previous: tuple[int, int] = (0, 0)
) -> tuple[int, int]:
    """SQLite's required rolling checksum, not a file fingerprint."""
    first, second = previous
    for a, b in struct.iter_unpack(endian + "II", value):
        first = (first + a + second) & 0xFFFFFFFF
        second = (second + b + first) & 0xFFFFFFFF
    return first, second


def wal_pages(
    path: Path, cancel: threading.Event, deadline: float
) -> tuple[dict[int, int], int, int]:
    """Page offsets through the last valid COMMIT; discard uncommitted/old tail."""
    if not path.exists() or path.stat().st_size == 0:
        return {}, 0, 0
    with path.open("rb") as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise NativeError("wechat_live_source_busy")
        magic, version, size, _, salt1, salt2, c1, c2 = struct.unpack(">8I", header)
        if magic not in {0x377F0682, 0x377F0683} or version != 3007000 or size != PAGE:
            raise NativeError("wechat_live_format_unsupported")
        endian = "<" if magic == 0x377F0682 else ">"
        rolling = checksum(header[:24], endian)
        if rolling != (c1, c2):
            raise NativeError("wechat_live_source_busy")
        committed: dict[int, int] = {}
        pending: dict[int, int] = {}
        database_size = commits = 0
        while True:
            checkpoint(cancel, deadline)
            frame = stream.read(24)
            if not frame:
                break
            page = stream.read(PAGE)
            if len(frame) != 24 or len(page) != PAGE:
                break
            number, count, s1, s2, c1, c2 = struct.unpack(">6I", frame)
            if (s1, s2) != (salt1, salt2):
                break
            rolling = checksum(frame[:8] + page, endian, rolling)
            if rolling != (c1, c2):
                break
            if not 1 <= number <= 2_097_152 or count > 2_097_152:
                raise NativeError("wechat_live_storage_limit")
            pending[number] = stream.tell() - PAGE
            if count:
                committed.update(pending)
                pending.clear()
                database_size = count
                commits += 1
        return (
            {p: offset for p, offset in committed.items() if p <= database_size},
            database_size,
            commits,
        )


def file_state(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
        return info.st_ino, info.st_size, info.st_mtime_ns
    except FileNotFoundError:
        return None


def copy_stable(
    source: Path, target: Path, cancel: threading.Event, deadline: float
) -> None:
    """Copy DB + WAL only when both remained stable; never checkpoint the source."""
    wal = source.with_name(source.name + "-wal")
    if source.with_name(source.name + "-journal").exists():
        raise NativeError("wechat_live_source_busy")
    target.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        checkpoint(cancel, deadline)
        before = (file_state(source), file_state(wal))
        if before[0] is None or sum(item[1] for item in before if item) > 8 * 1024**3:
            raise NativeError("wechat_live_storage_limit")
        for origin, output in (
            (source, target),
            (wal, target.with_name(target.name + "-wal")),
        ):
            if not origin.exists():
                output.unlink(missing_ok=True)
                continue
            with origin.open("rb") as inp, output.open("wb") as out:
                while chunk := inp.read(1024 * 1024):
                    checkpoint(cancel, deadline)
                    out.write(chunk)
        after = (file_state(source), file_state(wal))
        if before == after:
            return
    raise NativeError("wechat_live_source_busy")


def decrypt_database(
    source: Path, output: Path, key: bytes, cancel: threading.Event, deadline: float
) -> int:
    """Authenticate every used encrypted page and overlay the committed WAL view."""
    wal = source.with_name(source.name + "-wal")
    frames, committed_size, commits = wal_pages(wal, cancel, deadline)
    size = source.stat().st_size
    if size < PAGE or size % PAGE:
        raise NativeError("wechat_live_format_unsupported")
    count = committed_size or size // PAGE
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as inp:
        first = inp.read(PAGE)
        if not verifies(key, first):
            raise NativeError("wechat_live_key_changed")
        secret = mac_key(key, first[:16])
        with (
            closing(AESCBC(key)) as cipher,
            output.open("wb") as out,
            wal.open("rb") if frames else source.open("rb") as changes,
        ):
            for number in range(1, count + 1):
                checkpoint(cancel, deadline)
                if number in frames:
                    changes.seek(frames[number])
                    page = changes.read(PAGE)
                else:
                    inp.seek((number - 1) * PAGE)
                    page = inp.read(PAGE)
                if number > 1 and page == bytes(PAGE):
                    out.write(page)
                    continue
                if not authentic(page, number, secret):
                    raise NativeError("wechat_live_page_integrity_failed")
                start = 16 if number == 1 else 0
                plain = cipher.decrypt(
                    page[start : PAGE - RESERVE], page[PAGE - RESERVE : PAGE - 64]
                )
                out.write((HEADER if number == 1 else b"") + plain + bytes(RESERVE))
    # Only the new, private copy is opened. Immutable bypasses WAL creation entirely.
    with closing(
        sqlite3.connect(output.as_uri() + "?mode=ro&immutable=1", uri=True)
    ) as db:
        db.execute("PRAGMA trusted_schema=OFF")
        db.set_progress_handler(
            lambda: int(cancel.is_set() or time.monotonic() > deadline), 10000
        )
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise NativeError("wechat_live_snapshot_invalid")
    return commits


def require_space(root: Path, source: Path) -> None:
    wal = source.with_name(source.name + '-wal')
    required = (source.stat().st_size + (wal.stat().st_size if wal.exists() else 0)) * 3 + 128 * 1024**2
    if shutil.disk_usage(root).free < required:
        raise NativeError("wechat_live_disk_full")
