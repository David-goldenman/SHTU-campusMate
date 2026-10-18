"""Build bounded group or filehelper-test snapshots; full shards are temporary."""

import hashlib
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .reader import CST
from .crypto import (
    NativeError,
    checkpoint,
    copy_stable,
    decrypt_database,
    file_state,
    require_space,
)
from .process import source_files

COLUMNS = "local_id,server_id,local_type,real_sender_id,create_time,WCDB_CT_message_content,message_content,compress_content"
SCHEMA = "local_id INTEGER,server_id INTEGER,local_type INTEGER,real_sender_id INTEGER,create_time INTEGER,WCDB_CT_message_content INTEGER,message_content,compress_content"
Progress = Callable[[str, int, int], None]


def state_of_source(root: Path) -> dict[str, Any]:
    return {
        path.relative_to(root).as_posix(): [
            list(state) if state else None
            for state in (
                file_state(path),
                file_state(path.with_name(path.name + "-wal")),
            )
        ]
        for path in source_files(root)
    }


def database(
    path: Path, cancel: threading.Event, deadline: float
) -> sqlite3.Connection:
    db = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    db.execute("PRAGMA trusted_schema=OFF")
    db.execute("PRAGMA query_only=ON")
    db.set_progress_handler(
        lambda: int(cancel.is_set() or time.monotonic() > deadline), 10000
    )
    return db


def remove_owned(path: Path, parent: Path) -> None:
    """Only remove an app-created UUID generation immediately under its own root."""
    root, target = parent.resolve(), path.resolve()
    if (
        target.parent != root
        or len(target.name) != 32
        or any(c not in "0123456789abcdef" for c in target.name)
    ):
        raise NativeError("wechat_live_cleanup_invalid")
    if target.exists():
        shutil.rmtree(target)


@contextmanager
def private_workspace(root: Path) -> Iterator[Path]:
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        remove_owned(path, root)


def prune_snapshots(current: Path, storage: Path) -> None:
    root = (storage / "snapshots")
    generations = sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep = {current.resolve()}
    previous = next(
        (p.resolve() for p in generations if p.resolve() != current.resolve()), None
    )
    if previous:
        keep.add(previous)
    for path in generations:
        if path.resolve() not in keep:
            try:
                remove_owned(path, root)
            except (OSError, NativeError):
                # A reader or AV may still have the old generation open; retry later.
                continue


def build_snapshot(
    root: Path,
    keys: dict[str, str],
    selected: set[str] | None,
    days: int,
    cancel: threading.Event,
    progress: Progress,
    storage: Path,
) -> dict[str, Any]:
    files = source_files(root)
    deadline = time.monotonic() + 600
    since = int((datetime.now(CST) - timedelta(days=days)).timestamp())
    output = (
        (storage / "snapshots" / uuid.uuid4().hex)
        if selected is not None
        else None
    )
    work = (storage / "work")
    work.mkdir(parents=True, exist_ok=True)
    groups: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}
    selected_people: set[str] = set()
    bytes_saved = wal_commits = 0
    earliest: int | None = None
    initial_state = state_of_source(root)
    try:
        if output:
            (output / "message").mkdir(parents=True)
            (output / "contact").mkdir()
        for index, path in enumerate(files):
            checkpoint(cancel, deadline)
            progress("copying", index, len(files))
            relative = path.relative_to(root).as_posix()
            if relative not in keys:
                raise NativeError("wechat_live_keys_incomplete")
            require_space(work, path)
            with private_workspace(work) as temporary:
                copied, plain = (
                    Path(temporary) / "source.db",
                    Path(temporary) / "readable.db",
                )
                copy_stable(path, copied, cancel, deadline)
                progress("decrypting", index, len(files))
                wal_commits += decrypt_database(
                    copied, plain, bytes.fromhex(keys[relative]), cancel, deadline
                )
                with closing(database(plain, cancel, deadline)) as db:
                    if relative == "contact/contact.db":
                        names = {
                            str(user): str(remark or name or "未命名群聊")[:300]
                            for user, remark, name in db.execute(
                                "SELECT username,remark,nick_name FROM contact LIMIT 100000"
                            )
                        }
                        continue
                    progress("selecting_groups", index, len(files))
                    people = dict(db.execute("SELECT rowid,user_name FROM Name2Id"))
                    conversations = {
                        "Msg_" + hashlib.md5(str(name).encode()).hexdigest(): str(name)
                        for name in people.values()
                        if str(name).endswith("@chatroom") or str(name) == "filehelper"
                    }
                    tables = {
                        row[0]
                        for row in db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    destination = (
                        sqlite3.connect(output / "message" / path.name)
                        if output
                        else None
                    )
                    try:
                        if destination:
                            destination.execute("CREATE TABLE Name2Id(user_name TEXT)")
                        sender_ids: set[int] = set()
                        for table, conversation in conversations.items():
                            if table not in tables:
                                continue
                            checkpoint(cancel, deadline)
                            # Only groups and the explicitly selected self-test channel.
                            count, _newest = db.execute(
                                f'SELECT count(*),max(create_time) FROM "{table}" WHERE create_time>=?',
                                (since,),
                            ).fetchone()
                            group = groups.setdefault(
                                conversation,
                                {
                                    "id": conversation,
                                    "name": (
                                        "文件传输助手（测试通道）"
                                        if conversation == "filehelper"
                                        else names.get(conversation, "未命名群聊")
                                    ),
                                    "test_channel": conversation == "filehelper",
                                    "message_count": 0,
                                },
                            )
                            group["message_count"] += count
                            if len(groups) > 3000:
                                raise NativeError("wechat_live_storage_limit")
                            if (
                                destination is None
                                or selected is None
                                or conversation not in selected
                            ):
                                continue
                            destination.execute(f'CREATE TABLE "{table}"({SCHEMA})')
                            cursor = db.execute(
                                f'SELECT {COLUMNS} FROM "{table}" WHERE create_time>=? ORDER BY create_time,local_id',
                                (since,),
                            )
                            while batch := cursor.fetchmany(500):
                                checkpoint(cancel, deadline)
                                if output and sum(p.stat().st_size for p in (output / 'message').glob('*') if p.is_file()) > 512 * 1024**2:
                                    raise NativeError('wechat_live_storage_limit')
                                first_time = int(batch[0][4])
                                earliest = (
                                    min(earliest, first_time)
                                    if earliest is not None
                                    else first_time
                                )
                                destination.executemany(
                                    f'INSERT INTO "{table}" VALUES(?,?,?,?,?,?,?,?)',
                                    batch,
                                )
                                sender_ids.update(
                                    int(row[3]) for row in batch if row[3] is not None
                                )
                            sender_ids.update(
                                int(number)
                                for number, name in people.items()
                                if name == conversation
                            )
                        if destination:
                            selected_people.update(str(people[number]) for number in sender_ids if number in people)
                            destination.executemany(
                                "INSERT INTO Name2Id(rowid,user_name) VALUES(?,?)",
                                [
                                    (number, people[number])
                                    for number in sender_ids
                                    if number in people
                                ],
                            )
                            destination.commit()
                    finally:
                        if destination:
                            destination.close()
                if output:
                    bytes_saved += (output / "message" / path.name).stat().st_size
                    if bytes_saved > 512 * 1024**2:
                        raise NativeError("wechat_live_storage_limit")
        if not groups:
            raise NativeError("wechat_live_no_groups")
        if selected is not None and not selected.issubset(groups):
            raise NativeError("wechat_live_groups_changed")
        if output and selected is not None:
            with closing(sqlite3.connect(output / "contact/contact.db")) as db, db:
                db.execute(
                    "CREATE TABLE contact(username TEXT PRIMARY KEY,remark TEXT,nick_name TEXT)"
                )
                db.executemany(
                    "INSERT INTO contact VALUES(?,?,?)",
                    [(person, "", names.get(person, groups.get(person, {}).get('name', person))) for person in selected_people | selected],
                )
        return {
            "groups": sorted(
                groups.values(), key=lambda g: (-g["message_count"], g["name"])
            ),
            "snapshot": str(output) if output else None,
            "wal_commits": wal_commits,
            "bytes": bytes_saved,
            "next_expiry": (
                earliest + days * 86400
                if earliest is not None
                else time.time() + days * 86400
            ),
            "source_state": initial_state,
        }
    except Exception:
        if output:
            remove_owned(output, (storage / "snapshots"))
        raise
