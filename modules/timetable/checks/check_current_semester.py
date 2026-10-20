"""A remembered portal semester must not hide the current assignment list."""
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError
from backend.services.campus.data import validate_bundle

module = load('timetable')
catalog = '''{semesters:{y0:[{id:264,schoolYear:"2025-2026",name:"3"}],
    y1:[{id:282,schoolYear:"2026-2027",name:"1"},{id:283,schoolYear:"2026-2027",name:"2"},
        {id:302,schoolYear:"2026-2027",name:"3"}]},semesterId:"264"}'''


class Portal:
    selected = None

    def request(self, method, url, **options):
        if url.endswith('/courseTableForStd.action'):
            text = 'addInput(form,"ids","123"); semesterCalendar({value:"264"});'
        elif url.endswith('/dataQuery.action'):
            text = catalog
        else:
            assert url.endswith('/courseTableForStd!courseTable.action')
            self.selected = options['data']['semester.id']
            text = '''<tr><td>CS100</td><td><a class="cs-detail-link" data-course-id="7">Synthetic course</a></td></tr>
                <script>var table = new CourseTable(2026,91); var unitCount=13;table.marshalTable(38,1,18);</script>'''
        return SimpleNamespace(text=text)


class October(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 18, tzinfo=tz)


portal = Portal()
with patch.dict(module.fetch.__globals__, datetime=October):
    result = module.fetch(portal, {})
assert portal.selected == '282', 'A portal remembered on summer must request the current fall semester'
assert result['metadata']['semester'] == '2026-2027学年秋季'

select = module.fetch.__globals__['select_semester']
assert select(catalog, date(2027, 1, 10))[0] == '282'
assert select(catalog, date(2027, 3, 10))[0] == '283'
assert select(catalog, date(2027, 7, 10))[0] == '302'
starts = {'2025-summer': {'week_one': '2026-06-22'}, '2026-fall': {'week_one': '2026-09-14'},
          '2026-spring': {'week_one': '2027-02-15'}, '2026-summer': {'week_one': '2027-06-21'}}
assert select(catalog, date(2026, 9, 13), starts)[0] == '264'
assert select(catalog, date(2026, 9, 14), starts)[0] == '282'
assert select(catalog, date(2027, 2, 14), starts)[0] == '282'
assert select(catalog, date(2027, 2, 15), starts)[0] == '283'
assert select(catalog, date(2027, 6, 21), starts)[0] == '302'
try:
    select(catalog, date(2028, 10, 18))
    raise AssertionError('Do not fall back to a historical portal choice when the current term is absent')
except SourceError:
    pass

# Confirm the corrected source metadata keeps the active course and task visible.
courses, assignments = load('courses'), load('assignments')
snapshot = {'status': 'ready', 'data': validate_bundle(result)}
assignment_source = {'status': 'ready', 'data': validate_bundle({'courses': [{
    'id': 'gradescope:course', 'source': 'gradescope', 'title': 'Synthetic course', 'code': 'CS100', 'term': 'Fall 2026'}],
    'assignments': [{'id': 'gradescope:task', 'source': 'gradescope', 'course_id': 'gradescope:course',
                     'title': 'Open task', 'due_at': '2026-10-20T23:59:00+08:00', 'submitted': False, 'availability': 'open'}]})}
sources = {'timetable': snapshot, 'gradescope': assignment_source}
combined = courses.combine(sources, [], courses.current_semester(sources))
items = assignments.arrange(combined, now=datetime.fromisoformat('2026-10-18T12:00:00+08:00'))
assert len(items) == 1 and items[0]['current'] and items[0]['pending']
print('PASS: current semester selection and assignment visibility')
