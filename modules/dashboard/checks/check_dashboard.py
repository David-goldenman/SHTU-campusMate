import asyncio
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from checks.module_support import load, sandbox

package = load('dashboard')
data = {'courses':[{'id':'current','current':True,'course_ids':['x:1']},{'id':'old','current':False,'course_ids':['x:2']}], 'materials':[{'course_id':'x:1'},{'course_id':'x:2'}], 'metadata':{'source_metadata':{'one':{'status':'ready'},'two':{'status':'error'}}}}
result = package.summarize(data,[{'id':'a','due_at':'2026-10-01'},{'id':'b','due_at':None}],[{'id':'read','read':True},{'id':'unread','read':False}])
assert result['stats'] == {'courses':1,'pending':2,'materials':1,'ready_sources':1}
assert len(result['upcoming']) == 1 and [item['id'] for item in result['notifications']] == ['unread']
assert package.summarize(data, [{'id': 'estimate', 'due_at': '2027-01-17', 'due_default': True}], [])['upcoming'] == []
print('dashboard: current-course statistics, known deadlines, partial sources and unread notices passed')

async def check_pending_contract():
    with sandbox('dashboard') as context:
        pending = [{'id':str(i),'due_at':'2026-10-20T23:59:00+08:00'} for i in range(7)] + [{'id':'undated','due_at':None}]
        assignment_status, coverage = 200, {'status': 'ready', 'sources': []}
        async def api(name, path='/snapshot', **kwargs):
            if name == 'assignments':
                return httpx.Response(assignment_status, json={'pending': pending, 'coverage': coverage})
            return httpx.Response(200,json={
                'courses':{'status':'ready','data':{**data,'issues':[]}},
                'assignments':{'pending':pending},'notifications':{'items':[]},'timetable':{'calendar':{'days':[]}},
            }[name])
        context.api=api
        app=FastAPI();app.include_router(package.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://fixture') as client:
            value=(await client.get('/snapshot')).json()
            assert value['pending'] == pending, 'Priority counts include items beyond the five-item preview and unknown dates'
            assert len(value['upcoming']) == 5 and value['stats']['pending'] == 8
            light = (await client.get('/summary')).json()
            assert light['pending'] == pending and light['stats'] == value['stats']
            assert set(light['data']) == {'metadata', 'issues'}
            assert 'courses' in value['data'], 'The full snapshot remains compatible'
            expanded = {**value, 'data': {**value['data'], 'lessons': [{'body_text': 'large transcript ' * 10000}]}}
            assert len(str(package.compact(expanded))) < 3000, 'Unrelated material text must not reach the homepage'
            for assignment_status in (404, 503):
                value = (await client.get('/snapshot')).json()
                assert value['stats']['pending'] is None and value['assignment_coverage']['status'] == 'unavailable'
                assert value['stats']['courses'] == 1, 'Other modules keep working'
                assert (await client.get('/summary')).json()['stats']['pending'] is None
            assignment_status = 200
            coverage = {'status': 'partial', 'sources': [{'id': 'blackboard', 'status': 'cached'}]}
            value = (await client.get('/snapshot')).json()
            assert value['stats']['pending'] == 8 and value['assignment_coverage'] == coverage
            pending = []
            coverage = {'status': 'unavailable', 'sources': []}
            assert (await client.get('/snapshot')).json()['stats']['pending'] is None
            coverage = {'status': 'ready', 'sources': []}
            assert (await client.get('/snapshot')).json()['stats']['pending'] == 0, 'A confirmed empty result still shows zero'

asyncio.run(check_pending_contract())
