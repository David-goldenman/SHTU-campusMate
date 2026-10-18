"""Export the timetable's four-week course and homework window as iCalendar."""
from datetime import date, datetime, timedelta, timezone
import hashlib

from .calendar import ZONE

FILENAME = 'shanghaitech-timetable-4-weeks.ics'


def _escape(value):
    return str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace(
        '\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')


def _fold(line):
    """Fold an iCalendar content line to 75 UTF-8 octets per physical line."""
    if len(line.encode('utf-8')) <= 75:
        return line
    chunks, chunk, size, limit = [], '', 0, 75
    for character in line:
        width = len(character.encode('utf-8'))
        if size + width > limit:
            chunks.append(chunk)
            chunk, size, limit = '', 0, 74  # Continuation lines start with one space.
        chunk += character
        size += width
    chunks.append(chunk)
    return '\r\n '.join(chunks)


def _moment(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZONE)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _utc(value):
    return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _identity(kind, item):
    digest = hashlib.sha256(('timetable:' + kind + ':' + str(item.get('id', ''))).encode('utf-8')).hexdigest()
    return digest[:40] + '@shanghaitech.local'


def _description(parts):
    return '\\n'.join(_escape(part) for part in parts if part)


def _class_event(item, stamp):
    status = item.get('status')
    if status in {'leave', 'cancel', 'moved'}:
        return []
    start = _moment(item.get('at'))
    end = _moment(item.get('ends_at'))
    lines = ['BEGIN:VEVENT', 'UID:' + _identity('class', item), 'DTSTAMP:' + stamp,
             'LAST-MODIFIED:' + stamp, 'SEQUENCE:0', 'CLASS:PUBLIC',
             'SUMMARY:' + _escape(item.get('title', '课程')), 'CATEGORIES:课程']
    if start:
        if not end or end <= start:
            end = start + timedelta(minutes=45)
        lines += ['DTSTART:' + _utc(start), 'DTEND:' + _utc(end)]
    else:
        try:
            day = date.fromisoformat(item.get('date', ''))
        except (TypeError, ValueError):
            return []
        lines += ['DTSTART;VALUE=DATE:' + day.strftime('%Y%m%d'),
                  'DTEND;VALUE=DATE:' + (day + timedelta(days=1)).strftime('%Y%m%d')]
    if item.get('location'):
        lines.append('LOCATION:' + _escape(item['location']))
    details = [item.get('course_title'), item.get('teacher'), item.get('department')]
    if item.get('period_start') is not None:
        details.append('第 %s–%s 节' % (item['period_start'], item['period_end']))
    if item.get('notes'):
        details.append(item['notes'])
    if status == 'rescheduled':
        details.append('此课程已由时间表中的调课记录移动。')
    if not start:
        details.append('具体钟点尚未同步，请以教务系统为准。')
    if details:
        lines.append('DESCRIPTION:' + _description(details))
    lines += ['STATUS:CONFIRMED', 'END:VEVENT']
    return lines


def _deadline_event(item, stamp):
    due = _moment(item.get('due_at') or item.get('at'))
    if not due:
        return []
    begin = due - timedelta(minutes=30)
    details = [item.get('course_title'), item.get('platform') and '提交平台：' + item['platform'],
               item.get('url')]
    lines = ['BEGIN:VEVENT', 'UID:' + _identity('deadline', item), 'DTSTAMP:' + stamp,
             'LAST-MODIFIED:' + stamp, 'SEQUENCE:0', 'CLASS:PUBLIC',
             'SUMMARY:' + _escape('作业截止：' + str(item.get('title', ''))), 'CATEGORIES:作业',
             'DTSTART:' + _utc(begin), 'DTEND:' + _utc(due)]
    if item.get('url') and str(item['url']).startswith(('http://', 'https://')):
        lines.append('URL:' + str(item['url']).replace('\r', '').replace('\n', ''))
    if details:
        lines.append('DESCRIPTION:' + _description(details))
    lines += ['STATUS:CONFIRMED',
              'BEGIN:VALARM', 'TRIGGER:-PT30M', 'ACTION:DISPLAY',
              'DESCRIPTION:' + _escape('作业即将截止：' + str(item.get('title', ''))), 'END:VALARM',
              'END:VEVENT']
    return lines


def build_calendar(schedule, now=None):
    """Build an importable calendar from a /schedule response."""
    moment = now or datetime.now(ZONE)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZONE)
    stamp = _utc(moment)
    overview = schedule.get('overview') or {}
    window = '至'.join(value for value in (overview.get('start'), overview.get('end')) if value)
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ShanghaiTech//Campus Timetable 1.0//ZH',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
             'X-WR-CALNAME:' + _escape('上海科技大学 · 近四周课程与作业'),
             'X-WR-CALDESC:' + _escape('课程课表与作业截止' + ('（' + window + '）' if window else '')),
             'X-WR-TIMEZONE:Asia/Shanghai']
    seen = set()
    for week in overview.get('weeks') or []:
        for day in week.get('days') or []:
            for item in day.get('events') or []:
                kind = item.get('event_type')
                if kind not in {'class', 'deadline'}:
                    continue
                identity = (kind, item.get('id'))
                if identity in seen:
                    continue
                seen.add(identity)
                lines.extend(_class_event(item, stamp) if kind == 'class' else _deadline_event(item, stamp))
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'
