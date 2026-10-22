"""AI writes use the same public assignment API and actual read revisions."""
import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI, HTTPException
from checks.module_support import load, sandbox

study, assignments = load('academic-assistant'), load('assignments')


async def check():
    with sandbox('academic-assistant') as context, sandbox('assignments') as assignment_context:
        data={'courses':[{'id':'c','title':'合成课程','current':True,'course_ids':['bb:c']}],
              'assignments':[{'id':'blackboard:team','source':'blackboard','title':'合成团队作业','course_id':'bb:c','submitted':False,'availability':'open'}],
              'materials':[],'metadata':{}}
        async def course_api(*args,**kwargs):
            return httpx.Response(200,json={'status':'ready','data':copy.deepcopy(data)})
        assignment_context.api=course_api
        app=FastAPI();app.include_router(assignments.create_router(assignment_context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            async def api(name,path='/snapshot',method='GET',body=None,**kwargs):
                assert name=='assignments'
                return await client.request(method,path,json=body)
            context.api=api
            async def task(message):
                value=study.Task(context,message)
                await value.query(study.Query(area='assignments'))
                return value
            def change(value,status='waived',**kwargs):
                return value.assignment_handling(study.AssignmentHandling(record_id='blackboard:team',status=status,reason='team_submitted' if status=='waived' else None,quote=value.message,**kwargs))
            for message in ('不要把合成团队作业标记无需我提交','如果队友提交了，把合成团队作业标记无需我提交','把合成团队作业标记无需我提交，队友还没提交','队友准备提交，把合成团队作业标记无需我提交'):
                value=await task(message)
                try:
                    await change(value);raise AssertionError('Ambiguous/negative edit accepted')
                except HTTPException as error:assert error.status_code==422
            value=await task('合成团队作业队友已经提交了，标记无需我提交')
            stale=await task('合成团队作业队友已经提交了，标记无需我提交')
            saved=await change(value)
            assert saved['change']['applied'] and saved['change']['after']['status']=='waived'
            assert await change(value)==saved and len(value.changes)==1
            assert (await client.get('/snapshot')).json()['pending']==[]
            try:
                await change(stale);raise AssertionError('Stale edit accepted')
            except HTTPException as error:assert error.status_code==409
            restore=await task('恢复合成团队作业的提醒')
            assert (await change(restore,'required'))['change']['after']['status']=='required'
            snapshot=(await client.get('/snapshot')).json()
            assert len(snapshot['pending'])==1 and snapshot['pending'][0]['submitted'] is False
            assert 'study_assignment_handling' in Path(study.__file__).parents[1].joinpath('harness/index.js').read_text(encoding='utf-8')


asyncio.run(check())
print('AI assignment handling: actual public API, explicit team evidence, negative instructions, idempotence, source truth, restoration and stale version passed')
