"""Independent metadata matching: batching, cache, retry, cancellation and scope."""
import asyncio
import copy
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('group-messages')
models = sys.modules[module.__name__ + '.models']
qq = sys.modules[module.__name__ + '.qq']
COURSES = [{'id': 'em', 'title': '电磁学', 'code': 'EE130', 'aliases': ['Electromagnetics'], 'current': True, 'term': '2026-fall'}]


def wait(predicate):
    deadline = time.monotonic() + 8
    while not predicate():
        assert time.monotonic() < deadline, 'Timed out waiting for matching worker'
        time.sleep(.01)


def fixture(context, count=83):
    service = module.Service(context)
    assert hasattr(service, 'matcher'), 'Matching must own an independent worker and cache'
    catalog = {'items': copy.deepcopy(COURSES), 'current_semester': '2026-fall', 'account_revision': service.owner()}
    async def api(name, path='/snapshot', **kwargs):
        assert (name, path) == ('courses', '/identities')
        return httpx.Response(200, json={**catalog, 'account_revision': service.owner()})
    context.api = api
    service.save_source(service.owner(), 'wechat', {'connection': 'conn', 'revision': 'r1', 'selected': [], 'enabled': False,
        'groups': [{'id': 'g'+str(i), 'name': '电磁-'+str(i)} for i in range(count)], 'coverage': {}})
    calls = []
    def run(**kwargs):
        data = json.loads(kwargs['context']); calls.append(data)
        return answer(data)
    context.ai.run = run
    return service, catalog, calls


def answer(data):
    return {'content': json.dumps({'matches': [{'group_id': row['id'], 'candidates': [{'course_id': 'em', 'relation': 'abbreviation',
        'evidence': '电磁', 'reason': '电磁是电磁学简称'}]} for row in data['groups']]}), 'tools': [{'name': 'group_match_submit', 'is_error': False}]}


with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context)
    asyncio.run(service.course_options())
    assert not calls, 'Reading the courses endpoint must never start AI'
    service.matcher.start()
    try:
        service.matcher.observe(service.owner(), catalog)
        wait(lambda: service.status()['matching']['wechat']['state'] == 'done')
        assert [len(row['groups']) for row in calls] == [40, 40, 3]
        assert service.status()['matching']['wechat']['completed'] == 83
        options = asyncio.run(service.course_options())
        assert options['matches']['wechat']['g0']['status'] == 'suggested'
        assert not service.sources()['wechat']['selected'] and not service.sources()['wechat']['enabled']
        for _ in range(10): service.matcher.observe(service.owner(), catalog)
        asyncio.run(service.course_options())
        assert len(calls) == 3, 'Polling and unchanged metadata must hit the cache'
        restored = module.Service(context)
        restored.matcher.observe(restored.owner(), catalog)
        assert restored.status()['matching']['wechat']['completed'] == 83, 'Successful cache must survive restart'
        restored.close()
    finally: service.close()

with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context)
    def run(**kwargs):
        data = json.loads(kwargs['context']); calls.append(data)
        if len(calls) == 2: raise HTTPException(502, 'Synthetic provider failure with private details')
        return answer(data)
    context.ai.run = run
    service.matcher.start()
    try:
        service.matcher.observe(service.owner(), catalog)
        wait(lambda: service.status()['matching']['wechat']['state'] == 'error')
        assert service.status()['matching']['wechat']['completed'] == 40
        assert 'private details' not in json.dumps(service.status())
        for _ in range(10): service.matcher.observe(service.owner(), catalog)
        assert len(calls) == 2, 'Failure must not create an automatic retry loop'
        asyncio.run(service.request_match('wechat', models.MatchRequest(expected_revision='r1')))
        wait(lambda: service.status()['matching']['wechat']['state'] == 'done')
        assert [len(row['groups']) for row in calls] == [40, 40, 40, 3], 'Retry must retain successful batches'
    finally: service.close()

for change in ('cancel', 'course_change', 'account_change'):
    with sandbox('group-messages') as context:
        service, catalog, calls = fixture(context, 1)
        started, release = threading.Event(), threading.Event()
        def run(**kwargs):
            data = json.loads(kwargs['context']); calls.append(data); started.set()
            assert release.wait(5)
            return answer(data)
        context.ai.run = run
        service.matcher.start()
        try:
            service.matcher.observe(service.owner(), catalog); assert started.wait(5)
            body = models.WechatConnection(database_dir='synthetic', pid=123, acknowledge_local_read=True)
            assert service.queue('connect', 'wechat', body)['queued'], 'Matching must not occupy the connection queue'
            if change == 'cancel': service.matcher.cancel('wechat')
            elif change == 'course_change': catalog['items'].clear()
            else: context.auth.revision = 'other-account'
            release.set()
            wait(lambda: service.matcher.active is None)
            options = asyncio.run(service.course_options())
            assert not any(row['status'] == 'suggested' for row in options['matches'].get('wechat', {}).values()), change
            if change == 'cancel':
                service.matcher.observe(service.owner(), catalog)
                assert len(calls) == 1, 'Cancelled work waits for explicit retry'
        finally: release.set(); service.close()

with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context, 1)
    selected = {'id': 'g0', 'course_id': 'em', 'name': '电磁', 'trusted_senders': ['teacher'], 'auto_extract': True, 'auto_apply': False}
    service.save_source(service.owner(), 'qq', {'connection': 'same', 'revision': 'q1', 'account': '123', 'groups': [], 'selected': [selected],
        'interval_seconds': 60, 'history_days': 30, 'allow_ai': True, 'enabled': True})
    with patch.object(qq, 'connect', return_value=({'account': '123', 'groups': [{'id': 'g0', 'name': '电磁新群名'}]}, {})):
        service._connect({'owner': service.owner(), 'source': 'qq', 'kind': 'connect', 'body': models.QQConnection(access_token='synthetic', acknowledge_local_read=True)})
    config = service.sources()['qq']
    assert config['connection'] == 'same' and config['selected'][0]['trusted_senders'] == ['teacher']
    assert config['selected'][0]['name'] == '电磁新群名' and not config['enabled']
    assert config['allow_ai'] and config['history_days'] == 30 and config['interval_seconds'] == 60
    service.close()

with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context, 1)
    service.matcher.observe(service.owner(), catalog)
    config = service.sources()['wechat']; config['groups'][0]['name'] = 'EE130'
    service.save_source(service.owner(), 'wechat', config)
    service.matcher.observe(service.owner(), catalog)
    assert service.status()['matching']['wechat']['state'] == 'done', 'Superseded queued matching must publish the new local result immediately'
    assert not service.matcher.pending and service.status()['matching']['wechat']['total'] == 0
    service.close()

with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context, 1)
    service.matcher.observe(service.owner(), catalog)
    context.ai.settings = lambda: {'enabled': False}
    service.matcher.observe(service.owner(), catalog)
    assert service.status()['matching']['wechat']['state'] == 'idle' and not service.matcher.pending, 'Pausing AI removes pending requests without failing them'
    service.matcher.start()
    context.ai.settings = lambda: {'enabled': True}
    service.matcher.observe(service.owner(), catalog)
    wait(lambda: service.status()['matching']['wechat']['state'] == 'done')
    assert len(calls) == 1
    service.close()

with sandbox('group-messages') as context:
    service, catalog, calls = fixture(context, 1)
    started, cancelled = threading.Event(), threading.Event()
    def run_until_cancelled(**kwargs):
        data = json.loads(kwargs['context']); calls.append(data); started.set()
        if kwargs['cancel_event'].wait(5):
            cancelled.set()
        return answer(data)
    context.ai.run = run_until_cancelled
    service.matcher.start()
    try:
        service.matcher.observe(service.owner(), catalog)
        assert started.wait(5)
        result = service.forget('wechat')
        assert not result['sources']['wechat']['connected']
        assert cancelled.wait(1), 'Removing a source must cancel its active name-only AI request'
        wait(lambda: service.matcher.active is None)
        assert not service.matcher.pending and not service.status()['matching']
    finally:
        service.close()

async def check_routes():
    with sandbox('group-messages') as context:
        setup, catalog, calls = fixture(context, 1)
        app = FastAPI(); app.include_router(module.create_router(context))
        service = module._service
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
                assert (await client.post('/sources/wechat/match', json={'expected_revision': 'old'})).status_code == 409
                assert (await client.post('/sources/wechat/match', json={'expected_revision': 'r1'})).status_code == 200
                assert (await client.get('/status')).json()['matching']['wechat']['state'] == 'queued'
                assert (await client.delete('/sources/wechat/match')).json()['matching']['wechat']['state'] == 'cancelled'
                assert (await client.post('/sources/unknown/match', json={'expected_revision': 'r1'})).status_code == 422
                assert not calls
        finally: service.close(); setup.close()

asyncio.run(check_routes())
print('PASS: 40-name batches, persistent cache, no GET/model coupling, partial retry, isolated cancellation/scope, source-removal cancellation, reconnect and match routes')
