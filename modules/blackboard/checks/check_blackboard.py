import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('blackboard')
reader = sys.modules[package.__name__ + '.reader']
at = datetime(2026,10,16,tzinfo=timezone.utc)
assert reader.availability({'available':'Yes'},at) == ('open',True)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'2099-01-01T00:00:00Z'}},at) == ('scheduled',False)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'bad-date'}},at) == ('unknown',None)
assert reader.availability(None,at) == ('unknown',None)
assert reader.activity('<div id="grades_wrapper"><div id="12" class="sortable_item_row submitted_item_row">Submitted</div><div id="13" class="sortable_item_row">未提交</div></div>') == {'_12_1':True,'_13_1':False}
for term in ['2026秋季学期', '2026-2027学年秋季学期']:
    courses = reader.portal('<div id="module:_185_1"><a href="/launcher?type=Course&amp;id=_9_1">PHYS1183 普通物理II-' + term + '</a></div>')
    assert courses['_9_1']['term'] == term


class Tree:
    def pages(self,url):
        return iter([{'id':'_1_1','title':'合成文件夹','contentHandler':{'id':'resource/x-bb-folder'},'hasChildren':True}, {'id':'_2_1','title':'合成资料','contentHandler':{'id':'resource/x-bb-file'}}])


issues = []
nodes = reader.contents(Tree(),'_9_1',issues)
assert len(nodes) == 2 and issues
items = reader.materials(nodes,'_9_1')
assert len(items) == 1 and items[0]['download_url'].startswith('/api/v1/modules/blackboard/file?')


class Submissions:
    def pages(self, url):
        if url.endswith('/users/me/courses'):
            return [{'courseId': '_9_1'}]
        if url.endswith('/contents'):
            return [{'id': f'_{number}_1', 'title': f'合成作业{number}', 'contentHandler': {'id': 'resource/x-bb-assignment'}, 'availability': {'available': 'Yes'}} for number in (11, 12, 13)]
        if url.endswith('/gradebook/columns'):
            return [{'id': f'_{number + 10}_1', 'contentId': f'_{number}_1'} for number in (11, 12, 13)]
        if url.endswith('/gradebook/users/me'):
            return [{'columnId': '_21_1', 'displayGrade': None}, {'columnId': '_23_1', 'displayGrade': {'score': 0}}]
        raise AssertionError(url)

    def json(self, method, url):
        assert method == 'GET' and url.endswith('/courses/_9_1')
        return {'name': '合成课程2026秋季学期', 'courseId': 'QA101'}

    def html(self, url):
        if '/myGrades?' in url:
            return '<div id="grades_wrapper"><div id="21" class="sortable_item_row">—</div><div id="22" class="sortable_item_row submitted_item_row">Submitted</div></div>'
        if '/announcement?' in url:
            return '<div id="announcementList"></div>'
        assert '/tabs/tabAction?' in url
        return '<div id="module:_185_1"></div>'


synced = reader.fetch(Submissions(), {})
assert [item['submitted'] for item in synced['assignments']] == [False, True, True]
assert synced['assignments'][2]['score'] == 0


async def check_cached_submissions():
    with sandbox('blackboard') as bb, sandbox('courses') as courses, sandbox('assignments') as assignments:
        app = FastAPI()
        app.include_router(package.create_router(bb), prefix='/blackboard')
        app.include_router(load('courses').create_router(courses), prefix='/courses')
        app.include_router(load('assignments').create_router(assignments), prefix='/assignments')
        data = validate_bundle({
            'courses': [course('blackboard', '_9_1', '合成课程', 'QA101', '2026-fall')],
            'assignments': [{'id': 'blackboard:' + name, 'source': 'blackboard', 'title': name, 'course_id': 'blackboard:_9_1', 'submitted': submitted, 'actionable': actionable}
                            for name, submitted, actionable in [('null', None, True), ('false', False, True), ('submitted', True, True), ('closed', None, False), ('unknown_open', None, None)]],
        })
        bb.store.write('snapshot', {'owner': package._source.owner(), 'data': data, 'updated_at': '2026-10-17T00:00:00Z'})
        bb.store.write('sync', {'owner': package._source.owner(), 'status': 'ready'})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                async def api(module, path='/snapshot', **options):
                    if module in {'blackboard', 'courses', 'assignments'}:
                        return await client.request(options.get('method', 'GET'), '/' + module + path, json=options.get('body'))
                    if module == 'timetable':
                        return httpx.Response(200, json={'data': validate_bundle({'metadata': {'semester': '2026-fall'}})})
                    if module == 'gradescope':
                        return httpx.Response(200, json={'data': validate_bundle({
                            'courses': [course('gradescope', 'qa', '另一课程', 'QA102', '2026-fall')],
                            'assignments': [{'id': 'gradescope:unknown', 'source': 'gradescope', 'title': '其他来源状态', 'course_id': 'gradescope:qa', 'submitted': None, 'actionable': True}],
                        })})
                    return httpx.Response(404)
                courses.api = assignments.api = api
                values = (await client.get('/blackboard/snapshot')).json()['data']['assignments']
                assert [item['submitted'] for item in values] == [False, False, True, False, False]
                assert bb.store.read('snapshot')['data']['assignments'][0]['submitted'] is None, 'Reading normalizes the response without rewriting cached source data'
                pending = (await client.get('/courses/catalog/assignments?current=true&pending=true')).json()['items']
                assert {item['id'] for item in pending} == {'blackboard:null', 'blackboard:false'}
                overview = (await client.get('/assignments/snapshot')).json()
                assert {item['id'] for item in overview['pending']} == {'blackboard:null', 'blackboard:false'}
                assert next(item for item in overview['data']['assignments'] if item['id'] == 'gradescope:unknown')['submitted'] is None
                response = await client.post('/courses/context', json={'context_ids': ['assignments:blackboard:null']})
                assert response.status_code == 200, response.text
                assert response.json()['items'][0]['submitted'] is False
                bb.auth.revision = 'different-account'
                assert (await client.get('/blackboard/snapshot')).json()['data']['assignments'] == []
        finally:
            package.stop(bb)


asyncio.run(check_cached_submissions())
print('blackboard: null means unsubmitted in sync/cache/catalog/pending/AI context; submitted and zero-score evidence, availability, account isolation and file paths passed')
