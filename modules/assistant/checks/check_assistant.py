import asyncio
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('assistant')


async def check():
    with sandbox('assistant') as context:
        raw = course('gradescope','1','合成课程','CS100','Fall 2026','https://www.gradescope.com/courses/1')
        data = validate_bundle({'courses':[{'id':'group:1','source':'catalog','title':'合成课程','term':'2026-fall','current':True,'course_ids':[raw['id']],'sources':[raw]}]})
        async def api(module,path='/snapshot',**kwargs):
            return httpx.Response(200,json={'data':data})
        context.api = api
        context.ai.result['content'] = {'text':'合成回答','insufficient_context':False,'citation_ids':['courses:gradescope:1']}
        app = FastAPI(); app.include_router(package.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post('/chat',json={'message':'课程介绍'})).status_code == 200
            assert len((await client.get('/chat')).json()['messages']) == 2
            assert (await client.get('/chat?course_id=group:1')).json()['messages'] == []
            context.ai.result['content']['citation_ids'] = ['invented']
            assert (await client.post('/chat',json={'message':'错误引用'})).status_code == 502
            assert len((await client.get('/chat')).json()['messages']) == 2
            empty = (await client.post('/generate',json={'prompt':'空范围','context_ids':[]})).json()
            assert empty['insufficient_context'] and empty['citations'] == []
            context.auth.revision = 'new-account'
            assert (await client.get('/chat')).json()['messages'] == []
            assert (await client.delete('/chat')).status_code == 200


asyncio.run(check())
print('assistant: verified citations, isolated course histories, failed-answer preservation, empty selections and account changes passed')
