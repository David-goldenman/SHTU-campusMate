"""Local learning records and one-shot reminders, independent of school submission state."""
import asyncio
import threading
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.services.campus.analysis import account_revision
from backend.services.campus.data import digest


class WorkItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['assignment', 'reminder', 'plan']
    title: str = Field(min_length=1, max_length=120)
    status: Literal['todo', 'in_progress', 'done', 'cancelled'] = 'todo'
    notes: str = Field(default='', max_length=12000)
    due_at: AwareDatetime | None = None
    assignment_id: str = Field(default='', max_length=400)

    @model_validator(mode='after')
    def validate_item(self):
        if not self.title.strip() or (self.kind == 'reminder' and not self.due_at):
            raise ValueError('提醒需要明确的时间，事项需要名称。')
        if (self.kind == 'assignment') != bool(self.assignment_id):
            raise ValueError('本地作业状态必须关联实际读取的作业。')
        return self


class WorkCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['create', 'update', 'delete', 'set_assignment']
    request_id: str = Field(pattern=r'^[a-f0-9-]{16,64}$')
    account_revision: str = Field(min_length=1, max_length=100)
    record_id: str = Field(default='', max_length=400)
    expected_revision: str | None = None
    item: dict = Field(default_factory=dict)


class WorkEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['create', 'update', 'delete', 'set_assignment']
    quote: str = Field(min_length=2, max_length=8000)
    record_id: str = Field(default='', max_length=400)
    item: dict = Field(default_factory=dict)


class Workspace:
    def __init__(self, context):
        self.context, self.lock = context, threading.RLock()
        self.stopping, self.wake = threading.Event(), threading.Event()
        self.thread = None

    def state(self, owner):
        return self.context.store.read('work:' + owner, {'items': [], 'receipts': []})

    def snapshot(self):
        with self.lock:
            owner = account_revision(self.context)
            state = self.state(owner)
            return {'account_revision': owner, 'items': state['items'], 'changes': [row['result'] for row in state['receipts'][-30:]],
                    'reminder_delivery': '应用服务运行时约每 30 秒检查一次；离线期间到期的提醒在下次启动后补发到通知中心。'}

    async def command(self, body):
        assignment = None
        if body.action == 'set_assignment':
            response = await self.context.api('assignments')
            if response.status_code != 200:
                raise HTTPException(409, '请先启用并同步作业来源。')
            assignment = next((row for row in response.json()['data']['assignments'] if row['id'] == body.record_id), None)
            if assignment is None:
                raise HTTPException(404, '作业已不在当前缓存，请重新查询。')
        with self.lock:
            owner = account_revision(self.context)
            if body.account_revision != owner:
                raise HTTPException(409, '账号已变化，本次修改未保存。')
            state, request = self.state(owner), body.model_dump(mode='json')
            prior = next((row for row in state['receipts'] if row['request_id'] == body.request_id), None)
            if prior:
                if prior['request'] != request:
                    raise HTTPException(409, '操作编号已经用于另一项修改。')
                return {**prior['result'], 'already_applied': True}
            identity = 'work:assignment:' + digest(body.record_id) if assignment else body.record_id
            before = next((row for row in state['items'] if row['id'] == identity), None)
            if body.action != 'create':
                if before is None and not assignment:
                    raise HTTPException(404, '未找到这条学习事务。')
                revision = before['revision'] if before else ''
                if body.expected_revision != revision:
                    raise HTTPException(409, '记录已被修改，请重新读取，避免覆盖手动编辑。')
            try:
                after = None
                if body.action == 'create':
                    if body.record_id:
                        raise HTTPException(422, '新增事项不接受已有记录 ID。')
                    item = WorkItem.model_validate(body.item)
                    if item.kind == 'assignment':
                        raise HTTPException(422, '作业状态请使用 set_assignment。')
                    identity = 'work:' + body.request_id
                    if any(row['id'] == identity for row in state['items']):
                        raise HTTPException(409, '此操作编号已创建事项，请重新读取，不能覆盖已有修改。')
                elif body.action == 'set_assignment':
                    if set(body.item) - {'status', 'notes'} or 'status' not in body.item:
                        raise HTTPException(422, '作业只允许修改本地状态和备注。')
                    item = WorkItem(kind='assignment', title=assignment['title'][:120], assignment_id=assignment['id'],
                                    notes=(before or {}).get('notes', ''), **{key: value for key, value in body.item.items() if key != 'notes'})
                    if 'notes' in body.item:
                        item = WorkItem.model_validate({**item.model_dump(), 'notes': body.item['notes']})
                elif body.action == 'update':
                    if set(body.item) & {'kind', 'assignment_id'} or before['kind'] == 'assignment':
                        raise HTTPException(422, '不能更换事项类型或作业关联；作业状态请使用 set_assignment。')
                    item = WorkItem.model_validate({**{key: before[key] for key in WorkItem.model_fields}, **body.item})
                elif body.item:
                    raise HTTPException(422, '删除操作不接受新字段。')
                if body.action != 'delete':
                    after = {**item.model_dump(mode='json'), 'id': identity, 'revision': uuid4().hex,
                             'updated_at': datetime.now(timezone.utc).isoformat(), 'source': 'local'}
                    if before and before.get('delivered_at') and before.get('due_at') == after.get('due_at'):
                        after['delivered_at'] = before['delivered_at']
            except ValidationError as error:
                raise HTTPException(422, '请核对事项名称、状态及带时区的提醒时间。') from error
            result = {'applied': True, 'domain': 'workspace', 'request_id': body.request_id, 'action': body.action,
                      'before': before, 'after': after, 'affected_count': 1, 'local_only': True}
            state['items'] = [row for row in state['items'] if row['id'] != identity] + ([after] if after else [])
            state['receipts'] = [*state['receipts'], {'request_id': body.request_id, 'request': request, 'result': result}][-200:]
            if owner != account_revision(self.context):
                raise HTTPException(409, '账号已变化，本次修改未保存。')
            self.context.store.write('work:' + owner, state)
            self.wake.set()
            return result

    async def deliver_due(self, now=None):
        now = now or datetime.now(timezone.utc)
        owner = account_revision(self.context)
        # The same lock serializes edits with delivery, so a cancelled reminder cannot be sent afterward.
        with self.lock:
            state = self.state(owner)
            changed = False
            for item in state['items']:
                if self.stopping.is_set() or owner != account_revision(self.context):
                    break
                if item['kind'] != 'reminder' or item['status'] in {'done', 'cancelled'} or item.get('delivered_at') or datetime.fromisoformat(item['due_at']) > now:
                    continue
                payload = {'id': 'study-reminder:' + item['id'], 'account_revision': owner, 'source_revision': item['revision'],
                           'title': item['title'], 'summary': (item['notes'] or '你设置的学习提醒已到时间。')[:3000],
                           'why': '用户设置的本地提醒', 'event_at': item['due_at'], 'importance': 'important', 'citations': []}
                response = await self.context.api('notifications', '/imports', method='POST', body=payload)
                if response.status_code == 200 and owner == account_revision(self.context):
                    item['delivered_at'] = now.isoformat()
                    item.pop('delivery_error', None)
                    changed = True
                else:
                    changed = changed or item.get('delivery_error') != '通知中心不可用，将在恢复后重试。'
                    item['delivery_error'] = '通知中心不可用，将在恢复后重试。'
            if changed and owner == account_revision(self.context):
                self.context.store.write('work:' + owner, state)

    def start(self):
        def run():
            while not self.stopping.is_set():
                try:
                    asyncio.run(self.deliver_due())
                except Exception:
                    pass  # Keep pending records for the next delivery attempt.
                self.wake.wait(30)
                self.wake.clear()
        self.thread = threading.Thread(target=run, name='study-reminders', daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        self.wake.set()
        if self.thread:
            self.thread.join()
