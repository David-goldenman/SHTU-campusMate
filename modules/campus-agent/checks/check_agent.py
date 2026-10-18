import asyncio
import json
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI, HTTPException
from backend.services.campus.analysis import account_revision
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

packages = {identity: load(identity) for identity in ('mail','timetable','notifications','campus-agent')}
with ExitStack() as stack:
    contexts = {identity: stack.enter_context(sandbox(identity)) for identity in packages}
    apps = {}
    async def api(module, path='/snapshot', **kwargs):
        if module not in apps:
            return httpx.Response(404, json={'detail': 'Optional module unavailable'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[module]),base_url='http://modules.local') as client:
            return await client.request(kwargs.get('method','GET'),path,json=kwargs.get('body'))
    for identity, context in contexts.items():
        context.api = api
        context.modules = lambda: {'modules':[{'id':key,'name':key,'status':'ready','revision':'fixture'} for key in packages]}
        app = apps[identity] = FastAPI()
        app.include_router(packages[identity].create_router(context))
    agent = packages['campus-agent']._service
    agent.origin = 'http://127.0.0.1:17668/api/v1/modules/campus-agent'
    source = packages['mail']._source
    mail_context = contexts['mail']
    intelligence = packages['mail']._intelligence
    mail_context.store.write(intelligence.key('preferences'),intelligence.preferences() | {'shape':'required'})
    event_models = sys.modules[packages['campus-agent'].__name__ + '.service']
    calls = []
    def ai_run(**kwargs):
        calls.append(kwargs)
        task = next(iter(agent.jobs.values()))
        async def review():
            for identity in json.loads(kwargs['context'])['pending_mail']:
                value = await task.review_context(identity)
                required = 'required' in identity
                decision = {'bucket':'focus' if required else 'recommend','topic':'shape' if required else 'research','category':'合成安排','summary':'合成讲座摘要','reason':'引用活动原文',
                    'evidence':[{'source':'title','quote':value['notification']['title']}], 'event':{'title':value['notification']['title'],'event_type':'lecture','starts_at':'2030-10-18T14:00:00+08:00','ends_at':'2030-10-18T15:00:00+08:00','location':'教学楼','quote':value['notification']['body_text']}}
                await task.classify({'message_id':identity,'fingerprint':value['fingerprint'],'decision':decision})
        asyncio.run(review())
        return {'content':'合成检查完成','tools':[]}
    contexts['campus-agent'].ai.run = ai_run
    def seed(items):
        mail_context.store.write('snapshot',{'owner':source.owner(),'updated_at':None,'data':validate_bundle({'messages':items})})
        mail_context.store.write('bodies',{'owner':source.owner(),'value':{item['id']:{'body_text':item['body_text'],'body_html':'<p>合成正文</p>'} for item in items}})
    seed([])
    asyncio.run(agent.check())
    assert calls == [], 'Startup must baseline existing data without mass AI calls'
    items = [{'id':'mail:'+key,'title':title,'source':'mail','source_id':key,'body_text':prefix+'活动时间：2030年10月18日 14:00–15:00；地点：教学楼。','received_at':'2030-10-16T09:00:00+08:00','sender':'合成发件人','url':'https://example.edu'} for key,title,prefix in [('required','合成形策活动','本次活动计入形策考勤。'),('optional','合成科研讲座','欢迎有兴趣的同学参加。')]]
    seed(items)
    asyncio.run(agent.check())
    assert len(calls) == 1 and len(agent.proposals()) == 2
    assert agent.status()['last_run']['reviewed'] == 2
    required = next(item for item in agent.proposals() if item['source_id']=='mail:required')
    optional = next(item for item in agent.proposals() if item['source_id']=='mail:optional')
    assert required['state']=='pending' and optional['state']=='pending'
    async def verify():
        assert len((await api('timetable','/events')).json()['items']) == 0
        await agent.decide(required['id'],'accept')
        await agent.decide(optional['id'],'accept')
        await agent.decide(optional['id'],'accept')
        events = (await api('timetable','/events')).json()['items']
        assert len(events) == 2
        event = next(item for item in events if item['title']=='合成科研讲座')
        response = await api('timetable','/events/'+event['id'],method='PUT',body={**event,'title':'手动更改的名称'})
        assert response.status_code == 200
        imported = await api('timetable','/events/import',method='POST',body={**optional['event'],'origin_id':'campus-agent:'+optional['id'],'account_revision':account_revision(contexts['timetable'])})
        assert imported.json()['title']=='手动更改的名称'
        notices=(await api('notifications')).json()['items']
        assert len(notices)==2 and any(item['proposal_id']==optional['id'] for item in notices)
        task=event_models.Job(agent,account_revision(contexts['campus-agent']),{'mail':{'reads':['/message','/catalog/{kind}']}},[])
        assert task.selected_data({'messages':items})['messages']==[], 'Mail bodies outside this job must not enter model context through aggregate APIs'
        assert len(event_models.Job(agent,task.owner,{},['mail:required']).selected_data({'messages':items})['messages'])==1
        try:
            await task.read('mail','/agent/token')
            raise AssertionError('Undocumented read')
        except HTTPException as error:
            assert error.status_code==422
    asyncio.run(verify())
    before=len(calls)
    asyncio.run(agent.check())
    assert len(calls)==before, 'Classification writes must not trigger another AI run'
    third={**items[1],'id':'mail:external','source_id':'external','title':'外部复核的合成讲座'}
    seed([*items,third])
    mail_models=sys.modules[packages['mail'].__name__ + '.intelligence']
    prepared=intelligence.prepared(third['id'])
    decision={**intelligence.records()[1]['classification'],'evidence':[{'source':'title','quote':third['title']}],
              'event':{**optional['event'],'quote':third['body_text']}}
    decision={key:decision[key] for key in mail_models.Decision.model_fields if key in decision}
    intelligence.submit(mail_models.Submission(message_id=third['id'],fingerprint=prepared['fingerprint'],decision=decision))
    asyncio.run(agent.check())
    assert len(calls)==before and any(item['source_id']==third['id'] for item in agent.proposals()), 'Reuse standalone email reviews without another model call'
    mail_context.store.write('sync',{'owner':source.owner(),'status':'error','message':'合成网络故障'})
    asyncio.run(agent.check())
    mail_context.store.write('sync',{'owner':source.owner(),'status':'ready'})
    asyncio.run(agent.check())
    recovered=asyncio.run(api('notifications')).json()['items']
    assert next(item for item in recovered if item['id']=='service:mail')['title'].endswith('已恢复')
    event_count = len(asyncio.run(api('timetable','/events')).json()['items'])
    exceptions = [{**items[0], 'id':'mail:'+key, 'source_id':key, 'title':'合成非必修活动',
                   'body_text':'本次活动不计入形策考勤。活动时间：2030年10月18日 14:00–15:00；地点：教学楼。'}
                  for key in ('noncredit-filter', 'noncredit-focus')]
    seed([*items,third,*exceptions])
    for item, bucket in zip(exceptions, ('filter', 'focus')):
        prepared=intelligence.prepared(item['id'])
        result=intelligence.submit(mail_models.Submission(message_id=item['id'],fingerprint=prepared['fingerprint'],decision={
            **decision, 'bucket':bucket, 'topic':'shape', 'evidence':[{'source':'body_text','quote':'本次活动不计入形策考勤。'}],
            'event':{**optional['event'],'title':item['title'],'quote':item['body_text']}}))
        assert result['bucket']==bucket and not result['protected'], 'A negative recognition statement must not force focus'
    # Existing saved classifications may still have the old protected flag.
    reviews=mail_context.store.read(intelligence.key('reviews'))
    reviews[exceptions[1]['id']]['protected']=True
    mail_context.store.write(intelligence.key('reviews'), reviews)
    before=len(calls)
    asyncio.run(agent.check())
    assert len(calls)==before, 'Already-reviewed notices do not need another model call'
    assert len(asyncio.run(api('timetable','/events')).json()['items'])==event_count, 'Non-credit activities require user confirmation'
    assert not any(item['source_id']==exceptions[0]['id'] for item in agent.proposals()), 'Filtered notices stay filtered'
    assert next(item for item in agent.proposals() if item['source_id']==exceptions[1]['id'])['state']=='pending', 'Current source evidence overrides a saved protected flag'
    more = [{**items[1], 'id':'mail:queue'+str(index), 'source_id':'queue'+str(index), 'title':'合成讲座 '+str(index)} for index in range(7)]
    seed([*items, third, *exceptions, *more])
    asyncio.run(agent.check())
    assert agent.status()['pending_count'] >= 3, 'Every cached message stays queued beyond the first batch'
    for _ in range(4):
        asyncio.run(agent.check())
    assert agent.status()['pending_count'] == 0
    assert all(item['classification']['by']=='agent' for item in intelligence.records())
    notice = next(item for item in asyncio.run(api('notifications')).json()['items'] if any(c['id']=='mail:required' for c in item['citations']))
    asyncio.run(api('notifications','/'+notice['id']+'/read',method='PUT',body={'read':True}))
    # Updating preferences invalidates every cached review, including messages beyond the latest five.
    asyncio.run(api('mail','/preferences',method='PUT',body={**intelligence.preferences(),'requirements':'只关注合成的新偏好'}))
    for _ in range(5):
        asyncio.run(agent.check())
    assert all(not item['classification']['review_pending'] for item in intelligence.records())
    assert next(item for item in asyncio.run(api('notifications')).json()['items'] if item['id']==notice['id'])['read'], 'Rechecking unchanged mail preserves its read state'
    proposal = next(item for item in agent.proposals() if item['source_id']==more[0]['id'])
    asyncio.run(agent.decide(proposal['id'],'dismiss'))
    notices = asyncio.run(api('notifications')).json()['items']
    assert not any(any(c['id']==more[0]['id'] for c in item['citations']) for item in notices), 'Declining removes related activity reminders'
    asyncio.run(api('mail','/labels',method='POST',body={'message_id':more[1]['id'],'label':'已筛选活动','bucket':'filter'}))
    notices = asyncio.run(api('notifications')).json()['items']
    assert not any(any(c['id']==more[1]['id'] for c in item['citations']) for item in notices), 'Filtering a mail also filters earlier reminders'
    asyncio.run(agent.check())
    assert next(item for item in agent.proposals() if item['source_id']==more[1]['id'])['state']=='withdrawn'
    survey = event_models.Event(title='活动问卷', event_type='activity', starts_at='2030-10-18T14:00:00+08:00',quote='调查问卷提交截止：2030年10月18日 14:00。')
    try:
        event_models.grounded(survey,survey.quote)
        raise AssertionError('A survey deadline is not an activity start')
    except HTTPException as error:
        assert error.status_code==422
    try:
        event_models.grounded(event_models.Event(title='虚构日期',event_type='lecture',starts_at='2031-10-18T14:00:00+08:00',quote=items[0]['body_text']),items[0]['body_text'],items[0]['received_at'])
        raise AssertionError('Ungrounded date')
    except HTTPException as error:
        assert error.status_code==422
    async def remove_confirmed_event():
        events = (await api('timetable', '/events')).json()['items']
        event = next(item for item in events if item['origin_id'] == 'campus-agent:' + optional['id'])
        result = await api('timetable', '/commands', method='POST', body={
            'action': 'delete', 'request_id': '00000000-0000-4000-8000-000000000072',
            'account_revision': account_revision(contexts['timetable']), 'record_id': event['id'],
            'expected_revision': event['revision']})
        assert result.status_code == 200, result.text
        await agent.check()
        await agent.decide(optional['id'], 'accept')
        remaining = (await api('timetable', '/events')).json()['items']
        assert all(item['id'] != event['id'] for item in remaining), 'A deleted confirmed event stays deleted after background checks and replayed acceptance'
    asyncio.run(remove_confirmed_event())
    contexts['campus-agent'].auth.revision='other-account'
    assert agent.proposals()==[]
    agent.start();agent.close();assert not agent.thread.is_alive()
    for identity,package in packages.items():
        package.stop(contexts[identity])
print('campus agent: change coalescing, native tool flow, required vs optional events, confirmation, deduplication, manual edits, evidence, account isolation and lifecycle passed')
