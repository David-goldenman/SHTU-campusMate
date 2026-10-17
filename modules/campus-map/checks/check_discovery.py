"""Synthetic sources only: discovery must never silently change routing conditions."""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('campus-map')
parser = sys.modules[module.__name__ + '.discovery_parser']
today = datetime.now(ZoneInfo('Asia/Shanghai')).date()
url = 'https://www.shanghaitech.edu.cn/' + today.strftime('%Y/%m%d') + '/c1004a999999/page.htm'


def source(text, identity='notice-one', kind='official'):
    return {'source': kind, 'source_id': identity, 'title': text.split('\n')[0], 'text': text,
            'source_date': today.isoformat(), 'url': url if kind == 'official' else 'https://mail.shanghaitech.edu.cn/coremail/'}


async def check():
    with sandbox('campus-map') as context:
        app = FastAPI(); app.include_router(module.create_router(context))
        service = module._discovery
        west = next(b['id'] for b in service.places['buildings'] if b.get('short_name') == '西门')
        closure = source('西门人行通道施工封闭\n2026年10月18日起西门行人请绕行北门。')
        reopen = source('西门恢复通行\n西门施工结束，行人通道已恢复通行。', 'notice-two')
        assert parser.screen(closure, service.places, today)['action'] == 'restriction'
        assert parser.screen(reopen, service.places, today)['action'] == 'reopening'
        assert parser.screen(source('西门预计恢复通行\n尚未开放。'), service.places, today)['action'] != 'reopening'
        assert parser.screen(source('西门没有恢复通行，请绕行。'), service.places, today)['action'] != 'reopening'
        assert parser.screen(source('西门机动车封闭，车辆绕行。'), service.places, today)['action'] == 'caution'
        assert parser.screen(source('西门机动车封闭，行人正常通行。'), service.places, today)['action'] == 'caution'
        assert parser.screen(source('体育馆车辆临时管制，行人影响需核实。'), service.places, today)['action'] == 'caution'
        assert parser.screen(source('数据库维护后恢复开放服务。'), service.places, today) is None
        assert not parser.public_notice_url('https://www.shanghaitech.edu.cn.evil.invalid/2026/1018/c1004a1/page.htm')
        links = parser.notice_links(f'<a href="{url}">合成施工通知</a><a href="https://evil.invalid/page.htm">外站</a>', today)
        assert len(links) == 1 and links[0]['source_id'] == url
        assert parser.notice_text('<h1>合成通知</h1><div class="wp_articlecontent">西门施工<script>ignore()</script></div>') == ('合成通知', '西门施工')

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
            original = (await client.get('/conditions')).json()
            owner = service.owner()
            assert service.ingest(owner, 0, [closure]) == 1
            assert service.ingest(owner, 0, [closure]) == 0
            assert (await client.get('/conditions')).json()['version'] == original['version']
            state = (await client.get('/discovery')).json(); lead = state['items'][0]
            assert lead['state'] == 'pending' and not state['settings']['enabled']
            item = {'title': '合成西门步行封闭', 'state': 'confirmed', 'effect': 'blocked', 'scope': 'place',
                    'place_id': west, 'starts_on': today.isoformat(), 'review_on': today.isoformat(),
                    'source_kind': 'official', 'source_title': closure['title'], 'source_date': today.isoformat(),
                    'source_url': url, 'note': lead['evidence']}

            def change(item, condition_state, lead_id=lead['id'], confirmed=True, account=owner):
                return {'item': item, 'version': condition_state['version'], 'account_revision': condition_state['account_revision'],
                        'discovery_id': lead_id, 'discovery_account': account, 'evidence_confirmed': confirmed}

            assert (await client.post('/conditions', json=change(item, original, confirmed=False))).status_code == 422
            assert (await client.post('/conditions', json=change(item, original, account='old-account'))).status_code == 409
            response = await client.post('/conditions', json=change(item, original)); assert response.status_code == 201, response.text
            conditions = response.json(); active = conditions['items'][-1]
            assert active['state'] == 'confirmed' and lead['id'] in active['discovery_ids']
            assert service.public()['items'][0]['state'] == 'reviewed'
            assert (await client.post('/conditions', json=change(item, conditions))).status_code == 409
            assert service.ingest(owner, 0, [closure]) == 0
            assert service.ingest(owner, 0, [reopen]) == 1
            assert (await client.get('/conditions')).json()['items'][-1]['state'] == 'confirmed'
            recovery = next(v for v in service.public()['items'] if v['action'] == 'reopening')
            resolved = {**item, 'state': 'resolved', 'source_title': reopen['title'], 'note': recovery['evidence']}
            assert (await client.post('/conditions', json=change(resolved, conditions, recovery['id']))).status_code == 422
            response = await client.put('/conditions/'+active['id'], json=change(resolved, conditions, recovery['id']))
            assert response.status_code == 200, response.text
            conditions = response.json(); assert conditions['items'][-1]['state'] == 'resolved'
            conditions = (await client.post('/conditions/undo', json={k:conditions[k] for k in ('version','account_revision')})).json()
            assert conditions['items'][-1]['state'] == 'confirmed'
            assert service.ingest(owner, 0, [reopen]) == 0  # Undo never makes a source reimport itself.

            changed = source('西门继续施工封闭\n新通道尚未开放。', 'changed-notice')
            service.ingest(owner, 0, [changed])
            old_lead = next(v for v in service.public()['items'] if v['source_id'] == 'changed-notice')
            changed['text'] += '\n新增说明：北门人行通道也封闭。'
            service.ingest(owner, 0, [changed])
            assert next(v for v in service.public()['items'] if v['id'] == old_lead['id'])['state'] == 'superseded'
            assert (await client.post('/conditions', json=change(item, conditions, old_lead['id']))).status_code == 409
            current = service.public(); pending = next(v for v in current['items'] if v['state'] == 'pending')
            response = await client.post('/discovery/'+pending['id']+'/dismiss', json={k:current[k] for k in ('version','account_revision')})
            assert response.status_code == 200
            assert service.ingest(owner, 0, [changed]) == 0
            stale = {k:current[k] for k in ('version','account_revision')}
            assert (await client.post('/discovery/check', json=stale)).status_code == 409

            # Change only the email account: private evidence and conditions must be partitioned.
            original_revision = context.auth.get_account_revision
            context.auth.get_account_revision = lambda provider: 'second-mail-account' if provider == 'coremail' else original_revision(provider)
            assert service.public()['items'] == []
            assert (await client.get('/conditions')).json()['version'] == 0
            try:
                service.ingest(owner, 0, [closure])
            except HTTPException as error:
                assert error.status_code == 409
            else:
                raise AssertionError('old account result was accepted')
            context.auth.get_account_revision = original_revision
            assert (await client.get('/conditions')).json()['version'] == conditions['version']

        # Public mail API use, bounded body reads, no mark-read endpoint, disabled dependency and async account switch.
        state = service.read(owner); state['settings'].update(official=False, mail=True); service.save(owner, state)
        calls = []
        async def mail_api(module_id, path='/snapshot', **kwargs):
            calls.append((module_id,path,kwargs.get('method','GET')))
            if path == '/sync':
                return httpx.Response(202, json={'queued':True})
            if path.startswith('/message?'):
                return httpx.Response(200, json={'body_text':'体育馆施工，西侧行人通道封闭，请绕行。'})
            return httpx.Response(200, json={'status':'ready','data':{'messages':[{'id':'mail:synthetic','title':'合成体育馆施工通知','received_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}]}})
        context.api = mail_api
        await service.scan(owner, 0)
        assert any(i['source'] == 'mail' for i in service.public()['items'])
        assert any(path == '/sync' and method == 'POST' for _,path,method in calls)
        assert all(module_id == 'mail' for module_id,_,_ in calls)
        before = json.dumps(service.public()['items'], ensure_ascii=False)
        async def missing(*args, **kwargs):
            return httpx.Response(404, json={})
        context.api = missing
        await service.scan(owner, 0)
        assert service.public()['sources']['mail']['status'] == 'error'
        assert json.dumps(service.public()['items'], ensure_ascii=False) == before
        async def switching(*args, **kwargs):
            context.auth.revision = 'switched-during-read'
            return httpx.Response(200, json={'data':{'messages':[]}})
        context.api = switching
        try:
            await service.scan(owner, 0)
        except HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError('account change during read was ignored')
        assert service.public()['items'] == []
        context.auth.revision = 'synthetic-account-one'
        # Idle worker is owned by module lifecycle and stops without further writes/network.
        state = service.read(owner); state['settings']['enabled'] = False; service.save(owner, state)
        module.start(context); module.stop(context)
        assert not service.thread.is_alive()


asyncio.run(check())
print('campus-map discovery: source parsing, pending-only import, explicit confirmation, reopening, deduplication, changed sources, dismissal, account isolation, optional mail and cleanup passed')
