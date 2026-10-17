import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

package = load('assignments')
data = {'courses':[{'id':'group:1','title':'合成课程','current':True,'course_ids':['gradescope:c']},{'id':'group:2','title':'历史课程','current':False,'course_ids':['blackboard:old']}], 'assignments':[
    {'id':'gradescope:late','source':'gradescope','course_id':'gradescope:c','availability':'open','actionable':True,'submitted':False,'due_at':'2026-10-01T00:00:00+08:00'},
    {'id':'gradescope:future','source':'gradescope','course_id':'gradescope:c','availability':'open','actionable':True,'submitted':False,'due_at':'2026-10-23T22:00:00+08:00'},
    {'id':'gradescope:unknown','source':'gradescope','course_id':'gradescope:c','availability':'open','actionable':True,'submitted':None},
    {'id':'gradescope:closed','source':'gradescope','course_id':'gradescope:c','availability':'closed','actionable':False,'submitted':False},
    {'id':'gradescope:unknown-state','source':'gradescope','course_id':'gradescope:c','availability':'unknown','actionable':None,'submitted':False},
    {'id':'gradescope:graded','source':'gradescope','course_id':'gradescope:c','availability':'closed','actionable':False,'submitted':True,'score':0,'max_score':10},
    {'id':'gradescope:completed','source':'gradescope','course_id':'gradescope:c','availability':'closed','actionable':False,'submitted':True,'score':None},
    {'id':'blackboard:old','source':'blackboard','course_id':'blackboard:old','availability':'open','actionable':True,'submitted':False},
    {'id':'gradescope:legacy-open','source':'gradescope','course_id':'gradescope:c','actionable':True,'submitted':False,'due_at':'2026-10-30T22:00:00+08:00'},
]}
values = package.arrange(data,datetime(2026,10,16,tzinfo=timezone.utc))
items = {item['id']:item for item in values}
assert items['gradescope:late']['category'] == 'late' and items['gradescope:late']['overdue'] is True
assert items['gradescope:future']['category'] == 'pending'
assert items['gradescope:legacy-open']['category'] == 'pending'
assert items['gradescope:unknown']['category'] == 'pending' and items['gradescope:unknown']['submitted'] is None
assert items['gradescope:closed']['category'] == 'ended'
assert items['gradescope:unknown-state']['category'] == 'ended'
assert items['gradescope:graded']['category'] == 'graded' and items['gradescope:graded']['score'] == 0
assert items['gradescope:completed']['category'] == 'completed'
assert items['blackboard:old']['category'] == 'pending' and items['blackboard:old']['pending'] is False
assert {item['id'] for item in values if item['pending']} == {'gradescope:late','gradescope:future','gradescope:unknown','gradescope:legacy-open'}
assert package.counts(values) == {'pending':4,'late':1,'graded':1,'completed':1,'ended':2}
ordered = package.arrange(data,datetime(2026,10,16,tzinfo=timezone.utc),{'pending':['gradescope:unknown','gradescope:future'],'late':['gradescope:late']})
pending = [item['id'] for item in ordered if item['category'] == 'pending']
assert pending[:2] == ['gradescope:unknown','gradescope:future'] and pending[-2:] == ['gradescope:legacy-open','blackboard:old']
assert [item['id'] for item in ordered if item['category'] == 'late'] == ['gradescope:late']
assert package.apply_order(values,{'pending':['missing']}) == values, 'Unknown saved IDs must not hide newly synced work'
print('assignments: five states, zero scores, unconfirmed open work, current-course scope and saved drag order passed')
