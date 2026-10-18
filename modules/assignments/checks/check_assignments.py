import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus.assignments import filter_issues

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
assert items['blackboard:old']['category'] == 'ended' and items['blackboard:old']['pending'] is False
assert {item['id'] for item in values if item['pending']} == {'gradescope:late','gradescope:future','gradescope:unknown','gradescope:legacy-open'}
assert package.counts(values) == {'pending':3,'late':1,'graded':1,'completed':1,'ended':3}
counts = package.summary(values)
assert (counts['total'], counts['unsubmitted'], counts['pending'], counts['needs_review']) == (9, 6, 4, 1)
assert {key: counts['by_source']['blackboard'][key] for key in ('total', 'unsubmitted', 'pending')} == {'total': 1, 'unsubmitted': 1, 'pending': 0}
assert {key: counts['by_source']['gradescope'][key] for key in ('total', 'unsubmitted', 'pending')} == {'total': 8, 'unsubmitted': 5, 'pending': 4}
before = {'metadata': {'current_semester': '2026-fall', 'source_metadata': {'elrc': {'semester': {'startTime': '2026-09-13T16:00:00.000+00:00'}}}},
          'courses': [{'id': 'group:current', 'title': '本学期课程', 'current': True, 'term': '2026-fall', 'course_ids': ['blackboard:c']}],
          'assignments': [
              {'id': 'blackboard:old-due', 'source': 'blackboard', 'course_id': 'blackboard:c', 'title': '旧作业',
               'availability': 'open', 'actionable': True, 'submitted': False, 'due_at': '2026-09-13T23:59:00+08:00'},
              {'id': 'blackboard:new-due', 'source': 'blackboard', 'course_id': 'blackboard:c', 'title': '新作业',
               'availability': 'open', 'actionable': True, 'submitted': False, 'due_at': '2026-10-20T23:59:00+08:00'}]}
before_values = {item['id']: item for item in package.arrange(before, datetime(2026, 10, 17, tzinfo=timezone.utc))}
assert before_values['blackboard:old-due']['category'] == 'ended' and not before_values['blackboard:old-due']['pending']
assert before_values['blackboard:new-due']['category'] == 'pending' and before_values['blackboard:new-due']['pending']
assert filter_issues(['旧作业 的提交情况本次未能核实，请查看记录说明。', '新作业 的提交情况本次未能核实，请查看记录说明。'],
                     before['assignments'], before['courses'], '2026-fall', '2026-09-14') == ['新作业 的提交情况本次未能核实，请查看记录说明。']
missing = {'metadata': {'current_semester': '2026-fall', 'source_metadata': {'elrc': {'semester': {'startTime': '2026-09-13T16:00:00.000+00:00'}}}},
           'courses': [{'id': 'group:current', 'title': '本学期课程', 'current': True, 'term': '2026-fall', 'course_ids': ['blackboard:c']}],
           'assignments': [{'id': 'blackboard:no-date', 'source': 'blackboard', 'course_id': 'blackboard:c', 'title': '无截止时间',
                            'availability': 'open', 'actionable': True, 'submitted': False}]}
assert package.default_due(missing['metadata']) == '2027-01-17T23:59:00+08:00'
fallback = package.arrange(missing, datetime(2026, 10, 17, tzinfo=timezone.utc))[0]
assert (fallback['category'], fallback['due_default'], fallback['due_source']) == ('pending', True, 'default')
assert fallback['due_at'] == '2027-01-17T23:59:00+08:00' and fallback['pending']
manual = package.arrange(missing, datetime(2026, 10, 17, tzinfo=timezone.utc),
                         dues={'blackboard:no-date': '2026-10-01T23:59:00+08:00'})[0]
assert (manual['category'], manual['due_default'], manual['due_source']) == ('late', False, 'manual')
assert package.default_due({}) is None, 'Without a semester start there is no invented deadline'
ordered = package.arrange(data,datetime(2026,10,16,tzinfo=timezone.utc),{'pending':['gradescope:unknown','gradescope:future'],'late':['gradescope:late']})
pending = [item['id'] for item in ordered if item['category'] == 'pending']
assert pending[:2] == ['gradescope:unknown','gradescope:future'] and pending[-1:] == ['gradescope:legacy-open']
assert [item['id'] for item in ordered if item['category'] == 'late'] == ['gradescope:late']
assert package.apply_order(values,{'pending':['missing']}) == values, 'Unknown saved IDs must not hide newly synced work'
late = {'courses': [{'id': 'group:current', 'title': '本学期课程', 'current': True, 'course_ids': ['blackboard:c']}],
        'assignments': [{'id': 'blackboard:' + name, 'source': 'blackboard', 'course_id': 'blackboard:c', 'submitted': False, 'actionable': True, 'due_at': due}
                        for name, due in [('late', '2026-09-30T23:30:00+08:00'), ('no-date', None)]]}
late_values = package.arrange(late, datetime(2026, 10, 17, tzinfo=timezone.utc))
assert all(item['pending'] for item in late_values)
assert package.summary(late_values)['pending'] == 2
states = {'courses': late['courses'], 'metadata': {'source_metadata': {'blackboard': {'status': 'ready'}}}, 'assignments': [
    {'id': 'blackboard:' + status, 'source': 'blackboard', 'course_id': 'blackboard:c', 'submitted': submitted,
     'submission_status': status, 'actionable': True, 'local_status': 'done'}
    for status, submitted in [('not_submitted', False), ('draft', False), ('submitted', True), ('needs_grading', True),
                              ('graded', True), ('exempt', False), ('unknown', None)]]}
state_values = package.arrange(states)
assert {item['submission_status'] for item in state_values if item['pending']} == {'not_submitted', 'draft', 'unknown'}
assert package.summary(state_values)['unsubmitted'] == 2
assert package.summary(state_values)['needs_review'] == 1
assert all(value == 1 for value in package.summary(state_values)['submission_states'].values())
mixed = package.summary(state_values + [item for item in values if item['source'] == 'gradescope'])
blackboard = mixed['by_source']['blackboard']
gradescope = mixed['by_source']['gradescope']
assert mixed['total'] == 15 and blackboard['total'] == 7 and gradescope['total'] == 8
assert all(count == 1 for count in blackboard['submission_states'].values()), 'Every Blackboard state remains distinct from other sources'
assert gradescope['submission_states']['not_submitted'] == 5 and gradescope['submission_states']['unknown'] == 1
assert gradescope['submission_states']['submitted'] == 1 and gradescope['submission_states']['graded'] == 1 and gradescope['needs_review'] == 1
assert sum(blackboard['submission_states'][state] for state in ('submitted', 'needs_grading', 'graded')) == 3
assert all(sum(counts['submission_states'].values()) == counts['total'] for counts in [mixed, blackboard, gradescope])
states['metadata']['source_metadata']['blackboard']['status'] = 'error'
cached_values = package.arrange(states)
assert all(item['needs_review'] and item['source_stale'] for item in cached_values)
assert package.summary(cached_values)['pending'] == 3, 'Last known counts remain visible but explicitly need review'
catalog = sys.modules[load('courses').__name__ + '.catalog']
assert {item['id'] for item in catalog.query(states, 'assignments', current=True, pending=True)} == {'blackboard:not_submitted', 'blackboard:draft'}, 'Catalog pending keeps the documented stricter filter that excludes unknown submission states'
print('assignments: five states, zero scores, week-18 fallback deadlines, manual due overrides, current-course scope, saved drag order and submission evidence passed')
