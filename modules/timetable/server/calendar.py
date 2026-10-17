from datetime import date, datetime, time, timedelta
from datetime import date as CalendarDate
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from backend.services.campus.data import digest

ZONE = ZoneInfo('Asia/Shanghai')


class SemesterSettings(BaseModel):
    week_one: date

    @model_validator(mode='after')
    def monday(self):
        if self.week_one.weekday() != 0:
            raise ValueError('第 1 教学周的起始日期应为周一。')
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    event_type: Literal['quiz', 'exam', 'tutorial', 'study', 'presentation', 'activity', 'lecture']
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    date: CalendarDate | None = None
    period_start: int | None = Field(default=None, ge=1, le=30)
    period_end: int | None = Field(default=None, ge=1, le=30)
    location: str = Field(default='', max_length=200)
    course_title: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def interval(self):
        if not self.title.strip() or (self.ends_at and (not self.starts_at or self.ends_at <= self.starts_at)):
            raise ValueError('请填写事项名称，结束时间须晚于开始时间。')
        numbered = self.period_start is not None or self.period_end is not None
        if numbered:
            if not self.date or self.period_start is None or self.period_end is None or self.period_end < self.period_start or self.starts_at:
                raise ValueError('按节次安排需要日期和完整起止节次，不能同时填写钟点。')
        elif not self.starts_at or self.date:
            raise ValueError('请提供带时区的开始时间，或日期与起止节次。')
        return self


class ClassAdjustment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lesson_id: str = Field(min_length=1, max_length=300)
    on_date: date
    action: Literal['leave', 'cancel', 'move', 'restore']
    scope: Literal['once', 'following'] = 'once'
    until_date: date | None = None
    to_date: date | None = None
    period_start: int | None = Field(default=None, ge=1, le=30)
    period_end: int | None = Field(default=None, ge=1, le=30)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=200)
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def interval(self):
        if self.until_date and (self.scope != 'following' or self.until_date < self.on_date):
            raise ValueError('结束日期只用于从本次起的调整，且不得早于原课程日期。')
        numbered = self.period_start is not None or self.period_end is not None
        if numbered and (self.period_start is None or self.period_end is None or self.period_end < self.period_start):
            raise ValueError('请提供完整且有序的起止节次。')
        if self.starts_at and (numbered or self.to_date):
            raise ValueError('调课请选择具体钟点或日期与节次，不要混用。')
        if self.ends_at and (not self.starts_at or self.ends_at <= self.starts_at):
            raise ValueError('结束时间须晚于开始时间。')
        moving = self.to_date or numbered or self.starts_at or self.location is not None
        if self.action == 'move' and not moving:
            raise ValueError('调课需要新的日期、节次、钟点或地点。')
        if self.action != 'move' and moving:
            raise ValueError('请假、取消和恢复不接受调课字段。')
        return self


def lesson_periods(data):
    """Old snapshots keep their lesson numbers without inventing clock times."""
    metadata = data['metadata']
    clocks = {}
    for item in metadata.get('periods') or []:
        try:
            number = item['period']
            start, end = time.fromisoformat(item['start']), time.fromisoformat(item['end'])
            if type(number) is int and 1 <= number <= 30 and start < end and not start.tzinfo and not end.tzinfo:
                clocks[number] = {'period': number, 'start': start.strftime('%H:%M'), 'end': end.strftime('%H:%M')}
        except (KeyError, TypeError, ValueError):
            continue
    numbers = [metadata.get('units', 0), *clocks, *(item.get('period_end') for item in data['timetable'] + data.get('events', []))]
    count = max((value for value in numbers if type(value) is int and 1 <= value <= 30), default=0)
    return [clocks.get(number, {'period': number, 'start': None, 'end': None}) for number in range(1, count + 1)]


def event_order(item):
    if item.get('period_start') is not None:
        return (0, item['period_start'], item['period_end'], item['id'])
    at = item.get('at') or item['date'] + 'T00:00:00+08:00'
    return (1, datetime.fromisoformat(at).timestamp(), 0, item['id'])


def apply_clock(item, periods):
    if item.get('period_start') is not None:
        first, last = periods.get(item['period_start'], {}), periods.get(item['period_end'], {})
        return {**item, 'at': item['date'] + 'T' + first['start'] + ':00+08:00' if first.get('start') else None,
                'ends_at': item['date'] + 'T' + last['end'] + ':00+08:00' if last.get('end') else None}
    return item


def class_events(data, week_one, periods, adjustments):
    if not week_one:
        return []
    anchor, events = date.fromisoformat(week_one), []
    closed = {item['date'] for item in data['events'] if item.get('source') == 'calendar'}
    for lesson in data['timetable']:
        for week in lesson['weeks']:
            day = anchor + timedelta(days=(week - 1) * 7 + lesson['weekday'] - 1)
            rules = [rule for rule in adjustments if rule['lesson_id'] == lesson['id'] and
                     (rule['on_date'] == day.isoformat() or (rule['scope'] == 'following' and rule['on_date'] <= day.isoformat() <= (rule.get('until_date') or '9999-12-31')))]
            rule = rules[-1] if rules else None
            if day.isoformat() in closed and not (rule and rule['action'] == 'move'):
                continue
            item = apply_clock({**lesson, 'id': lesson['id'] + ':' + day.isoformat(), 'lesson_id': lesson['id'],
                                'event_type': 'class', 'date': day.isoformat(), 'original_date': day.isoformat(),
                                'status': 'scheduled', 'revision': digest([lesson, week_one, rule])}, periods)
            if not rule or rule['action'] == 'restore':
                events.append(item)
                continue
            item.update(adjustment_id=rule['id'], adjustment_scope=rule['scope'], notes=rule.get('notes', ''))
            if rule['action'] != 'move':
                events.append({**item, 'status': rule['action']})
                continue
            change_start = datetime.fromisoformat(rule['starts_at']).astimezone(ZONE) if rule.get('starts_at') else None
            target = change_start.date() if change_start else date.fromisoformat(rule.get('to_date') or rule['on_date'])
            shift = target - date.fromisoformat(rule['on_date'])
            moved_day = day + shift
            moved = {**item, 'id': item['id'] + ':moved', 'status': 'rescheduled', 'date': moved_day.isoformat()}
            if rule.get('location') is not None:
                moved['location'] = rule['location']
            if change_start:
                repeat_shift = day - date.fromisoformat(rule['on_date'])
                moved.update(at=(change_start + repeat_shift).isoformat(), period_start=None, period_end=None,
                             ends_at=(datetime.fromisoformat(rule['ends_at']).astimezone(ZONE) + repeat_shift).isoformat() if rule.get('ends_at') else None)
            else:
                moved.update(period_start=rule.get('period_start') or lesson['period_start'], period_end=rule.get('period_end') or lesson['period_end'])
                moved = apply_clock(moved, periods)
            if all(moved.get(key) == item.get(key) for key in ('date', 'at', 'ends_at', 'period_start', 'period_end')):
                moved['id'] = item['id']
            else:
                events.append({**item, 'status': 'moved', 'moved_to': moved_day.isoformat()})
            events.append(moved)
    return events


def conflicts(days):
    found, incomplete = [], False
    for day in days:
        items = [item for item in day['events'] if item.get('status') not in {'leave', 'cancel', 'moved'}
                 and item.get('event_type') not in {'deadline', 'calendar'} and not item.get('all_day')]
        for index, first in enumerate(items):
            if not first.get('at') or not first.get('ends_at'):
                incomplete = True
            for second in items[index + 1:]:
                if first['id'] == second['id']:
                    continue
                if first.get('period_start') is not None and second.get('period_start') is not None:
                    overlaps = max(first['period_start'], second['period_start']) <= min(first['period_end'], second['period_end'])
                elif all(item.get('at') and item.get('ends_at') for item in (first, second)):
                    overlaps = max(datetime.fromisoformat(first['at']), datetime.fromisoformat(second['at'])) < min(datetime.fromisoformat(first['ends_at']), datetime.fromisoformat(second['ends_at']))
                else:
                    continue
                if overlaps:
                    found.append({'date': day['date'], 'first_id': first['id'], 'first_title': first['title'], 'second_id': second['id'], 'second_title': second['title']})
    return {'items': found, 'complete': not incomplete,
            'message': '部分课程只有节次或安排缺少结束时间，钟点冲突检查不完整。' if incomplete else ''}


def calendar(data, week_start, week_one, adjustments=()):
    start = week_start - timedelta(days=week_start.weekday())
    teaching_week = (start - date.fromisoformat(week_one)).days // 7 + 1 if week_one else None
    period_data = {**data, 'events': data['events'] + list(adjustments)}
    periods = {item['period']: item for item in lesson_periods(period_data)}
    expanded = class_events(data, week_one, periods, adjustments)
    expanded += [apply_clock(dict(item), periods) for item in data['events']]
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        events = []
        for item in expanded:
            first = datetime.fromisoformat(item['at']).astimezone(ZONE).date() if item.get('at') else date.fromisoformat(item['date'])
            last = (datetime.fromisoformat(item['ends_at']).astimezone(ZONE) - timedelta(microseconds=1)).date() if item.get('ends_at') else first
            if first <= day <= last:
                events.append(item)
        events.sort(key=event_order)
        days.append({'date': day.isoformat(), 'events': events})
    return {'week_start': start.isoformat(), 'week_end': (start + timedelta(days=6)).isoformat(),
            'week_one': week_one, 'teaching_week': teaching_week, 'periods': list(periods.values()), 'days': days, 'conflicts': conflicts(days)}
