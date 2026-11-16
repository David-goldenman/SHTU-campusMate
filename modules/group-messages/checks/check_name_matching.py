"""Rules and evidence-backed, metadata-only semantic suggestions."""
import copy
import json
import sys
import threading
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('group-messages')
matching = sys.modules[module.__name__ + '.matching']
courses = [
    {'id': 'em', 'title': '电磁学', 'code': 'EE130', 'aliases': ['Electromagnetics']},
    {'id': 'project', 'title': '电磁学课程设计', 'code': 'EE130P', 'aliases': []},
    {'id': 'p1', 'title': '普通物理Ⅰ', 'code': 'PHYS101', 'aliases': ['Physics I']},
    {'id': 'p2', 'title': '普通物理Ⅱ', 'code': 'PHYS102', 'aliases': ['Physics II']},
    {'id': 'lab', 'title': '普通物理实验', 'code': 'PHYS111', 'aliases': []},
]


def suggest(name):
    return matching.suggest({'id': 'g', 'name': name}, courses, '2026-fall')


assert suggest('2025级 EE130 交流群')['course_id'] == 'em', 'A cohort year is not an old semester'
assert suggest('2025 EE130')['course_id'] == 'em', 'A bare year is not sufficient to reject a group'
assert suggest('2025秋 EE130')['status'] == 'other_term'
assert suggest('电磁学 习题课 2026秋')['course_id'] == 'em'
assert suggest('EE130P 电磁学')['course_id'] == 'project'
assert suggest('普通物理Ⅱ 2026秋')['course_id'] == 'p2'
assert suggest('普通物理实验 2026秋')['course_id'] == 'lab'
assert suggest('EE130 与 EE130P')['status'] == 'ambiguous'
assert suggest('同学聚餐群')['status'] == 'unmatched'

groups = [{'id': 'g1', 'name': '2026秋 电磁'}, {'id': 'g2', 'name': '普通物理 II 讨论'}, {'id': 'g3', 'name': '同学聚餐群'}]
output = {'matches': [
    {'group_id': 'g1', 'candidates': [{'course_id': 'em', 'relation': 'abbreviation', 'evidence': '电磁', 'reason': '电磁是电磁学的简称'}]},
    {'group_id': 'g2', 'candidates': [{'course_id': 'p1', 'relation': 'synonym', 'evidence': '普通物理 II', 'reason': '名称相关'}]},
    {'group_id': 'g3', 'candidates': []},
]}
assert callable(getattr(matching, 'validate_ai', None)), 'Semantic output must be validated by the module'
result = matching.validate_ai(output, groups, courses, '2026-fall')
assert result['g1']['status'] == 'suggested' and result['g1']['method'] == 'ai'
assert result['g2']['status'] == 'unmatched', 'A contradictory level must not be recommended'
assert result['g3']['status'] == 'unmatched'
for name, candidate, evidence in [('普物实验群', 'p1', '普物'), ('Physics lab helpers', 'p1', 'Physics')]:
    role_courses = [courses[2], {**courses[-1], 'aliases': ['Physics Laboratory']}]
    value = {'matches': [{'group_id': 'lab-group', 'candidates': [{'course_id': candidate, 'relation': 'abbreviation', 'evidence': evidence, 'reason': 'Related name'}]}]}
    assert matching.validate_ai(value, [{'id': 'lab-group', 'name': name}], role_courses, '2026-fall')['lab-group']['status'] != 'suggested', 'Independent lab abbreviations must not recommend the main course'
weak = copy.deepcopy(output)
weak['matches'][0]['candidates'][0]['relation'] = 'related'
assert matching.validate_ai(weak, groups, courses, '2026-fall')['g1']['status'] == 'ambiguous'
for mutation in ('unknown_course', 'invented_evidence', 'duplicate_group', 'missing_group'):
    invalid = copy.deepcopy(output)
    if mutation == 'unknown_course': invalid['matches'][0]['candidates'][0]['course_id'] = 'invented'
    if mutation == 'invented_evidence': invalid['matches'][0]['candidates'][0]['evidence'] = '老师说这门课是电磁学'
    if mutation == 'duplicate_group': invalid['matches'].append(invalid['matches'][0])
    if mutation == 'missing_group': invalid['matches'].pop()
    try:
        matching.validate_ai(invalid, groups, courses, '2026-fall')
    except HTTPException as error:
        assert error.status_code == 502
    else:
        raise AssertionError('Invalid model output accepted: ' + mutation)

with sandbox('group-messages') as context:
    captured = []
    def run(**kwargs):
        captured.append(kwargs)
        return {'content': json.dumps(output), 'tools': [{'name': 'group_match_submit', 'is_error': False}]}
    context.ai.run = run
    matching.run_ai(context, groups, courses, '2026-fall', threading.Event())
    payload = json.loads(captured[0]['context'])
    assert set(payload) == {'groups', 'courses', 'current_semester'}
    assert payload['groups'] == groups and len(payload['courses']) == 5
    assert captured[0]['plugins'] == ['group-messages']

print('PASS: cohort/term/role/code/level rules, semantic evidence and closed IDs, weak suggestions, metadata-only Harness input')
