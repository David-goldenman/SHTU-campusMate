"""Synthetic end-to-end tools -> public calendar API and local learning records."""
import asyncio
import copy
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
from backend.services.campus.analysis import account_revision
from backend.services.campus.data import validate_bundle

study, timetable = load('academic-assistant'), load('timetable')
lesson = {'id':'timetable:math','source':'timetable','title':'合成数学','weekday':1,'period_start':3,'period_end':4,'weeks':[1,2,3],'location':'A101'}
fixture = validate_bundle({'timetable':[lesson], 'metadata':{'semester':'合成学期','semester_id':'test-1','units':13,'periods':[
    {'period':3,'start':'10:00','end':'10:45'},{'period':4,'start':'11:00','end':'11:45'}]}})
assignment = {'id':'blackboard:hw','source':'blackboard','title':'合成作业','submitted':False,'actionable':True}


async def rejected(operation, status=422):
    try:
        await operation
        raise AssertionError('An invalid or unauthorized edit was accepted')
    except HTTPException as error:
        assert error.status_code == status, (error.status_code, error.detail)


async def check():
    with sandbox('timetable') as calendar_context, sandbox('academic-assistant') as context:
        notices, notices_available = [], True
        async def sources(name, path='/snapshot', **options):
            if name == 'notifications':
                if not notices_available:
                    return httpx.Response(404, json={})
                notices.append(options['body'])
                return httpx.Response(200, json={'saved':True})
            if name == 'assignments':
                return httpx.Response(200, json={'data':{'assignments':[assignment]},'pending':[assignment]})
            events = [{'id':'eams:exam','title':'外部考试','source':'eams','due_at':'2026-10-19T10:15:00+08:00','ends_at':'2026-10-19T11:15:00+08:00','start_time':'10:15'}] if name == 'eams' else []
            return httpx.Response(200, json={'status':'ready','data':validate_bundle({'assignments':events}),'updated_at':datetime.now(timezone.utc).isoformat()})
        calendar_context.api = sources
        app = FastAPI(); app.include_router(timetable.create_router(calendar_context))
        source = timetable._source
        calendar_context.store.write('snapshot', {'owner':source.owner(),'data':fixture,'updated_at':datetime.now(timezone.utc).isoformat()})
        calendar_context.store.write('sync', {'owner':source.owner(),'status':'ready'})
        raw = copy.deepcopy(calendar_context.store.read('snapshot'))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://fixture') as client:
                await client.put('/calendar-settings',json={'week_one':'2026-10-19'})
                async def api(name,path='/snapshot',**options):
                    if name == 'timetable':
                        return await client.request(options.get('method','GET'), path, json=options.get('body'))
                    return await sources(name,path,**options)
                context.api = api
                study_app=FastAPI();study_app.include_router(study.create_router(context))
                work = study._agent.work
                async def query_task(message, area='timetable', q='', week='2026-10-19'):
                    task=study.Task(context,message,work)
                    await task.query(study.Query(area=area,q=q,week_start=week))
                    return task
                def edit(task,action,**values):
                    return task.schedule_edit(study.ScheduleEdit(action=action,quote=task.message,**values))
                async def schedule(week='2026-10-19'):
                    return (await client.get('/schedule',params={'week_start':week})).json()
                async def classes(week='2026-10-19'):
                    return [row for day in (await schedule(week))['calendar']['days'] for row in day['events'] if row['event_type']=='class']

                task=study.Task(context,'添加合成习题课，10月19日第3至4节',work)
                fields={'title':'合成习题课','event_type':'tutorial','date':'2026-10-19','period_start':3,'period_end':4}
                created=await edit(task,'create',event=fields)
                result=created['change']; identity=result['after']['id']
                assert result['applied'] and result['conflicts']['complete']
                assert any(row['second_id']=='eams:exam' or row['first_id']=='eams:exam' for row in result['conflicts']['items'])
                assert (await edit(task,'create',event=fields))==created
                assert len((await client.get('/events')).json()['items'])==1
                old_events=calendar_context.store.read('events:'+source.owner())
                old_events[0].pop('revision')
                calendar_context.store.write('events:'+source.owner(),old_events)
                legacy_edit=await client.post('/commands',json={'action':'update','request_id':uuid4().hex,'account_revision':account_revision(calendar_context),
                    'record_id':identity,'expected_revision':'','event':{'location':'B202'}})
                assert legacy_edit.status_code==200 and legacy_edit.json()['after']['revision'], 'Legacy personal records acquire a revision on first edit'
                for message in ['不要添加合成习题课','如果添加合成习题课会怎样','我只想了解如何添加合成习题课','原文写着：添加合成习题课']:
                    blocked=study.Task(context,message,work)
                    await rejected(edit(blocked,'create',event=fields))
                await rejected(task.schedule_edit(study.ScheduleEdit(action='create',quote='添加合成习题课',event=fields)))
                stale=await query_task('把合成习题课改到晚上7点')
                manual={**fields,'title':'合成习题课手动编辑'}
                assert (await client.put('/events/'+identity,json=manual)).status_code==200
                await rejected(edit(stale,'update',record_id=identity,event={'starts_at':'2026-10-19T19:00:00+08:00'}),409)
                update=await query_task('把合成习题课手动编辑改到晚上7点')
                changed=await edit(update,'update',record_id=identity,event={'starts_at':'2026-10-19T19:00:00+08:00','ends_at':'2026-10-19T20:00:00+08:00'})
                assert changed['change']['after']['period_start'] is None
                delete=await query_task('删除合成习题课手动编辑')
                await edit(delete,'delete',record_id=identity)
                assert not (await client.get('/events')).json()['items']

                original=(await classes())[0]
                leave=await query_task('合成数学10月19日请假')
                await edit(leave,'adjust_class',record_id=original['id'],adjustment={'action':'leave'})
                assert (await classes())[0]['status']=='leave'
                assert (await classes('2026-10-26'))[0]['status']=='scheduled'
                restore=await query_task('恢复合成数学10月19日安排')
                await edit(restore,'adjust_class',record_id=original['id'],adjustment={'action':'restore'})
                move=await query_task('合成数学从10月19日起后续都调课到下一周周二第5至6节')
                moved=await edit(move,'adjust_class',record_id=original['id'],adjustment={'action':'move','scope':'following','to_date':'2026-10-27','period_start':5,'period_end':6})
                assert moved['change']['affected_count']==3 and len(moved['change']['checked_weeks'])==3
                assert not moved['change']['conflicts']['complete'], 'Unknown lesson clocks cannot claim a complete conflict check'
                assert (await classes())[0]['status']=='moved'
                assert any(row['date']=='2026-10-27' and row['status']=='rescheduled' for row in await classes('2026-10-26'))
                restore=await query_task('恢复合成数学从10月19日起后续全部安排')
                await edit(restore,'adjust_class',record_id=original['id'],adjustment={'action':'restore','scope':'following'})
                location=await query_task('合成数学10月19日修改地点为B101')
                await edit(location,'adjust_class',record_id=original['id'],adjustment={'action':'move','location':'B101'})
                assert len(await classes())==1 and (await classes())[0]['location']=='B101'
                wrong_scope=await query_task('合成数学10月19日请假')
                await rejected(edit(wrong_scope,'adjust_class',record_id=original['id'],adjustment={'action':'leave','scope':'following'}))
                unread=study.Task(context,'合成数学10月19日请假',work)
                await rejected(edit(unread,'adjust_class',record_id=original['id'],adjustment={'action':'leave'}))
                assert calendar_context.store.read('snapshot')==raw
                rules=calendar_context.store.read(timetable.adjustments_key(source))
                calendar_context.store.write('snapshot',{**raw,'data':{**raw['data'],'metadata':{**raw['data']['metadata'],'semester_id':'new'}}})
                assert not (await schedule())['adjustments']
                calendar_context.store.write('snapshot',raw)
                assert (await schedule())['adjustments']==rules

                finish=study.Task(context,'解释向量加法',work)
                assert (await finish.finish(study.Answer(basis='general',citations=[])))['accepted']
                await rejected(study.Task(context,'我的课表',work).finish(study.Answer(citations=[])))

                async def work_edit(task, action, **values):
                    return await task.work_edit(study.WorkEdit(action=action,quote=task.message,**values))
                progress=await query_task('把合成作业标记为已完成',area='assignments')
                done=await work_edit(progress,'set_assignment',record_id=assignment['id'],item={'status':'done'})
                assert done['change']['after']['status']=='done' and assignment['submitted'] is False
                assert (await work_edit(progress,'set_assignment',record_id=assignment['id'],item={'status':'done'}))==done
                start=await query_task('开始做合成作业',area='assignments')
                await rejected(work_edit(start,'set_assignment',record_id=assignment['id'],item={'status':'done'}))
                bad=await query_task('不要把合成作业标记为完成',area='assignments')
                await rejected(work_edit(bad,'set_assignment',record_id=assignment['id'],item={'status':'done'}))
                reminder=study.Task(context,'提醒我合成复习，10月20日19点',work)
                reminder_fields={'kind':'reminder','title':'合成复习','due_at':'2026-10-20T19:00:00+08:00'}
                saved=await work_edit(reminder,'create',item=reminder_fields)
                await work.deliver_due(datetime(2026,10,20,10,tzinfo=timezone.utc));assert not notices
                notices_available=False
                await work.deliver_due(datetime(2026,10,20,12,tzinfo=timezone.utc));assert not notices
                assert any(row.get('delivery_error') for row in work.snapshot()['items'])
                notices_available=True
                await work.deliver_due(datetime(2026,10,20,12,tzinfo=timezone.utc))
                await work.deliver_due(datetime(2026,10,21,12,tzinfo=timezone.utc));assert len(notices)==1
                cancelled=study.Task(context,'设置合成取消提醒，10月22日19点',work)
                cancel_saved=await work_edit(cancelled,'create',item={**reminder_fields,'title':'合成取消提醒','due_at':'2026-10-22T19:00:00+08:00'})
                cancel_task=await query_task('取消合成取消提醒',area='workspace')
                await work_edit(cancel_task,'update',record_id=cancel_saved['change']['after']['id'],item={'status':'cancelled'})
                await work.deliver_due(datetime(2026,10,23,12,tzinfo=timezone.utc));assert len(notices)==1
                plan=study.Task(context,'保存合成复习计划',work)
                planned=await work_edit(plan,'create',item={'kind':'plan','title':'合成复习计划','notes':'1. 理解定义\n2. 做三道练习'})
                plan_id=planned['change']['after']['id']
                outdated=await query_task('修改合成复习计划',area='workspace')
                current=next(row for row in work.snapshot()['items'] if row['id']==plan_id)
                await work.command(study.WorkCommand(action='update',request_id=uuid4().hex,account_revision=account_revision(context),record_id=plan_id,expected_revision=current['revision'],item={'notes':'手动修改'}))
                await rejected(work_edit(outdated,'update',record_id=plan_id,item={'notes':'旧内容'}),409)
                deletion=await query_task('删除合成复习计划',area='workspace')
                await work_edit(deletion,'delete',record_id=plan_id)
                assert all(row['id']!=plan_id for row in work.snapshot()['items'])

                # Successful writes remain in history even if the model fails afterward.
                loop=asyncio.get_running_loop()
                def failed_model(**options):
                    token=options['plugin_env']['CAMPUS_PLUGIN_STUDY_TOKEN']
                    response=asyncio.run_coroutine_threadsafe(study_client.post('/tools/work-edit',
                        json={'action':'create','quote':'保存合成回执计划','item':{'kind':'plan','title':'合成回执计划','notes':'内容'}},
                        headers={'Authorization':'Bearer '+token}),loop).result(5)
                    assert response.status_code==200, response.text
                    raise RuntimeError('synthetic provider failure')
                context.ai.run=failed_model
                async with httpx.AsyncClient(transport=httpx.ASGITransport(study_app),base_url='http://fixture') as study_client:
                    assert (await study_client.post('/tools/capabilities')).status_code==401
                    response=await study_client.post('/chat',json={'message':'保存合成回执计划'})
                    assert response.status_code==200 and response.json()['changes'][0]['applied']
                    assert len((await study_client.get('/chat')).json()['messages'])==2
                context.auth.revision='another-account';calendar_context.auth.revision='another-account'
                await rejected(work_edit(reminder,'create',item=reminder_fields),409)
                assert work.snapshot()['items']==[]
                assert not (await schedule())['adjustments']
        finally:
            study.stop(context);timetable.stop(calendar_context)


asyncio.run(check())
print('study actions: calendar CRUD, class overrides, scopes/conflicts, stale/account/consent guards, learning progress, reminder delivery and durable receipts passed')
