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
catalog = sys.modules[package.__name__ + '.catalog']
assert catalog.current_semester({'elrc': {'data': {'metadata': {'semester': {'id': '2030-2031-2'}}}}}) == '2031-spring'


def check_term_matches():
    known = [course('timetable', 'current', '教务本学期', 'QA101', '2026-fall'),
             course('timetable', 'ambiguous', '重复开课', 'QA102', '2026-fall'),
             course('elrc', 'older', '重复开课', 'QA102', '2025-fall')]
    unknown = [course('blackboard', 'match', '名称不同但课程代码一致', 'QA101', '', status='active'),
               course('blackboard', 'ambiguous', '学期无法唯一确定', 'QA102', '', status='active'),
               course('blackboard', 'unmatched', '只有活跃标记', 'QA999', '', status='active'),
               course('blackboard', 'completed', '已结束课程', 'QA101', '', status='completed'),
               course('blackboard', 'unknown', '状态未知课程', 'QA101'),
               course('gradescope', 'unknown', '其他来源', 'QA101')]
    snapshots = {'timetable': {'data': validate_bundle({'courses': known})}, 'blackboard': {'data': validate_bundle({'courses': unknown})}}
    combined = catalog.combine(snapshots, [], '2026-fall')
    current = next(item for item in combined['courses'] if 'blackboard:match' in item['course_ids'])
    assert current['current'] and current['course_ids'] == ['timetable:current', 'blackboard:match']
    assert current['term_matches'] == [{'course_id': 'blackboard:match', 'term': '2026-fall', 'source_ids': ['timetable:current']}]
    assert current['sources'][-1]['term'] == '' and unknown[0]['term'] == '', 'Keep the original source record intact'
    for item in unknown[1:]:
        assert not next(group for group in combined['courses'] if item['id'] in group['course_ids'])['current']
    manual = catalog.combine(snapshots, [{'id': 'manual', 'title': '手动关联', 'course_ids': ['blackboard:match', 'gradescope:unknown']}], '2026-fall')
    assert not next(group for group in manual['courses'] if group['id'] == 'manual:manual')['current']
    unknown[0]['term'] = '2025-fall'
    explicit = catalog.combine(snapshots, [], '2026-fall')
    assert not next(group for group in explicit['courses'] if 'blackboard:match' in group['course_ids'])['current']


check_term_matches()


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
            selected = await client.post('/context',json={'context_ids':[]})
            assert selected.status_code == 200 and selected.json()['items'] == []
            assert (await client.post('/context',json={'course_id':'missing'})).status_code == 404
            assert (await client.post('/context',json={'context_ids':['unknown']})).status_code == 422
            async def changed_account(module,path='/snapshot',**kwargs):
                context.auth.revision += '-changed'
                return await api(module,path,**kwargs)
            context.api = changed_account
            assert (await client.post('/context',json={})).status_code == 409
            assert (await client.get('/snapshot')).status_code == 409


asyncio.run(check())
print('courses: public API aggregation, unavailable sources, semester matching, tri-state pending filters and manual grouping passed')
