"""Keep semester timetables; only dynamic study information needs frequent refreshes."""
import asyncio
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from backend.services.campus import Source, semester
from backend.services.campus.source import snapshots
from .school_calendar import ZONE, term_key
from .semesters import expected_semester


def term_starts(context):
    year = datetime.now(ZONE).year
    return {key: value for start in (year - 1, year)
            for key, value in context.store.read('school-calendar:' + str(start), {}).get('terms', {}).items()}


class SavedTimetable(Source):
    def __init__(self, *args, **kwargs):
        self.verification_lock = asyncio.Lock()
        super().__init__(*args, **kwargs)

    def _is_stale(self, saved):
        # A semester change, rather than elapsed hours, invalidates the timetable.
        key = term_key(saved.get('data', {}).get('metadata', {}))
        return bool(saved.get('updated_at') and key and key !=
                    expected_semester(datetime.now(ZONE).date(), term_starts(self.context)))

    def sync(self, force: bool = False):
        with self.lock:
            if self.cancelled.is_set():
                raise HTTPException(409, '模块正在停止。')
            saved = self.context.store.read(self.snapshot_key, {})
            if (not force and saved.get('owner') == self.owner() and saved.get('updated_at')
                    and not self._is_stale(saved)):
                state = self.context.store.read(self.sync_key, {})
                return {'queued': False, 'status': state.get('status', 'ready'), 'reused': True}
            return super().sync()


def code(value):
    return re.sub(r'[\s_-]', '', str(value or '')).upper()


async def verify_saved(context, source, saved):
    """Persist one comparison per saved timetable; never force other sources to sync."""
    async with source.verification_lock:
        return await _verify_saved(context, source, saved)


async def _verify_saved(context, source, saved):
    updated = saved.get('updated_at')
    owner = source.owner()
    data = saved['data']
    key = 'timetable-verification:' + owner + ':' + str(term_key(data['metadata']))
    previous = context.store.read(key, {})
    if previous.get('timetable_updated_at') == updated and updated:
        return previous
    if not updated:
        return {'status': 'unavailable', 'checked_at': None, 'courses': []}
    values, unavailable = await snapshots(context, ('elrc', 'ecourse'))
    if owner != source.owner() or updated != source.snapshot().get('updated_at'):
        raise HTTPException(409, '账号或课表已更新，请重新读取时间表。')
    term = semester(data['metadata'].get('semester'))
    known = {name: {code(item.get('code')) for item in value['data']['courses']
                    if semester(item.get('term') or item.get('semester')) == term and code(item.get('code'))}
             for name, value in values.items() if value.get('status') == 'ready'}
    rows = [{'id': item['id'], 'code': item.get('code', ''),
             'sources': [name for name, codes in known.items() if code(item.get('code')) in codes]}
            for item in data['courses']]
    confirmed = sum(bool(row['sources']) for row in rows)
    result = {'status': 'verified' if rows and confirmed == len(rows) else 'partial',
              'timetable_updated_at': updated, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'courses': rows, 'confirmed': confirmed, 'total': len(rows),
              'sources': list(known), 'unavailable': unavailable,
              'scope': '仅核对课程代码与学期；节次、教室和教师以已保存的教务课表为准。'}
    # An unavailable or still-loading peer is not a completed comparison.
    # Keep checking its local snapshot until one usable peer exists, without a POST.
    if known:
        context.store.write(key, result)
    return result
