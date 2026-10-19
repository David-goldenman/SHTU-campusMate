"""Current-course matching and enforced collection boundaries with synthetic data."""
import asyncio
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('group-messages')
matching = sys.modules[module.__name__ + '.matching']
models = sys.modules[module.__name__ + '.models']
qq = sys.modules[module.__name__ + '.qq']
extraction = sys.modules[module.__name__ + '.extraction']
courses = [{'id': 'em', 'title': '电磁学', 'aliases': ['Electromagnetics', '电磁学-2026秋'], 'code': 'EE130', 'term': '2026-fall', 'current': True, 'course_ids': ['bb:em']},
           {'id': 'project', 'title': '电磁学课程设计', 'aliases': ['Electromagnetics Project'], 'code': 'EE130P', 'term': '2026-fall', 'current': True, 'course_ids': ['bb:project']}]


def suggest(name, values=courses, saved=None):
    return matching.suggest({'id': 'g', 'name': name}, values, '2026-fall', saved)


assert suggest('2026秋-电磁学')['course_id'] == 'em'
assert suggest('2026秋-电磁学微信群')['course_id'] == 'em'
assert suggest('EE 130P 2026 Fall')['course_id'] == 'project'
assert suggest('电磁学课程设计 2026秋')['course_id'] == 'project'
assert suggest('Electromagnetics 2026 Fall')['course_id'] == 'em'
assert suggest('2025秋-电磁学')['status'] == 'other_term'
assert suggest('2026春-电磁学')['status'] == 'other_term'
assert suggest('2025-2026-1 电磁学')['status'] == 'other_term'
assert suggest('EE130 与 EE130P')['status'] == 'ambiguous'
assert suggest('电磁学讨论', courses + [{**courses[0], 'id': 'another'}])['course_id'] == ''
assert suggest('电磁学', courses + [{**courses[0], 'id': 'another'}])['status'] == 'ambiguous'
assert suggest('完全不同的群名')['status'] == 'unmatched'
assert suggest('2026秋-电磁学', saved={'course_id': 'project'})['course_id'] == 'project'

# The supplied announcement has a class time, but only a relative Quiz time.
notice = '10月21日下周三\n1. 课上上交hw2\n2. 习题课补课时间改到20点15分（习题课正常时间）\n3. 习题课补课完之后会有一次quiz 题量会比前两次quiz少一些 大家做好准备'
message = {'id': 'm1', 'remote_id': 'm1', 'sender_id': 'teacher', 'sender_name': '合成老师', 'revision': 1,
           'sent_at': '2026-10-18T12:00:00+08:00', 'kind': 'text', 'text': notice}
batch = {'messages': [message], 'new_ids': ['m1']}
prepared = extraction.prepare(batch, {'course': courses[0]}, [])
quiz = {'object_key': 'quiz-after-makeup', 'kind': 'quiz', 'title': '补课后 Quiz', 'summary': '补课结束后进行，具体钟点待确认',
        'date': '2026-10-21', 'citations': [{'message_id': 'm1', 'quote': notice}]}
checked = extraction.validate({'items': [quiz]}, prepared, batch, [])[0]
assert checked['date'] == '2026-10-21' and checked['starts_at'] is None and checked['ends_at'] is None
try:
    extraction.validate({'items': [{**quiz, 'starts_at': '2026-10-21T20:15:00+08:00'}]}, prepared, batch, [])
except HTTPException as error:
    assert error.status_code == 502
else:
    raise AssertionError('Class start time cannot be borrowed as the following Quiz start')


async def rejected(operation):
    try:
        await operation
    except HTTPException as error:
        assert error.status_code == 409, error.detail
    else:
        raise AssertionError('Expected out-of-scope operation to fail')


async def check():
    with sandbox('group-messages') as context:
        service = module.Service(context)
        owner = service.owner()
        available = True
        values = copy.deepcopy(courses)
        async def api(name, path='/snapshot', **kwargs):
            assert (name, path) == ('courses', '/identities'), (name, path)
            return httpx.Response(200, json={'items': values, 'current_semester': '2026-fall', 'account_revision': service.owner()}) if available else httpx.Response(404)
        context.api = api
        groups = [{'id': 'g1', 'name': '2026秋-电磁学'}, {'id': 'g2', 'name': '2025秋-电磁学'}, {'id': 'g3', 'name': '未关联群'}]
        selected = [{'id': row['id'], 'name': row['name'], 'course_id': cid, 'course': {'id': cid}, 'auto_extract': False, 'auto_apply': False, 'trusted_senders': []} for row, cid in zip(groups, ['em', 'old', ''])]
        config = {'connection': 'conn', 'revision': 'r1', 'groups': groups, 'selected': selected, 'enabled': True, 'history_days': 7,
                  'interval_seconds': 300, 'allow_ai': False, 'coverage': {}}
        service.save_source(owner, 'qq', config)
        options = await service.course_options()
        assert len(options['items']) == 2 and options['matches']['qq']['g2']['status'] == 'inactive'
        assert service.sources(owner)['qq']['course_scope']['active_group_ids'] == ['g1']
        reads = []
        def synchronize(config, secret, cancelled):
            reads.append([row['id'] for row in config['selected']])
            return {'messages': {'g1': [{'remote_id': '1', 'text': '合成通知', 'sender_id': 't', 'sent_at': None}]}}
        with patch.object(qq, 'synchronize', synchronize):
            await asyncio.to_thread(service._sync, {'owner': owner, 'source': 'qq', 'kind': 'sync'})
        assert reads == [['g1']], reads
        assert service.messages.rows(owner, 'qq', 'conn', 'g1')['total'] == 1
        assert len(service.sources(owner)['qq']['selected']) == 3, 'Keep old choices available for correction'
        await rejected(service.select('qq', models.Selection(expected_revision='r1', groups=[{'id': 'g2', 'course_id': 'old'}])))
        await rejected(service.select('qq', models.Selection(expected_revision='r1', groups=[{'id': 'g3'}])))
        # Explicit correction persists and never gets overwritten by the name suggestion.
        await service.select('qq', models.Selection(expected_revision='r1', groups=[{'id': 'g1', 'course_id': 'project'}]))
        service.cancelled.clear()
        restored = module.Service(context)
        options = await restored.course_options()
        assert options['matches']['qq']['g1']['course_id'] == 'project'
        assert not restored.visible({'connection': 'conn', 'source': 'qq', 'group_id': 'g1', 'course': {'id': 'em'}}, restored.sources(owner))
        context.store.write('items:' + owner, {'old-item': {'id': 'old-item', 'connection': 'conn', 'source': 'qq', 'group_id': 'g1',
            'course': {'id': 'em'}, 'summary': '旧课程事项', 'kind': 'notice', 'status': 'pending'}})
        prompts = []
        def ai(**kwargs):
            prompts.append(json.loads(kwargs['context']))
            return {'content': '{"items":[]}', 'tools': [{'name': 'group_submit', 'is_error': False}]}
        context.ai.run = ai
        await asyncio.to_thread(restored._extract, {'owner': owner, 'source': 'qq', 'group_id': 'g1', 'manual': True})
        assert prompts[0]['existing_items'] == [] and prompts[0]['course']['id'] == 'project'
        assert 'old-item' in restored.all_items(owner), 'Preserve old results without retargeting them to another course'
        # A semester/source change blocks I/O and preserves cached data/settings.
        values.clear()
        with patch.object(qq, 'synchronize', synchronize):
            await rejected(asyncio.to_thread(restored._sync, {'owner': owner, 'source': 'qq', 'kind': 'sync'}))
        assert len(reads) == 1 and restored.messages.rows(owner, 'qq', 'conn', 'g1')['total'] == 1
        values.extend(copy.deepcopy(courses)); available = False
        with patch.object(qq, 'synchronize', synchronize):
            await rejected(asyncio.to_thread(restored._sync, {'owner': owner, 'source': 'qq', 'kind': 'sync'}))
        assert len(reads) == 1
        available = True
        def stale(config, secret, cancelled):
            values.clear()
            return {'messages': {'g1': [{'remote_id': 'late', 'text': '过期结果', 'sender_id': 't', 'sent_at': None}]}}
        with patch.object(qq, 'synchronize', stale):
            await rejected(asyncio.to_thread(restored._sync, {'owner': owner, 'source': 'qq', 'kind': 'sync'}))
        assert restored.messages.rows(owner, 'qq', 'conn', 'g1')['total'] == 1


asyncio.run(check())
print('PASS: semester/name/code matching, manual correction, current-only collection, unavailable dependencies and in-flight scope changes')
