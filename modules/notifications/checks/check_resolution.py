import asyncio
import sys
from copy import deepcopy
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backend.services.campus.analysis import account_revision
from checks.module_support import load, sandbox

package = load('notifications')


async def check():
    with sandbox('notifications') as context:
        router = package.create_router(context)
        service = package._service
        owner = account_revision(context)
        records = {
            state: {'id': 'blackboard:' + state, 'source_status': 'ready', 'needs_review': state == 'unknown',
                    'submitted': state in {'submitted', 'needs_grading', 'graded'}, 'submission_status': state}
            for state in ('submitted', 'needs_grading', 'graded', 'draft', 'not_submitted', 'unknown')
        }
        records['cached'] = {**records['submitted'], 'id': 'blackboard:cached', 'submission_stale': True}
        records['failed'] = {**records['submitted'], 'id': 'blackboard:failed', 'source_status': 'error'}
        unavailable, switch = False, False

        async def api(module, path='/snapshot', **options):
            assert module == 'assignments' and path == '/snapshot' and not options
            if switch:
                context.auth.revision = 'new-owner'
            return httpx.Response(409 if unavailable else 200, json={'data': {'assignments': list(records.values())}})

        context.api = api

        def notice(identity, keys, title='合成作业待提交', read=False):
            return {'id': identity, 'title': title, 'summary': '请在截止前提交合成作业。', 'read': read,
                    'importance': 'normal', 'source_revision': 'v1', 'created_at': '2026-10-17T10:00:00Z',
                    'citations': [{'id': key, 'title': '合成作业', 'source': 'assignments'} for key in keys]}

        items = [notice(key, [record['id']]) for key, record in records.items()]
        items += [notice('all-complete', ['assignments:blackboard:submitted', 'blackboard:graded']),
                  notice('mixed-pending', ['blackboard:submitted', 'blackboard:not_submitted']),
                  notice('mixed-source', ['blackboard:submitted', 'announcements:other']),
                  notice('grade-notice', ['blackboard:graded'], title='合成作业评分结果'),
                  notice('manual', ['blackboard:submitted']), notice('already-read', ['blackboard:submitted'], read=True)]
        context.store.write('imports:' + owner, items)
        context.store.write('notifications', {'owner': owner, 'items': [notice('generated', ['blackboard:submitted'])]})
        service.mark_read('manual', False)
        endpoint = next(route.endpoint for route in router.routes if route.path == '/snapshot')
        first = await endpoint()
        by_id = {item['id']: item for item in first['items']}
        assert {key for key, item in by_id.items() if item.get('auto_read')} == {'submitted', 'needs_grading', 'graded', 'all-complete', 'generated'}
        assert by_id['manual']['read'] is False and by_id['manual']['read_source'] == 'manual'
        assert by_id['already-read']['read'] and 'auto_read' not in by_id['already-read']
        assert all(not by_id[key]['read'] for key in ('draft', 'unknown', 'cached', 'failed', 'grade-notice', 'mixed-pending', 'mixed-source'))
        original_auto = deepcopy(by_id['submitted']['auto_read'])
        assert next(item for item in (await endpoint())['items'] if item['id'] == 'submitted')['auto_read'] == original_auto

        body = package.ImportedNotice(account_revision=owner, id='submitted', title='合成作业待提交', summary='截止前提交',
                                      source_revision='v1', citations=[{'id': 'blackboard:submitted', 'title': '合成作业', 'source': 'blackboard'}])
        assert service.import_notice(body)['auto_read'] == original_auto, 'A repeated import keeps automatic read state'
        records['submitted'].update(submitted=False, submission_status='draft')
        reopened = {item['id']: item for item in (await endpoint())['items']}
        assert all(not reopened[key]['read'] and 'auto_read' not in reopened[key] for key in ('submitted', 'all-complete', 'generated'))
        assert reopened['already-read']['read'], 'Do not reopen a manually read legacy notice'

        service.mark_read('submitted', True)
        assert next(item for item in (await endpoint())['items'] if item['id'] == 'submitted')['read']
        unavailable = True
        before = deepcopy(service.snapshot()['items'])
        assert (await endpoint())['items'] == before, 'A disabled or failing assignment module keeps notifications'
        unavailable = False
        switch = True
        before = deepcopy(context.store.read('imports:' + owner))
        await service.reconcile_assignments()
        assert context.store.read('imports:' + owner) == before, 'Do not apply old-account evidence after an account change'
        assert service.snapshot()['items'] == []
        service.close()


asyncio.run(check())
print('notifications: confirmed submission resolution, reopened drafts, grading notices, manual priority, cache failures and account isolation passed')
