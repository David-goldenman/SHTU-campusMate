"""QJQ native reader adapted to explicit module/account storage and publication."""
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .native import process, version
from .native.crypto import NativeError, checkpoint
from .native.paths import local_folder
from .native.reader import CST, read_messages
from .native.snapshot import build_snapshot, prune_snapshots, remove_owned, state_of_source
from .text import readable


class VersionChanged(NativeError):
    def __init__(self, client, compatible):
        super().__init__('wechat_version_changed')
        self.client, self.compatible = client, compatible


def discovery():
    return {'available': process.available(), 'folders': process.discover_folders(), 'processes': process.discover_processes() if process.available() else [],
            'tested_version': '4.1.15.13'}


def connect(body, storage, cancel, progress):
    root = process.account_root(body.database_dir)
    client = version.process_version(body.pid)
    keys = process.capture_keys(root, body.pid, cancel, time.monotonic() + 300)
    report = build_snapshot(root, keys, None, 7, cancel, progress, storage)
    checkpoint(cancel, float('inf'))
    if version.observe_version(client.executable) != client:
        raise NativeError('wechat_live_version_changed_during_check')
    return {'mode': 'native', 'database_dir': str(root), 'client_executable': client.executable, 'approved_version': client.version,
            'groups': [row for row in report['groups'] if not row.get('test_channel')]}, {'database_dir': str(root), 'keys': keys}


def inspect_snapshot(value):
    base = local_folder(value)
    root = base if (base / 'message').is_dir() else base / 'decrypted'
    root = root.resolve()
    if not root.is_relative_to(base) or root.name == 'db_storage':
        raise NativeError('wechat_snapshot_invalid')
    paths = sorted(path for path in (root / 'message').glob('message_*.db') if re.fullmatch(r'message_\d+\.db', path.name))
    if not paths or len(paths) > 100:
        raise NativeError('wechat_snapshot_invalid')
    groups, names = {}, {}
    contact = root / 'contact/contact.db'
    for path in ([contact] if contact.exists() else []) + paths:
        if not path.resolve().is_relative_to(root) or path.with_name(path.name + '-wal').exists():
            raise NativeError('wechat_snapshot_in_use')
        with path.open('rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                raise NativeError('wechat_snapshot_encrypted')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            deadline = time.monotonic() + 10
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            if path == contact:
                names = {str(row[0]): str(row[1] or row[2] or '未命名群聊') for row in db.execute("SELECT username,remark,nick_name FROM contact WHERE username LIKE '%@chatroom' LIMIT 3001")}
            else:
                for (name,) in db.execute("SELECT DISTINCT user_name FROM Name2Id WHERE user_name LIKE '%@chatroom' LIMIT 3001"):
                    groups[str(name)] = {'id': str(name), 'name': names.get(str(name), str(name)), 'message_count': None}
    if not groups or len(groups) > 3000:
        raise NativeError('wechat_live_no_groups')
    return {'mode': 'snapshot', 'snapshot': str(root), 'groups': list(groups.values()), 'approved_version': ''}


def scan(path, groups, days, cancel):
    if not groups:
        return {}
    values = {group: [] for group in groups}
    names = {}
    contact = path / 'contact/contact.db'
    if contact.exists():
        with closing(sqlite3.connect(contact.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            names = {str(row[0]): str(row[1] or row[2] or row[0]) for row in db.execute('SELECT username,remark,nick_name FROM contact LIMIT 100000')}
    since = datetime.now(CST) - timedelta(days=days)
    for message in read_messages(path, since, groups):
        checkpoint(cancel, float('inf'))
        text, kind, reply_to = readable(message)
        if len(values[message.conversation_id]) >= 20000:
            raise NativeError('wechat_message_limit')
        values[message.conversation_id].append({'remote_id': message.key, 'sender_id': message.sender_id,
            'sender_name': names.get(message.sender_id, message.sender_id), 'sent_at': message.sent_at.astimezone(timezone.utc).isoformat() if message.time_source == 'source' else None,
            'text': text[:64000], 'kind': kind, 'reply_to': reply_to, 'truncated': len(text) > 64000})
    return values


def synchronize(config, secret, storage, cancel, progress, *, compatibility=False, pause_for_version=None):
    selected = [group['id'] for group in config.get('selected', [])]
    if config.get('mode') == 'snapshot':
        report = inspect_snapshot(config['snapshot'])
        return {**report, 'messages': scan(Path(report['snapshot']), selected, config['history_days'], cancel), 'owned_snapshot': False}
    root = process.account_root(secret.get('database_dir', ''))
    client = version.observe_version(config.get('client_executable', ''))
    changed = client.version != config.get('approved_version') or compatibility
    if changed:
        if pause_for_version:
            pause_for_version(client)
        candidate = None
        try:
            report = build_snapshot(root, secret['keys'], set(selected) if selected else None, config['history_days'], cancel, progress, storage)
            candidate = Path(report['snapshot']) if report['snapshot'] else None
            if version.observe_version(client.executable) != client:
                raise NativeError('wechat_live_version_changed_during_check')
            compatible = True
        except NativeError:
            checkpoint(cancel, float('inf'))
            compatible = False
        finally:
            if candidate:
                remove_owned(candidate, storage / 'snapshots')
        raise VersionChanged(client, compatible)
    if not selected:
        raise NativeError('wechat_live_no_groups')
    current_state = state_of_source(root)
    if current_state == config.get('source_state') and time.time() < config.get('next_expiry', 0) and config.get('snapshot') and Path(config['snapshot']).is_dir():
        return {'unchanged': True}
    report = build_snapshot(root, secret['keys'], set(selected), config['history_days'], cancel, progress, storage)
    candidate = Path(report['snapshot'])
    try:
        values = scan(candidate, selected, config['history_days'], cancel)
        if version.observe_version(client.executable) != client:
            raise NativeError('wechat_live_version_changed_during_check')
        return {**report, 'messages': values, 'owned_snapshot': True}
    except Exception:
        remove_owned(candidate, storage / 'snapshots')
        raise


def discard(report, storage):
    if report.get('owned_snapshot') and report.get('snapshot'):
        remove_owned(Path(report['snapshot']), storage / 'snapshots')


def prune(report, storage):
    if report.get('owned_snapshot'):
        prune_snapshots(Path(report['snapshot']), storage)
