from datetime import datetime, timezone
from uuid import uuid4
import threading

from fastapi import HTTPException

from backend.services.campus.analysis import account_revision


class Conversations:
    def __init__(self, context):
        self.context = context
        self.lock = threading.RLock()

    def index(self, owner=None):
        with self.lock:
            return self._index(owner or account_revision(self.context))

    def _index(self, owner):
        value = self.context.store.read('conversations:' + owner)
        if value is None:
            value = {'items': [], 'active_id': None}
            legacy = self.context.store.read('chat:' + owner, [])
            if legacy:
                created = legacy[0].get('created_at') or datetime.now(timezone.utc).isoformat()
                item = {'id': uuid4().hex, 'title': next((row['text'][:36] for row in legacy if row['role'] == 'user'), '学习对话'),
                        'created_at': created, 'updated_at': legacy[-1].get('created_at', created), 'archived': False, 'legacy': True}
                value['items'].append(item)
                value['active_id'] = item['id']
                self.context.store.write('conversation:' + owner + ':' + item['id'], legacy)
            self.save(value, owner)
        return value

    def save(self, value, owner):
        self.context.store.write('conversations:' + owner, value)

    def find(self, identity=None, owner=None):
        value = self.index(owner)
        identity = identity or value['active_id']
        item = next((item for item in value['items'] if item['id'] == identity), None)
        if item is None:
            raise HTTPException(404, '这段对话不存在于当前账号。')
        return value, item

    def messages(self, identity=None, owner=None):
        owner = owner or account_revision(self.context)
        if identity is None and not self.index(owner)['active_id']:
            return []
        _, item = self.find(identity, owner)
        return self.context.store.read('conversation:' + owner + ':' + item['id'], [])

    def create(self):
        owner = account_revision(self.context)
        value = self.index(owner)
        now = datetime.now(timezone.utc).isoformat()
        item = {'id': uuid4().hex, 'title': '新对话', 'created_at': now, 'updated_at': now, 'archived': False}
        value['items'].insert(0, item)
        value['active_id'] = item['id']
        self.save(value, owner)
        return item

    def select(self, identity):
        owner = account_revision(self.context)
        value, item = self.find(identity, owner)
        value['active_id'] = item['id']
        self.save(value, owner)
        return {'conversation': item, 'messages': self.messages(identity, owner)}

    def update(self, identity, changes):
        owner = account_revision(self.context)
        value, item = self.find(identity, owner)
        item.update(changes)
        self.save(value, owner)
        return item

    def delete(self, identity):
        owner = account_revision(self.context)
        value, item = self.find(identity, owner)
        self.context.store.delete('conversation:' + owner + ':' + identity)
        if item.get('legacy'):
            self.context.store.delete('chat:' + owner)
        value['items'].remove(item)
        if value['active_id'] == identity:
            value['active_id'] = next((item['id'] for item in value['items'] if not item['archived']), None)
        self.save(value, owner)

    def append(self, identity, pair, owner=None):
        owner = owner or account_revision(self.context)
        if owner != account_revision(self.context):
            raise HTTPException(409, '账号已更新，请重新发送。')
        value, item = self.find(identity, owner)
        messages = self.messages(identity, owner)
        if not messages:
            item['title'] = ' '.join(pair[0]['text'].split())[:36]
        self.context.store.write('conversation:' + owner + ':' + identity, messages + pair)
        item['updated_at'] = pair[-1]['created_at']
        value['active_id'] = identity
        self.save(value, owner)
