"""Synthetic selected-chat -> evidence -> real public work/calendar commands."""
import asyncio
import copy
import json
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module, study, calendar = load('group-messages'), load('academic-assistant'), load('timetable')
Service = module.Service
extraction = sys.modules[module.__name__ + '.extraction']
qq = sys.modules[module.__name__ + '.qq']
models = sys.modules[module.__name__ + '.models']


def rejects(fn, code=409):
    try:
        fn()
    except HTTPException as error:
        assert error.status_code == code, error.detail
    else:
        raise AssertionError('Expected rejected operation')


async def rejected(fn, code=409):
    try:
        await fn
    except HTTPException as error:
        assert error.status_code == code, error.detail
    else:
        raise AssertionError('Expected rejected operation')


def raw(mid, text='作业1在2026年10月20日23:59截止', sender='teacher', **extra):
    return {'remote_id':str(mid), 'sender_id':sender, 'sender_name':'合成老师',
            'sent_at':datetime.now(timezone.utc).isoformat(), 'text':text, 'kind':'text', 'reply_to':'', 'truncated':False, **extra}


async def check():
    with sandbox('group-messages') as context, sandbox('academic-assistant') as study_context, sandbox('timetable') as calendar_context:
        service = Service(context)
        owner = service.owner()
        group = {'id':'g1', 'name':'合成课程群', 'course_id':'course1', 'course':{'id':'course1','title':'合成计算机','course_ids':['bb:1']},
                 'trusted_senders':['teacher'], 'auto_extract':True, 'auto_apply':True}
        config = {'connection':'conn', 'revision':'r1','enabled':True, 'selected':[group], 'groups':[{'id':'g1','name':'合成课程群'}],
                  'interval_seconds':300, 'history_days':7, 'allow_ai':True, 'coverage':{}}
        service.save_source(owner,'qq',config)
        calls=[]
        async def no_sources(name,path='/snapshot',**kwargs):
            return httpx.Response(200,json={'status':'ready','data':{key:[] for key in ['courses','assignments','announcements','materials','timetable','posts','messages','lessons']},'pending':[]})
        study_context.api=calendar_context.api=no_sources
        apps={}
        for name,package,ctx in [('academic-assistant',study,study_context),('timetable',calendar,calendar_context)]:
            app=FastAPI();app.include_router(package.create_router(ctx));apps[name]=app
        async def api(name,path='/snapshot',**kwargs):
            calls.append((name,path,copy.deepcopy(kwargs)))
            if name=='notifications':return httpx.Response(200,json={'saved':True})
            if name not in apps:return await no_sources(name,path,**kwargs)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(apps[name]),base_url='http://fixture') as client:
                return await client.request(kwargs.get('method','GET'),path,json=kwargs.get('body'))
        context.api=api
        since=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
        cache=service.messages
        assert cache.ingest(owner,'qq','conn','g1',[raw(1)],since)==1
        first=cache.rows(owner,'qq','conn','g1')['items'][0]
        assert cache.ingest(owner,'qq','conn','g1',[raw(1,sent_at=first['sent_at'])],since)==0
        assert not cache.rows('other','qq','conn','g1')['items']
        assert not cache.rows(owner,'qq','conn','other')['items']
        output={'items':[]}
        ai_calls=[]
        def ai(**kwargs):
            ai_calls.append(kwargs)
            return {'content':json.dumps(output),'tools':[{'name':'group_submit','is_error':False}]}
        context.ai.run=ai
        def finding(message, **extra):
            return {'object_key':'hw1','kind':'assignment','title':'作业1','summary':'提交作业1','due_at':'2026-10-20T23:59:00+08:00',
                    'citations':[{'message_id':message['id'],'quote':message['text']}], **extra}
        output['items']=[finding(first)]
        task={'owner':owner,'source':'qq','group_id':'g1','manual':True}
        service._extract(task)
        item=service.items()['items'][0]
        assert item['automatic_ready'] and item['time_verified'] and item['status']=='pending'
        service._extract(task);assert len(ai_calls)==1, 'Unchanged content must not call AI'
        applied=await service.effects.apply(owner,item['id'],item['revision'],automatic=True)
        assert applied['target']['module']=='academic-assistant' and applied['receipt']['value']['after']['kind']=='plan'
        duplicate=await service.effects.apply(owner,item['id'],applied['revision'])
        assert duplicate['target']==applied['target']
        await service.effects.publish(owner,applied);await service.effects.publish(owner,service.current_item(owner,item['id']))
        assert sum(name=='notifications' for name,_,_ in calls)==1
        # Date change updates the existing local plan, with stable origin and exact revision.
        cache.ingest(owner,'qq','conn','g1',[raw(2,'作业1延期到2026年10月22日23:59截止')],since)
        message=cache.rows(owner,'qq','conn','g1')['items'][0]
        output['items']=[finding(message,target_id=item['id'],action='change',due_at='2026-10-22T23:59:00+08:00')]
        service._extract(task);changed=service.current_item(owner,item['id'])
        changed=await service.effects.apply(owner,item['id'],changed['revision'])
        assert changed['target']['id']==applied['target']['id']
        restored=await service.effects.undo(owner,item['id'],changed['revision'])
        assert restored['target']['id']==applied['target']['id'] and restored['undo_receipt']['after']['due_at'].startswith('2026-10-20')
        # Reapplying after undo must issue a new idempotency request, not reuse a stale receipt.
        changed=await service.effects.apply(owner,item['id'],restored['revision'])
        assert changed['receipt']['value']['after']['due_at'].startswith('2026-10-22')
        # Cancellation updates only the linked local item; undo restores the prior date/status.
        cache.ingest(owner,'qq','conn','g1',[raw('cancel','作业1已取消')],since)
        message=cache.rows(owner,'qq','conn','g1')['items'][0]
        output['items']=[finding(message,target_id=item['id'],action='cancel',due_at=None)]
        service._extract(task);cancelled=service.current_item(owner,item['id'])
        assert not cancelled['automatic_ready']
        cancelled=await service.effects.apply(owner,item['id'],cancelled['revision'])
        assert cancelled['receipt']['value']['after']['status']=='cancelled'
        undone=await service.effects.undo(owner,item['id'],cancelled['revision'])
        assert undone['undo_receipt']['after']['status']=='todo'
        # Keep a new applied revision for the following manual-edit conflict check.
        fresh={**changed,'target':undone['target'],'revision':uuid4().hex,'applied_content':None,'undo_receipt':undone['undo_receipt']}
        service.save_item(owner,fresh)
        changed=await service.effects.apply(owner,item['id'],fresh['revision'])
        target=changed['target']
        manual=await api('academic-assistant','/work/commands',method='POST',body={'action':'update','account_revision':owner,'request_id':uuid4().hex,
            'record_id':target['id'],'expected_revision':target['revision'],'item':{'title':'本人手动修改'}})
        assert manual.status_code==200, manual.text
        await rejected(service.effects.undo(owner,item['id'],changed['revision']))
        assert not context.store.read('operation:'+owner+':'+item['id']), 'Definite rejection leaves no uncertain request'
        # Trust uses stable IDs, never display names; invalid citations do not advance the cursor.
        cache.ingest(owner,'qq','conn','g1',[raw(3,'作业2在2026年10月23日23:59截止',sender='student')],since)
        message=cache.rows(owner,'qq','conn','g1')['items'][0]
        output['items']=[finding(message,object_key='hw2',title='作业2',due_at='2026-10-23T23:59:00+08:00')]
        output['items'][0]['citations'][0]['quote']='捏造依据'
        key=service.cursor_key(owner,'qq','conn','g1');before=context.store.read(key)
        rejects(lambda:service._extract(task),502);assert context.store.read(key)==before
        output['items'][0]['citations'][0]['quote']=message['text'];service._extract(task)
        assert not next(row for row in service.items()['items'] if row['object_key']=='hw2')['automatic_ready']
        assert not extraction.time_supported('2026-10-23T23:59:00+08:00','明天截止',None)
        assert not extraction.time_supported('2026-10-23T23:59:00+08:00','2026年10月23日截止',message['sent_at'])
        # An activity never auto applies, but explicit participation uses the real calendar API.
        cache.ingest(owner,'qq','conn','g1',[raw(4,'2026年10月24日19:00社团交流')],since)
        message=cache.rows(owner,'qq','conn','g1')['items'][0]
        output['items']=[finding(message,object_key='activity',kind='activity',title='社团交流',due_at=None,starts_at='2026-10-24T19:00:00+08:00')]
        service._extract(task);event=next(row for row in service.items()['items'] if row['kind']=='activity')
        assert not event['automatic_ready']
        await rejected(service.effects.apply(owner,event['id'],event['revision'],automatic=True))
        event=await service.effects.apply(owner,event['id'],event['revision']);assert event['target']['module']=='timetable'
        event=await service.effects.undo(owner,event['id'],event['revision']);assert event['target'] is None
        await service.effects.publish(owner,event)
        assert calls[-1][2]['body']['active'] is False
        # An in-flight result cannot survive pause, selection revision or account change.
        cache.ingest(owner,'qq','conn','g1',[raw(5)],since)
        for mutate,restore in [(lambda:service.cancelled.set(),lambda:service.cancelled.clear()),
                               (lambda:service.save_source(owner,'qq',{**config,'revision':'new'}),lambda:service.save_source(owner,'qq',config)),
                               (lambda:setattr(context.auth,'revision','other-account'),lambda:setattr(context.auth,'revision','synthetic-account-one'))]:
            def late(**kwargs):
                mutate();return {'content':'{"items":[]}','tools':[{'name':'group_submit','is_error':False}]}
            context.ai.run=late;before=context.store.read(key)
            rejects(lambda:service._extract(task));restore();assert context.store.read(key)==before
        rejects(lambda:service.queue('extract','qq',models.ExtractRequest(source='qq',group_id='unselected',allow_ai=True)),404)
        assert service.queued is None
        # Unknown timestamps stay unknown; late old messages and long payloads remain bounded.
        cache.ingest(owner,'qq','conn','g1',[raw('unknown',sent_at=None),raw('long','x'*64000)],since)
        batch=cache.batch(owner,'qq','conn','g1',before)
        assert any(row['sent_at'] is None for row in batch['messages'])
        assert max(len(row['text']) for row in batch['messages'])<=8000
        assert any(row['truncated'] for row in batch['messages'])
        context.ai.run=ai
        # Retained messages and accepted results survive construction/restart.
        restored_service=Service(context)
        assert restored_service.items()==service.items()
        assert restored_service.messages.rows(owner,'qq','conn','g1')['total']>=7
        service.pause('qq');service.start();service.close();assert not service.thread.is_alive()
        study.stop(study_context);calendar.stop(calendar_context)
    print('PASS: selected scope, incremental extraction, evidence/time/trust, real work/calendar commands, undo, edit conflicts, account/pause races and lifecycle')


def qq_check():
    rows=[{'message_id':n,'self_id':123,'group_id':5,'sender':{'user_id':9,'nickname':'teacher'},'message':[{'type':'text','data':{'text':'通知'}}]} for n in range(100)]
    config={'account':'123','base_url':'http://127.0.0.1:3000','selected':[{'id':'5'}],'coverage':{}}
    class Client:
        def __init__(self,*args,**kwargs):pass
        def login_info(self):return {'user_id':123}
        def group_history(self,gid):assert gid=='5';return rows
    with patch.object(qq,'QQClient',Client):
        first=qq.synchronize(config,{'access_token':'synthetic'},threading.Event())
        assert first['coverage']['5']['possible_gap'] and first['messages']['5'][0]['sent_at'] is None
        config['coverage']=first['coverage'];rows[:]=rows[-2:]
        assert qq.synchronize(config,{},threading.Event())['coverage']['5']['possible_gap'], 'Unfilled history gaps persist'
        config['account']='456'
        try:qq.synchronize(config,{},threading.Event())
        except qq.APIError as error:assert error.category=='account'
        else:raise AssertionError('Changed QQ account accepted')
    for address in ['https://127.0.0.1:3000','http://remote.example','http://127.0.0.1:3000/private']:
        try:qq.QQClient(address,'synthetic')
        except ValueError:pass
        else:raise AssertionError('Nonlocal QQ endpoint accepted')
    print('PASS: QQ account scope, unknown time, persistent 100-message coverage gaps and loopback-only transport')


if __name__=='__main__':
    asyncio.run(check());qq_check()
