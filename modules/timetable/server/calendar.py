from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field, model_validator

ZONE = ZoneInfo('Asia/Shanghai')


class SemesterSettings(BaseModel):
    week_one: date

    @model_validator(mode='after')
    def monday(self):
        if self.week_one.weekday() != 0:
            raise ValueError('第 1 教学周的起始日期应为周一。')
        return self


class Event(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    event_type: Literal['quiz', 'presentation', 'activity', 'lecture']
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    location: str = Field(default='', max_length=200)
    course_title: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def interval(self):
        if not self.title.strip() or (self.ends_at and self.ends_at <= self.starts_at):
            raise ValueError('请填写事项名称，结束时间须晚于开始时间。')
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
    numbers = [metadata.get('units', 0), *clocks, *(item['period_end'] for item in data['timetable'])]
    count = max((value for value in numbers if type(value) is int and 1 <= value <= 30), default=0)
    return [clocks.get(number, {'period': number, 'start': None, 'end': None}) for number in range(1, count + 1)]


def event_order(item):
    if item.get('event_type') == 'class':
        return (0, item['period_start'], item['period_end'], item['id'])
    return (1, datetime.fromisoformat(item['at']).timestamp(), 0, item['id'])


def calendar(data, week_start, week_one):
    start = week_start - timedelta(days=week_start.weekday())
    teaching_week = (start - date.fromisoformat(week_one)).days // 7 + 1 if week_one else None
    periods = {item['period']: item for item in lesson_periods(data)}
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        events = []
        closed = any(item.get('source') == 'calendar' and item.get('date') == day.isoformat() for item in data['events'])
        for item in data['timetable']:
            if closed or teaching_week not in item['weeks'] or item['weekday'] != offset + 1:
                continue
            first, last = periods.get(item['period_start']), periods.get(item['period_end'])
            at = day.isoformat() + 'T' + first['start'] + ':00+08:00' if first and first['start'] else None
            end = day.isoformat() + 'T' + last['end'] + ':00+08:00' if last and last['end'] else None
            events.append({**item, 'id': item['id'] + ':' + day.isoformat(), 'event_type': 'class', 'date': day.isoformat(), 'at': at, 'ends_at': end})
        for item in data['events']:
            first = datetime.fromisoformat(item['at']).astimezone(ZONE).date()
            last = datetime.fromisoformat(item['ends_at']).astimezone(ZONE).date() if item.get('ends_at') else first
            if first <= day <= last:
                events.append(item)
        events.sort(key=event_order)
        days.append({'date': day.isoformat(), 'events': events})
    return {'week_start': start.isoformat(), 'week_end': (start + timedelta(days=6)).isoformat(),
            'week_one': week_one, 'teaching_week': teaching_week, 'periods': list(periods.values()), 'days': days}
