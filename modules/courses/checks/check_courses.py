import asyncio
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('courses')


async def check():
    with sandbox('courses') as context:
        sources = {
            'gradescope': {'status':'ready','data':validate_bundle({'courses':[course('gradescope','1','合成课程','CS 100','Fall 2026','https://www.gradescope.com/courses/1')], 'assignments':[{'id':'gradescope:a','source':'gradescope','title':'待办','course_id':'gradescope:1','actionable':True,'submitted':False},{'id':'gradescope:b','source':'gradescope','title':'未知','course_id':'gradescope:1','actionable':True,'submitted':None}]})},
            'timetable': {'status':'ready','data':validate_bundle({'courses':[course('timetable','2','教务课程','CS100','2026-2027学年秋季','https://eams.shanghaitech.edu.cn/')],'metadata':{'semester':'2026-2027学年秋季'}})}
        }

        async def api(module,path='/snapshot',**kwargs):
            if kwargs.get('method') == 'POST':
                return httpx.Response(202,json={'queued':True})
            if module == 'elrc':
                return httpx.Response(200,text='malformed-json')
            return httpx.Response(200,json=sources[module]) if module in sources else httpx.Response(404)

        context.api = api
        app = FastAPI()
        app.include_router(package.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            data = (await client.get('/snapshot')).json()
            assert len(data['data']['courses']) == 1 and 'elrc' in data['unavailable']
            merged = data['data']['courses'][0]
            assert merged['current'] and len(merged['course_ids']) == 2
            pending = (await client.get('/catalog/assignments?current=true&pending=true')).json()
            assert [item['id'] for item in pending['items']] == ['gradescope:a']
            assert (await client.get('/course?course_id=missing')).status_code == 404
            assert (await client.get('/catalog/posts?pending=true')).status_code == 400
            assert (await client.put('/groups',json={'groups':[{'id':'one','title':'合成分组','course_ids':['gradescope:1','timetable:2']}]})).status_code == 200
            assert (await client.get('/snapshot')).json()['data']['courses'][0]['title'] == '合成分组'
            assert (await client.put('/groups',json={'groups':[{'id':'bad','title':'错误分组','course_ids':['gradescope:1','gradescope:1']}]})).status_code == 422
            assert (await client.post('/sync')).status_code == 202


asyncio.run(check())
print('courses: public API aggregation, unavailable sources, semester matching, tri-state pending filters and manual grouping passed')
