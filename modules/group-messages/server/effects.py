"""Version-checked public API writes with durable requests and reversible receipts."""
from copy import deepcopy
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re
from zoneinfo import ZoneInfo
from uuid import uuid4
from fastapi import HTTPException
from .messages import identity, stamp

WORK_FIELDS = ('title', 'status', 'notes', 'due_at')
EVENT_FIELDS = ('title', 'event_type', 'starts_at', 'ends_at', 'date', 'period_start', 'period_end', 'location', 'course_title', 'notes')


class Effects:
    def __init__(self, service):
        self.service, self.context = service, service.context

    async def api(self, owner, module, path, *, body=None):
        self.service.check(owner)
        response = await self.context.api(module, path, method='POST' if body is not None else 'GET', body=body)
        if response.status_code >= 400:
            if response.status_code in {404, 503}:
                raise HTTPException(409, '目标功能未启用或记录已移除，请核对后再试。')
            raise HTTPException(response.status_code, '目标记录已变化或服务暂时不可用，请核对后再试。')
        return response.json()

    def notes(self, item):
        refs = '\n'.join(f"{ref.get('sent_at') or '时间未知'}：{ref['quote']}" for ref in item['citations'])
        return (item['summary'] + ('\n日期：' + item['date'] + '（未提供具体钟点）' if item.get('date') and not item.get('due_at') and not item.get('starts_at') else '')
                + '\n来源：' + item['group_name'] + '\n' + refs)[:1900]

    async def publish(self, owner, item):
        with self.service.lock:
            self.service.check(owner)
            current = self.service.all_items(owner).get(item['id'])
            if current is None or current['revision'] != item['revision']:
                return
            active = item['status'] != 'dismissed' and self.service.visible(item, self.service.sources(owner))
        revision = item['content_revision'] + ':' + item['status'] + ':' + str(active)
        if item.get('published_revision') == revision:
            return
        body = {'account_revision': owner, 'id': 'group:' + item['id'], 'title': (('待核实 · ' if item['status'] == 'pending' else '') + item['title'])[:120],
                'summary': item['summary'], 'source_revision': revision, 'importance': 'important', 'why': '所选课程群消息；可在群消息页面核对原文。',
                'citations': [{'id': ref['message_id'], 'title': item['group_name'], 'source': 'group-messages', 'url': '#group-messages'} for ref in item['citations'][-10:]],
                'event_at': item.get('due_at') or item.get('starts_at'), 'active': active}
        await self.api(owner, 'notifications', '/imports', body=body)
        with self.service.lock:
            self.service.check(owner)
            fresh = self.service.all_items(owner).get(item['id'])
            if fresh and fresh['revision'] == item['revision']:
                fresh.update(published_revision=revision, publish_error=None)
                self.service.save_item(owner, fresh)

    async def automatic_conflicts(self, owner, item):
        """A failed or incomplete comparison falls back to explicit confirmation."""
        if item['kind'] == 'assignment':
            snapshot = await self.api(owner, 'courses', '/snapshot')
            members = item.get('course', {}).get('course_ids', [])
            clean = lambda text: re.sub(r'[^\w\u4e00-\u9fff]', '', text.casefold())
            title = clean(item['title'])
            for assignment in snapshot.get('data', {}).get('assignments', []):
                other = clean(assignment.get('title', ''))
                if assignment.get('course_id') in members and other and (title in other or other in title or SequenceMatcher(None, title, other).ratio() >= .7):
                    raise HTTPException(409, '课程平台已有相似作业，请核对截止时间；需要时可手动创建独立的本地待办。')
        if item['kind'] in {'quiz', 'exam'} and item.get('starts_at'):
            if not item.get('ends_at'):
                raise HTTPException(409, '尚无明确结束时间，无法完整检查日程冲突，请手动确认。')
            start, end = (datetime.fromisoformat(item[key]) for key in ('starts_at', 'ends_at'))
            if end - start > timedelta(days=1):
                raise HTTPException(409, '跨日安排需要手动核对。')
            day = start.astimezone(ZoneInfo('Asia/Shanghai')).date()
            schedule = await self.api(owner, 'timetable', '/schedule?week_start=' + day.isoformat())
            plan = schedule.get('calendar', {})
            if not plan.get('conflicts', {}).get('complete') or schedule.get('status') != 'ready' or end.astimezone(ZoneInfo('Asia/Shanghai')).date() != day:
                raise HTTPException(409, '当前课表或时段信息不完整，需手动核对冲突。')
            for slot in plan.get('days', []):
                for event in slot['events']:
                    if event['id'] == (item.get('target') or {}).get('id') or event.get('status') in {'leave', 'cancel', 'moved'} or event.get('event_type') in {'deadline', 'calendar'}:
                        continue
                    if event.get('at') and event.get('ends_at') and max(start, datetime.fromisoformat(event['at'])) < min(end, datetime.fromisoformat(event['ends_at'])):
                        raise HTTPException(409, '群通知与已有日程时间重叠，请核对后手动确认。')

    async def apply(self, owner, item_id, expected_revision, *, automatic=False):
        if automatic:
            with self.service.lock:
                candidate = self.service.current_item(owner, item_id)
                if candidate['revision'] != expected_revision or not candidate.get('automatic_ready'):
                    raise HTTPException(409, '这项通知需要重新核对。')
            await self.automatic_conflicts(owner, candidate)
        with self.service.lock:
            item = self.service.current_item(owner, item_id)
            if item['revision'] != expected_revision:
                raise HTTPException(409, '群通知已变化，请重新核对。')
            if automatic and not item.get('automatic_ready'):
                raise HTTPException(409, '这项通知需要人工核对。')
            if automatic:
                self.service.check(owner, job=True)
                config, group = self.service.selected_group(owner, item['source'], item['group_id'])
                if not config.get('enabled') or not config.get('allow_ai') or not group.get('auto_apply'):
                    raise HTTPException(409, '自动应用已关闭。')
            if item['action'] in {'question', 'uncertain'}:
                raise HTTPException(409, '这条消息仍有歧义，请到学习事务或时间表手动确认具体安排。')
            if item.get('applied_content') == item['content_revision']:
                return item
            if item['kind'] in {'notice', 'material'}:
                item.update(status='accepted', revision=uuid4().hex, automatic=automatic)
                self.service.save_item(owner, item)
                return item
            previous = item.get('target')
            calendar = item['kind'] in {'quiz', 'exam', 'activity'} and bool(item.get('starts_at'))
            module = previous['module'] if previous else 'timetable' if calendar else 'academic-assistant'
            if item['kind'] == 'activity' and automatic:
                raise HTTPException(409, '活动需要明确确认参加。')
            if item['action'] == 'cancel' and not previous:
                raise HTTPException(409, '没有可核对的已导入记录，请查看原安排。')
            if module == 'timetable' and not item.get('starts_at') and item['action'] != 'cancel':
                raise HTTPException(409, '活动缺少明确的开始时刻，请先核对。')
            payload = {'action': 'create', 'account_revision': owner, 'request_id': identity(owner, item_id, item['content_revision'], 'apply', (item.get('undo_receipt') or {}).get('request_id'))}
            if previous:
                payload.update(action='delete' if item['action'] == 'cancel' and module == 'timetable' else 'update',
                               record_id=previous['id'], expected_revision=previous['revision'])
            elif item['action'] == 'change':
                raise HTTPException(409, '变更通知尚未对应到已导入事项，请先核对原事项。')
            if module == 'academic-assistant':
                fields = {'title': item['title'][:120], 'notes': self.notes(item), 'due_at': item.get('due_at') or item.get('starts_at'),
                          'status': 'cancelled' if item['action'] == 'cancel' else 'todo'}
                if not previous:
                    fields['kind'] = 'plan'
                payload['item'] = fields
                path = '/work/commands'
            else:
                if payload['action'] != 'delete':
                    payload['event'] = {'title': item['title'], 'event_type': 'activity' if item['kind'] == 'activity' else item['kind'],
                        'starts_at': item['starts_at'], 'ends_at': item.get('ends_at'), 'location': item.get('location', ''),
                        'course_title': item.get('course', {}).get('title', ''), 'notes': self.notes(item)}
                path = '/commands'
            operation_key = 'operation:' + owner + ':' + item_id
            pending = self.context.store.read(operation_key, {})
            if pending and pending.get('request') != payload:
                raise HTTPException(409, '上一项修改的结果尚未确认，请先重试原操作并核对目标记录。')
            self.context.store.write(operation_key, {'request': payload, 'module': module, 'path': path})
            self.service.check(owner, job=automatic)
        # The exact request is durable before dispatch. A retry never gets a new ID.
        try:
            receipt = await self.api(owner, module, path, body=payload)
        except HTTPException as error:
            if 400 <= error.status_code < 500:
                self.context.store.delete(operation_key)
            raise
        with self.service.lock:
            # Retain the old owner's receipt even if an account switches during an accepted write.
            self.context.store.write('receipt:' + owner + ':' + payload['request_id'], receipt)
            self.service.check(owner)
            current = self.service.current_item(owner, item_id)
            dismissed = current['status'] == 'dismissed' and current['revision'] != expected_revision
            after = receipt.get('after')
            current.update(target={'module': module, 'id': (after or receipt['before'])['id'], 'revision': (after or receipt['before'])['revision'], 'deleted': after is None},
                           receipt={'module': module, 'value': receipt}, applied_content=item['content_revision'], status='applied',
                           automatic=automatic, apply_error=None, revision=uuid4().hex, applied_at=stamp())
            if current['content_revision'] != item['content_revision']:
                current.update(status='pending', apply_error='新的来源已到达，请核对刚完成的修改。')
            if dismissed:
                current['status'] = 'dismissed'
            self.service.save_item(owner, current)
            self.context.store.delete(operation_key)
            return current

    async def undo(self, owner, item_id, expected_revision):
        with self.service.lock:
            item = self.service.current_item(owner, item_id)
            if item['revision'] != expected_revision or not item.get('receipt'):
                raise HTTPException(409, '记录已变化，或没有可撤销的修改。')
            saved = item['receipt']
            receipt, module = saved['value'], saved['module']
            before, after = receipt.get('before'), receipt.get('after')
            payload = {'account_revision': owner, 'request_id': identity(owner, receipt['request_id'], 'undo'), 'action': 'delete' if before is None else 'update' if after else 'create'}
            if after:
                payload.update(record_id=after['id'], expected_revision=after['revision'])
            if before:
                if module == 'academic-assistant':
                    payload['item'] = {key: before[key] for key in WORK_FIELDS if key in before}
                    if not after:
                        payload['item']['kind'] = before['kind']
                else:
                    payload['event'] = {key: before[key] for key in EVENT_FIELDS if key in before}
            key = 'operation:' + owner + ':' + item_id
            pending = self.context.store.read(key, {})
            if pending and pending.get('request') != payload:
                raise HTTPException(409, '上一项修改的结果尚未确认，请先重试原操作并核对目标记录。')
            self.context.store.write(key, {'request': payload, 'module': module, 'path': '/work/commands' if module == 'academic-assistant' else '/commands'})
        try:
            result = await self.api(owner, module, '/work/commands' if module == 'academic-assistant' else '/commands', body=payload)
        except HTTPException as error:
            if 400 <= error.status_code < 500:
                self.context.store.delete(key)
            raise
        with self.service.lock:
            self.context.store.write('receipt:' + owner + ':' + payload['request_id'], result)
            self.service.check(owner)
            current = self.service.current_item(owner, item_id)
            restored = result.get('after')
            current.update(status='dismissed', revision=uuid4().hex, applied_content=None, automatic_ready=False,
                           undo_receipt=result, receipt=None, target={'module': module, 'id': restored['id'], 'revision': restored['revision']} if restored else None, apply_error=None)
            self.service.save_item(owner, current)
            self.context.store.delete(key)
            return current
