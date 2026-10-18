"""Bounded local message cache and durable per-message change sequence."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5


def identity(*parts):
    return uuid5(NAMESPACE_URL, json.dumps(parts, ensure_ascii=False)).hex


def stamp():
    return datetime.now(timezone.utc).isoformat()


class Messages:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'messages.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS messages (
                    owner TEXT NOT NULL, id TEXT NOT NULL, source TEXT NOT NULL,
                    connection TEXT NOT NULL, group_id TEXT NOT NULL,
                    sent_at TEXT, received_at TEXT NOT NULL, body TEXT NOT NULL,
                    revision INTEGER NOT NULL, sequence INTEGER NOT NULL,
                    PRIMARY KEY(owner,id));
                CREATE INDEX IF NOT EXISTS message_group ON messages(owner,source,connection,group_id,sequence);
                CREATE TABLE IF NOT EXISTS changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT, message_id TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, owner, source, connection, group_id, values, since):
        changed = 0
        with self.connect() as db:
            for value in values:
                mid = 'group-message:' + identity(source, connection, group_id, value['remote_id'])
                body = {key: value.get(key) for key in ('remote_id', 'sender_id', 'sender_name', 'sent_at', 'text', 'kind', 'reply_to', 'truncated')}
                encoded = json.dumps(body, ensure_ascii=False, sort_keys=True)
                old = db.execute('SELECT body,revision FROM messages WHERE owner=? AND id=?', (owner, mid)).fetchone()
                if old and old['body'] == encoded:
                    continue
                sequence = db.execute('INSERT INTO changes(owner,message_id) VALUES(?,?)', (owner, mid)).lastrowid
                revision = old['revision'] + 1 if old else 1
                db.execute('''INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(owner,id) DO UPDATE SET body=excluded.body,sent_at=excluded.sent_at,
                    revision=excluded.revision,sequence=excluded.sequence''',
                    (owner, mid, source, connection, group_id, body['sent_at'], stamp(), encoded, revision, sequence))
                changed += 1
            # Unknown source times age by local receipt time, never by a fabricated sending time.
            db.execute('DELETE FROM messages WHERE owner=? AND source=? AND connection=? AND group_id=? AND COALESCE(sent_at,received_at)<?',
                       (owner, source, connection, group_id, since))
            db.execute('DELETE FROM changes WHERE owner=? AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.owner=changes.owner AND m.id=changes.message_id)', (owner,))
        return changed

    @staticmethod
    def unpack(row):
        return {**json.loads(row['body']), 'id': row['id'], 'revision': row['revision'], 'sequence': row['sequence'], 'received_at': row['received_at']}

    def rows(self, owner, source, connection, group_id, *, limit=100, offset=0):
        with self.connect() as db:
            args = (owner, source, connection, group_id)
            count = db.execute('SELECT count(*) FROM messages WHERE owner=? AND source=? AND connection=? AND group_id=?', args).fetchone()[0]
            rows = db.execute('SELECT * FROM messages WHERE owner=? AND source=? AND connection=? AND group_id=? ORDER BY COALESCE(sent_at,received_at) DESC,sequence DESC LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return {'items': [self.unpack(row) for row in rows], 'total': count, 'has_more': offset + len(rows) < count}

    def batch(self, owner, source, connection, group_id, cursor):
        args = (owner, source, connection, group_id)
        with self.connect() as db:
            pending = db.execute('SELECT * FROM messages WHERE owner=? AND source=? AND connection=? AND group_id=? AND sequence>? ORDER BY sequence LIMIT 60', (*args, cursor)).fetchall()
            if not pending:
                return None
            # Include preceding context and reply targets, without throwing away short corrections.
            edge = max(row['sent_at'] or row['received_at'] for row in pending)
            previous = db.execute('SELECT * FROM messages WHERE owner=? AND source=? AND connection=? AND group_id=? AND COALESCE(sent_at,received_at)<=? ORDER BY COALESCE(sent_at,received_at) DESC LIMIT 80', (*args, edge)).fetchall()
            replies = []
            for row in pending:
                reply = json.loads(row['body']).get('reply_to')
                if reply:
                    remote = f'wechat:{group_id}:server:{reply}' if source == 'wechat' else reply
                    mid = 'group-message:' + identity(source, connection, group_id, remote)
                    target = db.execute('SELECT * FROM messages WHERE owner=? AND id=?', (owner, mid)).fetchone()
                    if target:
                        replies.append(target)
            previous = replies + previous
        selected, size = {}, 0
        for row in pending:
            value = self.unpack(row)
            length = len(value['text'] or '')
            if selected and size + min(length, 8000) > 70000:
                break
            value['text'] = (value['text'] or '')[:8000]
            value['truncated'] = bool(value.get('truncated') or length > 8000)
            selected[value['id']] = value
            size += len(value['text'])
        new_ids = set(selected)
        next_cursor = max(value['sequence'] for value in selected.values())
        for row in previous:
            value = self.unpack(row)
            if value['id'] in selected or value['sequence'] > next_cursor:
                continue
            value['text'] = (value['text'] or '')[:8000]
            if size + len(value['text']) > 90000:
                continue
            selected[value['id']] = value
            size += len(value['text'])
        values = sorted(selected.values(), key=lambda value: (value['sent_at'] or value['received_at'], value['sequence']))
        return {'messages': values, 'new_ids': sorted(new_ids), 'cursor': next_cursor,
                'versions': {value['id']: value['revision'] for value in values}}

    def versions_match(self, owner, expected):
        with self.connect() as db:
            return all((row := db.execute('SELECT revision FROM messages WHERE owner=? AND id=?', (owner, mid)).fetchone()) and row[0] == revision
                       for mid, revision in expected.items())

