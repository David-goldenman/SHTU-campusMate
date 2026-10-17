import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

package = load('assignments')
data = {'courses':[{'id':'group:1','title':'合成课程','current':True,'course_ids':['gradescope:c']},{'id':'group:2','title':'历史课程','current':False,'course_ids':['blackboard:old']}], 'assignments':[
    {'id':'gradescope:open','source':'gradescope','course_id':'gradescope:c','actionable':True,'submitted':False,'due_at':'2026-10-01T00:00:00+08:00'},
    {'id':'gradescope:unknown','source':'gradescope','course_id':'gradescope:c','actionable':True,'submitted':None},
    {'id':'gradescope:closed','source':'gradescope','course_id':'gradescope:c','actionable':False,'submitted':False},
    {'id':'blackboard:old','source':'blackboard','course_id':'blackboard:old','actionable':True,'submitted':False},
]}
values = package.arrange(data,datetime(2026,10,16,tzinfo=timezone.utc))
assert [item['id'] for item in values if item['pending']] == ['gradescope:open']
assert next(item for item in values if item['pending'])['overdue'] is True
assert next(item for item in values if item['id'] == 'gradescope:unknown')['submitted'] is None
assert package.summary(values) == {'total': 4, 'unsubmitted': 3, 'pending': 1,
                                  'by_source': {'blackboard': {'total': 1, 'unsubmitted': 1, 'pending': 0},
                                                'gradescope': {'total': 3, 'unsubmitted': 2, 'pending': 1}}}
late = {'courses': [{'id': 'group:current', 'title': '本学期课程', 'current': True, 'course_ids': ['blackboard:c']}],
        'assignments': [{'id': 'blackboard:' + name, 'source': 'blackboard', 'course_id': 'blackboard:c', 'submitted': False, 'actionable': True, 'due_at': due}
                        for name, due in [('late', '2026-09-30T23:30:00+08:00'), ('no-date', None)]]}
late_values = package.arrange(late, datetime(2026, 10, 17, tzinfo=timezone.utc))
assert all(item['pending'] for item in late_values)
assert package.summary(late_values)['pending'] == 2
print('assignments: current-course scope, explicit submission capability, unknown states and late-open tasks passed')
