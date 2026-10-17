"""Account-bound local calendar commands, shared by the page and study tools."""
from datetime import date, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.services.campus.analysis import account_revision
from .calendar import ClassAdjustment, Event, ZONE, calendar


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['create', 'update', 'delete', 'adjust_class']
    account_revision: str = Field(min_length=1, max_length=100)
    request_id: str = Field(pattern=r'^[a-f0-9-]{16,64}$')
    record_id: str = Field(default='', max_length=400)
    expected_revision: str | None = Field(default=None, max_length=100)
    event: dict = Field(default_factory=dict)
    adjustment: ClassAdjustment | None = None


def event_record(body, identity=None):
    item = {**body.model_dump(mode='json'), 'id': identity or 'local:' + uuid4().hex, 'source': 'local', 'revision': uuid4().hex,
            'at': body.starts_at.astimezone(ZONE).isoformat() if body.starts_at else None}
    if body.event_type == 'exam' and body.starts_at:
        item['start_time'] = body.starts_at.astimezone(ZONE).strftime('%H:%M')
    return item


def event_fields(item):
    return {key: item[key] for key in Event.model_fields if key in item}


def adjustments_key(source):
    metadata = source.snapshot()['data']['metadata']
    return 'class-adjustments:' + source.owner() + ':' + str(metadata.get('semester_id', metadata.get('semester', '')))


def execute(context, source, settings, body, combined):
    with source.lock:
        if body.account_revision != account_revision(context):
            raise HTTPException(409, '账号已更新，请重新读取时间表。')
        owner = source.owner()
        events_key, rules_key, receipts_key = ('events:' + owner, adjustments_key(source), 'calendar-commands:' + owner)
        receipts = context.store.read(receipts_key, [])
        request = body.model_dump(mode='json')
        prior = next((item for item in receipts if item['request_id'] == body.request_id), None)
        if prior:
            if prior['request'] != request:
                raise HTTPException(409, '此操作编号已用于另一项修改，请重新发起。')
            return {**prior['result'], 'already_applied': True}
        events, rules = context.store.read(events_key, []), context.store.read(rules_key, [])
        before, after, affected = None, None, 1
        dates = settings()
        external = [item for item in combined['events'] if item.get('source') != 'local']
        data = {**source.snapshot()['data'], 'events': events + external}
        check_days = []
        try:
            if body.action == 'create':
                if body.record_id or body.adjustment:
                    raise HTTPException(422, '新增安排不接受目标课程或调整字段。')
                event = Event.model_validate(body.event)
                after = event_record(event, 'local:command:' + body.request_id)
                existing = next((item for item in events if item['id'] == after['id']), None)
                if existing:
                    if event_fields(existing) != event_fields(after):
                        raise HTTPException(409, '此操作编号已创建另一项安排。')
                    after = existing
                else:
                    events.append(after)
                day = date.fromisoformat(after['at'][:10] if after['at'] else after['date'])
            elif body.action in {'update', 'delete'}:
                if body.adjustment or (body.action == 'delete' and body.event):
                    raise HTTPException(422, '个人安排修改不接受课程调整字段。')
                before = next((item for item in events if item['id'] == body.record_id), None)
                if before is None:
                    raise HTTPException(404, '未找到可编辑的个人安排；教务课程应使用课程调整。')
                if body.expected_revision is None or before.get('revision', '') != body.expected_revision:
                    raise HTTPException(409, '安排已变化，请重新读取后修改，避免覆盖新的手动编辑。')
                day = date.fromisoformat(before['at'][:10] if before.get('at') else before['date'])
                events = [item for item in events if item['id'] != body.record_id]
                if body.action == 'update':
                    fields = event_fields(before)
                    if body.event.get('starts_at') and before.get('period_start'):
                        fields.update(date=None, period_start=None, period_end=None)
                    if body.event.get('period_start'):
                        fields.update(starts_at=None, ends_at=None)
                    event = Event.model_validate({**fields, **body.event})
                    after = {**before, **event_record(event, before['id'])}
                    if event.event_type != 'exam' or not event.starts_at:
                        after.pop('start_time', None)
                    events.append(after)
                    day = date.fromisoformat(after['at'][:10] if after['at'] else after['date'])
            else:
                rule = body.adjustment
                if rule is None or body.event or not dates['week_one']:
                    raise HTTPException(422, '课程调整需要已设置的教学周及明确的课程、日期和范围。')
                lesson = next((item for item in data['timetable'] if item['id'] == rule.lesson_id), None)
                anchor = date.fromisoformat(dates['week_one'])
                week = (rule.on_date - anchor).days // 7 + 1
                if lesson is None or week not in lesson['weeks'] or rule.on_date.isoweekday() != lesson['weekday']:
                    raise HTTPException(409, '原课程或教学周已变化，请重新读取后选择该次课程。')
                original_id = lesson['id'] + ':' + rule.on_date.isoformat()
                if body.record_id not in {original_id, original_id + ':moved'}:
                    raise HTTPException(422, '目标记录与课程日期不一致。')
                current = calendar(data, rule.on_date, dates['week_one'], rules)
                before = next((item for day_row in current['days'] for item in day_row['events'] if item['id'] == original_id), None)
                if before is None or body.expected_revision is None or before.get('revision', '') != body.expected_revision:
                    raise HTTPException(409, '课程安排已变化，请重新读取后调整。')
                if rule.scope == 'following':
                    check_days = [anchor + timedelta(days=(w - 1) * 7 + lesson['weekday'] - 1) for w in lesson['weeks']]
                    check_days = [day for day in check_days if rule.on_date <= day <= (rule.until_date or date.max)]
                    affected = len(check_days)
                after = {**rule.model_dump(mode='json'), 'id': body.request_id, 'title': lesson['title'], 'semester': data['metadata'].get('semester', '')}
                rules.append(after)
                day = rule.starts_at.astimezone(ZONE).date() if rule.starts_at else rule.to_date or rule.on_date
                check_days = [value + (day - rule.on_date) for value in check_days]
        except ValidationError as error:
            raise HTTPException(422, '安排字段不完整或时间无效，请核对类型、日期和起止时间。') from error
        data['events'] = events + external
        week = calendar(data, day, dates['week_one'], rules)
        checked = {week['week_start']: week['conflicts']}
        for value in check_days:
            monday = (value - timedelta(days=value.weekday())).isoformat()
            if monday not in checked:
                checked[monday] = calendar(data, value, dates['week_one'], rules)['conflicts']
        conflict = {'items': [item for value in checked.values() for item in value['items']],
                    'complete': all(value['complete'] for value in checked.values()) and not combined.get('issues'),
                    'message': '；'.join(dict.fromkeys([value['message'] for value in checked.values() if value['message']] + combined.get('issues', [])))}
        result = {'applied': True, 'request_id': body.request_id, 'action': body.action, 'before': before, 'after': after, 'affected_count': affected,
                  'week_start': week['week_start'], 'conflicts': conflict, 'checked_weeks': sorted(checked), 'local_only': True}
        if body.account_revision != account_revision(context) or owner != source.owner():
            raise HTTPException(409, '账号已更新，本次修改未保存。')
        context.store.write(rules_key if body.action == 'adjust_class' else events_key, rules if body.action == 'adjust_class' else events)
        context.store.write(receipts_key, [*receipts, {'request_id': body.request_id, 'request': request, 'result': result}][-200:])
        return result
