import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError

package = load('blackboard')
rules = sys.modules[package.__name__ + '.submission']
reader = sys.modules[package.__name__ + '.reader']
assert reader.grade_values({'score': 'unavailable', 'grading': None}, {'displayGrade': []}) == {'score': None, 'max_score': None, 'due_at': None}
assert reader.grade_values({}, {'displayGrade': {'score': float('nan')}})['score'] is None
NOW = '2026-10-17T10:00:00+00:00'
HISTORY = '''<span id="pageTitleText">复查提交历史记录: 合成报告</span>
<div id="assignmentInfo"><h3>截止日期</h3><p>2026年9月30日 下午11:30</p></div>
<div id="currentAttempt"><div class="attemptHeader"><span class="dateStamp">26-9-30 下午3:12</span></div>
<span id="currentAttempt_pointsPossible">/100</span>
<div id="currentAttempt_submission"><h4>提交</h4><ul><li>synthetic.pdf</li></ul></div></div>'''
UPLOAD = '<span id="pageTitleText">上载作业：合成作业</span><form id="uploadAssignmentFormId"></form>'


def failed():
    raise SourceError('synthetic unavailable')


def no_request():
    raise AssertionError('Definite evidence does not need extra requests')


history = rules.decide({}, None, lambda: HISTORY, {}, NOW)
assert history['submitted'] is True and history['submission_status'] == 'submitted'
assert history['submitted_at'] == '2026-09-30T15:12:00+08:00'
assert history['due_at'] == '2026-09-30T23:30:00+08:00' and history['max_score'] == 100
assert history['checked_at'] == NOW
assert rules.history_time('2026年9月30日 上午12:00').endswith('T00:00:00+08:00')
assert rules.history_time('2026年9月30日 下午12:00').endswith('T12:00:00+08:00')
for bad in ('2026-09-30', '2026年9月31日 下午3:00', '09/30/2026 3:00', '截止今晚'):
    assert rules.history_time(bad) is None

for grade, expected in [({'status': 'NeedsGrading'}, 'needs_grading'), ({'status': 'Graded'}, 'graded'),
                         ({'displayGrade': {'score': 0}}, 'graded'), ({'exempt': True}, 'exempt')]:
    item = rules.decide(grade, None, no_request, {}, NOW)
    assert item['submission_status'] == expected
    assert item['submitted'] is (None if expected == 'exempt' else True)
for invalid in ('', '—', 'NaN', float('inf'), True, False):
    item = rules.decide({'displayGrade': {'score': invalid}}, None, failed, {}, NOW)
    assert item['submitted'] is None and item['submission_status'] == 'unknown'

draft = rules.decide({'status': 'InProgress'}, None, lambda: UPLOAD, {}, NOW)
assert draft['submitted'] is False and draft['submission_status'] == 'draft'
assert rules.decide({}, None, lambda: HISTORY.replace('26-9-30 下午3:12', '草稿'), {}, NOW)['submission_status'] == 'draft'
assert rules.decide({'status': 'InProgress'}, rules.state('submitted', 'activity'), no_request, {}, NOW)['submitted'] is True
conflict = {'displayGrade': {'score': 0}, 'status': 'NotAttempted'}
assert rules.decide(conflict, None, lambda: HISTORY, {}, NOW)['submitted'] is True
assert rules.decide(conflict, None, lambda: UPLOAD, {}, NOW)['submitted'] is False
assert rules.decide(conflict, None, failed, {}, NOW)['submitted'] is None
negative = rules.state('not_submitted', 'activity')
assert rules.decide({'status': 'Graded'}, negative, lambda: UPLOAD, {}, NOW)['submitted'] is False
assert rules.decide({'status': 'Graded', 'displayGrade': {'score': 0}}, negative, failed, {}, NOW)['submitted'] is None
assert '不一致' in rules.decide({'status': 'Graded'}, negative, failed, {}, NOW)['submission_reason']

for html in (HISTORY.replace('<li>synthetic.pdf</li>', ''), UPLOAD.replace('上载作业：合成作业', '访问失败')):
    try:
        rules.submission_history(html)
    except SourceError:
        pass
    else:
        raise AssertionError('An error or empty history cannot establish submission status')

old = {**history, 'checked_at': '2026-10-16T10:00:00+00:00'}
cached = rules.decide({}, None, failed, old, NOW)
assert cached['submitted'] is True and cached['submission_stale'] is True
assert cached['submitted_at'] == old['submitted_at'] and cached['checked_at'] == old['checked_at']
assert cached['due_at'] == old['due_at'] and cached['max_score'] == old['max_score']
assert cached['submission_evidence'] == 'cached'
assert rules.decide({}, None, failed, {}, NOW)['submitted'] is None

activity = rules.activity('''<div id="grades_wrapper">
<div id="1" class="sortable_item_row"><div class="gradable">未提交问题指南</div><div class="activity">—</div></div>
<div id="2" class="sortable_item_row submitted_item_row"><div class="gradeStatus"><img alt="需要评分"></div></div>
<div id="3" class="sortable_item_row"><div class="activity">未提交</div></div>
<div id="4" class="sortable_item_row"><div class="gradeStatus">Exempt</div></div></div>''')
assert [value['submission_status'] for value in activity.values()] == ['unknown', 'needs_grading', 'not_submitted', 'exempt']
zero_without_submission = rules.activity('<div id="grades_wrapper"><div id="5" class="sortable_item_row graded_item_row"><div class="activity">No Submission</div><div class="grade">0</div></div></div>')
assert zero_without_submission['_5_1']['submitted'] is False
print('blackboard submission: explicit evidence, draft vs earlier submission, score conflicts, placeholders, failed reads and exact history dates passed')
