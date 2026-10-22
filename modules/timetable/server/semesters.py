"""Select an actual semester, not the portal's remembered dropdown choice."""
import re
from datetime import date

from backend.services.campus import SourceError

SEASONS = {'1': ('fall', '秋季'), '2': ('spring', '春季'), '3': ('summer', '夏季')}


def select_semester(catalog, today, term_starts=None):
    entries = {}
    for entry in re.findall(r'\{[^{}]*\}', catalog):
        identifier = re.search(r'\bid\s*:\s*(\d+)\b', entry)
        year = re.search(r'\bschoolYear\s*:\s*[\'\"](20\d{2})-(20\d{2})[\'\"]', entry)
        name = re.search(r'\bname\s*:\s*[\'\"]([123])[\'\"]', entry)
        if identifier and year and name and int(year[2]) == int(year[1]) + 1:
            season, label = SEASONS[name[1]]
            entries[year[1] + '-' + season] = (identifier[1], year[1] + '-' + year[2] + '学年' + label)
    expected = expected_semester(today, term_starts)
    if expected not in entries:
        raise SourceError('教务学期目录尚未提供当前学期，已保留上次课表，请稍后同步。')
    return entries[expected]


def expected_semester(today, term_starts=None):
    year = today.year if today.month >= 9 else today.year - 1
    season = 'fall' if today.month >= 9 or today.month == 1 else 'spring' if today.month <= 6 else 'summer'
    expected = str(year) + '-' + season
    starts = {}
    for key, value in (term_starts or {}).items():
        try:
            starts[key] = date.fromisoformat(value['week_one'])
        except (KeyError, TypeError, ValueError):
            continue
    # A matching year's official calendar resolves winter/summer boundaries.
    # An old calendar alone must not pin a new academic year to last summer.
    if expected in starts:
        begun = [key for key, start in starts.items() if start <= today]
        if begun:
            expected = max(begun, key=starts.get)
    return expected
