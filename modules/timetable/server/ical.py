"""Export four weeks of homework or the whole semester's courses as iCalendar."""
from datetime import date, datetime, timedelta, timezone
import hashlib

from .calendar import ZONE, class_events, lesson_periods
from .homework import PLATFORMS

HOMEWORK_FILENAME = 'shanghaitech-homework-4-weeks.ics'
COURSE_FILENAME = 'shanghaitech-courses-semester.ics'


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


def _identity(kind, value):
    digest = hashlib.sha256(('timetable:' + kind + ':' + str(value)).encode('utf-8')).hexdigest()
    return digest[:40] + '@shanghaitech.local'


def _description(parts):
    return '\\n'.join(_escape(part) for part in parts if part)


def _class_event(item, stamp):
    status = item.get('status')
    if status in {'leave', 'cancel', 'moved'}:
        return []
    start = _moment(item.get('at'))
    end = _moment(item.get('ends_at'))
    lines = ['BEGIN:VEVENT', 'UID:' + _identity('class', item.get('id', '')), 'DTSTAMP:' + stamp,
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


def _homework_event(item, stamp):
    due = _moment(item.get('due_at') or item.get('at'))
    if not due:
        return []
    begin = due - timedelta(minutes=30)
    platform = PLATFORMS.get(item.get('source'), item.get('source') or '作业平台')
    details = [item.get('course_title'), '迟交' if item.get('late') else None, item.get('url')]
    lines = ['BEGIN:VEVENT',
             'UID:' + _identity('homework', str(item.get('source', '')) + ':' + str(item.get('id', ''))),
             'DTSTAMP:' + stamp, 'LAST-MODIFIED:' + stamp, 'SEQUENCE:0', 'CLASS:PUBLIC',
             'SUMMARY:' + _escape('作业截止：' + str(item.get('title', ''))), 'CATEGORIES:作业',
             'DTSTART:' + _utc(begin), 'DTEND:' + _utc(due),
             'LOCATION:' + _escape(platform)]
    if item.get('url') and str(item['url']).startswith(('http://', 'https://')):
        lines.append('URL:' + str(item['url']).replace('\r', '').replace('\n', ''))
    if details:
        lines.append('DESCRIPTION:' + _description(details))
    lines += ['STATUS:CONFIRMED',
              'BEGIN:VALARM', 'TRIGGER:-PT30M', 'ACTION:DISPLAY',
              'DESCRIPTION:' + _escape('作业即将截止：' + str(item.get('title', ''))), 'END:VALARM',
              'END:VEVENT']
    return lines


def _render(name, description, stamp, events):
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ShanghaiTech//Campus Timetable 1.1//ZH',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
             'X-WR-CALNAME:' + _escape(name),
             'X-WR-CALDESC:' + _escape(description),
             'X-WR-TIMEZONE:Asia/Shanghai']
    lines.extend(events)
    lines.append('END:VCALENDAR')
    return '\r\n'.join(_fold(line) for line in lines) + '\r\n'


def _at(value):
    moment = value or datetime.now(ZONE)
    return moment if moment.tzinfo else moment.replace(tzinfo=ZONE)


def build_homework_calendar(schedule, now=None):
    """Build an importable calendar containing only the four-week homework window."""
    moment = _at(now)
    stamp = _utc(moment)
    homework = schedule.get('homework') or {}
    window = '至'.join(value for value in (homework.get('start'), homework.get('end')) if value)
    events, seen = [], set()
    for item in homework.get('items') or []:
        identity = (item.get('source'), item.get('id'))
        if identity in seen:
            continue
        seen.add(identity)
        events.extend(_homework_event(item, stamp))
    description = '近四周待交与迟交作业截止，地点为提交平台' + ('（' + window + '）' if window else '')
    return _render('上海科技大学 · 近四周作业', description, stamp, events)


def build_course_calendar(schedule, now=None):
    """Build an importable calendar containing every class in the current semester."""
    moment = _at(now)
    stamp = _utc(moment)
    data = schedule.get('data') or {}
    week_one = (schedule.get('calendar') or {}).get('week_one')
    events, seen = [], set()
    if week_one:
        periods = {item['period']: item for item in lesson_periods(data)}
        for item in class_events(data, week_one, periods, schedule.get('adjustments') or []):
            if item.get('id') in seen:
                continue
            seen.add(item.get('id'))
            events.extend(_class_event(item, stamp))
    semester = (data.get('metadata') or {}).get('semester') or ''
    description = '本学期全部课程时间与地点' + ('（' + semester + '）' if semester else '')
    return _render('上海科技大学 · 本学期课程', description, stamp, events)
