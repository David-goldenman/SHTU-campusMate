"""Ground activity times in cached mail text, independently of participation needs."""
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
DATES = r'(?:(20\d{2})[年/.-])?(\d{1,2})[月/.-](\d{1,2})日?'
CLOCKS = r'(?<!\d)(\d{1,2})[:：点](\d{2})?'


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        return result.astimezone(ZONE) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def event_window(item, classification):
    event = classification.get('event') or {}
    if classification.get('review_pending') or not classification.get('fingerprint') or event.get('event_type') not in {'activity', 'lecture', 'presentation', 'quiz'}:
        return None
    if classification.get('input_revision', classification['fingerprint']) != classification['fingerprint']:
        return None
    start, end = instant(event.get('starts_at')), instant(event.get('ends_at'))
    if not start or event.get('ends_at') and (not end or end <= start):
        return None
    compact = lambda value: re.sub(r'\s+', '', value or '')
    quote, text = compact(event.get('quote')), compact(item.get('body_text'))
    if not quote or quote not in text:
        return None
    # Keep separate activity clauses, but never use a registration/deadline clause.
    dated = re.sub(r'(?<=\d)\s+(?=[年月日:：/.-]|\d)|(?<=[年月日:：/.-])\s+(?=\d)', '', event['quote'])
    quote = compact('\n'.join(part for part in re.split(r'[。；;\n]', dated)
                    if not re.search(r'报名|问卷|调查|反馈|申请|提交|截止|deadline|survey|registration', part, re.I)))
    if not quote:
        return None
    received = instant(item.get('received_at'))
    def dates(value):
        found = []
        for year, month, day in re.findall(DATES, value):
            try:
                found.append(datetime(int(year or (received.year if received else 0)), int(month), int(day), tzinfo=ZONE).date())
            except ValueError:
                pass
        return found
    clocks = {(int(hour), int(minute or 0)) for hour, minute in re.findall(CLOCKS, quote)}
    if start.date() not in dates(quote) or (start.hour, start.minute) not in clocks:
        return None
    if end and ((end.hour, end.minute) not in clocks or end.date() != start.date() and end.date() not in dates(quote)):
        return None
    # Do not clear a whole mail that also contains a later dated obligation/activity.
    if any(day > (end or start).date() for day in dates(text)):
        return None
    expiry = end
    basis = 'event_end'
    all_clocks = {(int(hour), int(minute or 0)) for hour, minute in re.findall(CLOCKS, text)}
    if not end or any(clock > (end.hour, end.minute) and clock[0] < 24 and clock[1] < 60 for clock in all_clocks):
        expiry = datetime.combine((end or start).date() + timedelta(days=1), time.min, ZONE)
        basis = 'event_day_end'
    return {'starts_at': start.isoformat(), 'ends_at': end.isoformat() if end else None,
            'expires_at': expiry.isoformat(), 'basis': basis, 'source_revision': classification.get('input_revision') or classification['fingerprint']}
