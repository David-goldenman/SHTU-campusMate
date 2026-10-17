import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI, HTTPException
from backend.services.campus import SourceError, course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('blackboard')
reader = sys.modules[package.__name__ + '.reader']
at = datetime(2026,10,16,tzinfo=timezone.utc)
assert reader.availability({'available':'Yes'},at) == ('open',True)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'2099-01-01T00:00:00Z'}},at) == ('scheduled',False)
assert reader.availability({'available':'Yes','adaptiveRelease':{'start':'bad-date'}},at) == ('unknown',None)
assert reader.availability(None,at) == ('unknown',None)
assert {key: value['submitted'] for key, value in reader.activity('<div id="grades_wrapper"><div id="12" class="sortable_item_row submitted_item_row">Submitted</div><div id="13" class="sortable_item_row"><span class="activityType">未提交</span></div></div>').items()} == {'_12_1':True,'_13_1':False}
for term in ['2026秋季学期', '2026-2027学年秋季学期', '2026 秋', '2026秋', '2026年秋季']:
    courses = reader.portal('<div id="module:_185_1"><a href="/launcher?type=Course&amp;id=_9_1">PHYS1183 普通物理II-' + term + '</a></div>')
    assert courses['_9_1']['term'] == term
english = reader.portal('<div id="module:_185_1"><a href="/launcher?type=Course&amp;id=_9_1">EE115B 数字电路 【2026 Spring】</a></div>')
assert english['_9_1']['term'] == '2026 Spring'


class Tree:
    def pages(self,url):
        return iter([{'id':'_1_1','title':'合成文件夹','contentHandler':{'id':'resource/x-bb-folder'},'hasChildren':True}, {'id':'_2_1','title':'合成资料','contentHandler':{'id':'resource/x-bb-file'}}])


issues = []
nodes = reader.contents(Tree(),'_9_1',issues)
assert len(nodes) == 2 and issues
items = reader.materials(nodes,'_9_1')
assert len(items) == 1 and items[0]['download_url'].startswith('/api/v1/modules/blackboard/file?')

course_item = {'id':'blackboard:_9_1','source_id':'_9_1','url':'https://elearning.shanghaitech.edu.cn:8443/webapps/blackboard/execute/launcher?type=Course&id=_9_1'}
page = '<div id="announcementList"><li id="_11_1"><h3 class="item">开学通知</h3><div class="details"><div class="vtbegenerated">第一周停课。</div></div></li><li id="_12_1"><div class="details"><div class="vtbegenerated">缺少标题</div></div></li></div>'
announcements = reader.announcements(page,course_item)
assert len(announcements) == 1 and announcements[0]['id'] == 'blackboard:_9_1:_11_1' and announcements[0]['title'] == '开学通知' and announcements[0]['body_text'] == '第一周停课。'
assert reader.announcements('<html><body>系统维护</body></html>',course_item) is None
assert reader.announcements('<div id="announcementForm"></div>',course_item) == []


class Remote:
    def __init__(self,announcement):
        self.announcement = announcement

    def pages(self,url):
        if '/terms' in url:
            return iter([{'id':'_113_1','name':'2026-2027学年秋季学期'},{'id':'_114_1','name':'2026-2027学年春季学期'},{'id':'_115_1'}])
        return iter([{'courseId':'_9_1'}]) if url.endswith('/users/me/courses') else iter([])

    def json(self,method,url,**kwargs):
        return {'name':'数字电路 【2026 Spring】','courseId':'EE123','termId':'_113_1'}

    def html(self,url):
        if 'announcement' in url:
            if isinstance(self.announcement,Exception):
                raise self.announcement
            return self.announcement
        return '<div id="grades_wrapper"></div>' if 'mygrades' in url else '<html></html>'


old = {'id':'blackboard:_9_1:_11_1','source':'blackboard','course_id':'blackboard:_9_1','title':'旧公告','body_text':'','url':course_item['url']}
unreadable = reader.fetch(Remote(HTTPException(403,'forbidden')),{'announcements':[old],'courses':[]})
assert unreadable['announcements'] == [old] and not unreadable['issues'] and unreadable['courses'][0]['title'] == '数字电路 【2026 Spring】'
changed = reader.fetch(Remote('<html><body>系统维护</body></html>'),{'announcements':[old],'courses':[]})
assert changed['announcements'] == [old] and not changed['issues']
broken = reader.fetch(Remote(RuntimeError('unexpected page')),{'announcements':[old],'courses':[]})
assert broken['announcements'] == [old] and not broken['issues']
readable = reader.fetch(Remote(page),{'announcements':[old],'courses':[]})
assert [item['title'] for item in readable['announcements']] == ['开学通知'] and not readable['issues']
assert readable['courses'][0]['term'] == '2026-2027学年秋季学期' and readable['courses'][0]['semester'] == '2026-fall'


class Submissions:
    def pages(self, url):
        if url.endswith('/users/me/courses'):
            return [{'courseId': '_9_1'}]
        if '/terms' in url:
            return []
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
        if '/uploadAssignment?' in url:
            return '<span id="pageTitleText">上载作业：合成作业</span><form id="uploadAssignmentFormId"></form>'
        if '/myGrades?' in url:
            return '<div id="grades_wrapper"><div id="21" class="sortable_item_row">—</div><div id="22" class="sortable_item_row submitted_item_row">Submitted</div></div>'
        if '/announcement?' in url:
            return '<div id="announcementList"></div>'
        assert '/tabs/tabAction?' in url
        return '<div id="module:_185_1"></div>'


synced = reader.fetch(Submissions(), {})
assert [item['submitted'] for item in synced['assignments']] == [False, True, True]
assert synced['assignments'][2]['score'] == 0


HISTORY = '''<span id="pageTitleText">复查提交历史记录: 合成报告</span>
<div id="currentAttempt"><div class="attemptHeader"><span class="dateStamp">26-9-30 下午3:12</span></div>
<div id="currentAttempt_submission"><h4>提交</h4><ul class="filesList"><li>synthetic.pdf</li></ul></div></div>'''
assert reader.submission_history(HISTORY)['submitted'] is True
assert reader.submission_history(HISTORY.replace('复查提交历史记录', 'Review Submission History'))['submitted'] is True
assert reader.submission_history(HISTORY.replace('26-9-30 下午3:12', '草稿'))['submission_status'] == 'draft'
assert reader.submission_history('<span id="pageTitleText">上载作业</span><form id="uploadAssignmentFormId"><input type="file"></form>')['submitted'] is False
try:
    reader.submission_history('<div>Unable to read assignment</div>')
except SourceError:
    pass
else:
    raise AssertionError('Unrecognized pages must not become unsubmitted records')


class HiddenGradeColumns(Submissions):
    def pages(self, url):
        if url.endswith('/gradebook/columns') or url.endswith('/gradebook/users/me'):
            return []
        return super().pages(url)

    def html(self, url):
        if '/uploadAssignment?' in url:
            assert 'mode=view' in url and 'course_id=_9_1' in url and 'action=submit' not in url
            if 'content_id=_11_1' in url:
                return HISTORY
            if 'content_id=_12_1' in url:
                return '<span id="pageTitleText">上载作业</span><form id="uploadAssignmentFormId"></form>'
            raise SourceError('Synthetic history unavailable')
        return super().html(url)


hidden = reader.fetch(HiddenGradeColumns(), {})
assert [item['submitted'] for item in hidden['assignments']] == [True, False, None]
assert [item['submission_evidence'] for item in hidden['assignments']] == ['submission_history', 'submission_history', 'unavailable']
assert len(hidden['issues']) == 1


class NeedsGrading(Submissions):
    def pages(self, url):
        if url.endswith('/gradebook/users/me'):
            return [{'columnId': '_21_1', 'status': 'NeedsGrading'}, {'columnId': '_23_1', 'status': 'Graded'}]
        return super().pages(url)


assert all(item['submitted'] for item in reader.fetch(NeedsGrading(), {})['assignments'])


async def check_cached_submissions():
    with sandbox('blackboard') as bb, sandbox('courses') as courses, sandbox('assignments') as assignments:
        app = FastAPI()
        app.include_router(package.create_router(bb), prefix='/blackboard')
        app.include_router(load('courses').create_router(courses), prefix='/courses')
        app.include_router(load('assignments').create_router(assignments), prefix='/assignments')
        data = validate_bundle({
            'courses': [course('blackboard', '_9_1', '合成课程', 'QA101', '', status='active'),
                        course('blackboard', '_10_1', '另一合成课程2026 秋', 'QA102')],
            'assignments': [{'id': 'blackboard:' + name, 'source': 'blackboard', 'title': name, 'course_id': 'blackboard:_9_1', 'submitted': submitted, 'actionable': actionable}
                            for name, submitted, actionable in [('null', None, True), ('false', False, True), ('submitted', True, True), ('closed', None, False), ('unknown_open', None, None)]],
        })
        data['assignments'].append({'id': 'blackboard:unavailable', 'source': 'blackboard', 'title': '未能核实的历史',
                                    'course_id': 'blackboard:_9_1', 'submitted': None, 'actionable': True, 'submission_evidence': 'unavailable'})
        data['assignments'].append({'id': 'blackboard:history', 'source': 'blackboard', 'title': '已核实的历史',
                                   'course_id': 'blackboard:_9_1', 'actionable': True, **reader.submission_history(HISTORY)})
        data['assignments'].append({'id': 'blackboard:exempt', 'source': 'blackboard', 'title': '已豁免的作业',
                                   'course_id': 'blackboard:_9_1', 'submitted': False, 'actionable': True, 'exempt': True})
        bb.store.write('snapshot', {'owner': package._source.owner(), 'data': data, 'updated_at': '2026-10-17T00:00:00Z'})
        bb.store.write('sync', {'owner': package._source.owner(), 'status': 'ready'})
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                async def api(module, path='/snapshot', **options):
                    if module in {'blackboard', 'courses', 'assignments'}:
                        return await client.request(options.get('method', 'GET'), '/' + module + path, json=options.get('body'))
                    if module == 'timetable':
                        return httpx.Response(200, json={'data': validate_bundle({'metadata': {'semester': '2026-fall'},
                            'courses': [course('timetable', 'current', '教务合成课程', 'QA101', '2026-fall')]})})
                    if module == 'gradescope':
                        return httpx.Response(200, json={'data': validate_bundle({
                            'courses': [course('gradescope', 'qa', '另一课程', 'QA102', '2026-fall')],
                            'assignments': [{'id': 'gradescope:unknown', 'source': 'gradescope', 'title': '其他来源状态', 'course_id': 'gradescope:qa', 'submitted': None, 'actionable': True}],
                        })})
                    return httpx.Response(404)
                courses.api = assignments.api = api
                snapshot = (await client.get('/blackboard/snapshot')).json()['data']
                assert snapshot['courses'][0]['term'] == ''
                assert snapshot['courses'][1]['semester'] == '2026-fall'
                values = snapshot['assignments']
                assert [item['submitted'] for item in values] == [False, False, True, False, False, None, True, False]
                assert bb.store.read('snapshot')['data']['assignments'][0]['submitted'] is None, 'Reading normalizes the response without rewriting cached source data'
                pending = (await client.get('/courses/catalog/assignments?current=true&pending=true')).json()['items']
                assert {item['id'] for item in pending} == {'blackboard:null', 'blackboard:false'}
                overview = (await client.get('/assignments/snapshot')).json()
                actual_pending = {item['id'] for item in overview['pending']}
                assert actual_pending == {'blackboard:null', 'blackboard:false', 'gradescope:unknown'}, actual_pending
                source_counts = overview['summary']['by_source']['blackboard']
                assert {key: source_counts[key] for key in ('total', 'unsubmitted', 'pending')} == {'total': 8, 'unsubmitted': 4, 'pending': 2}
                assert sum(source_counts['submission_states'].values()) == 8
                assert next(item for item in overview['data']['assignments'] if item['id'] == 'gradescope:unknown')['submitted'] is None
                response = await client.post('/courses/context', json={'context_ids': ['assignments:blackboard:null']})
                assert response.status_code == 200, response.text
                assert response.json()['items'][0]['submitted'] is False
                unknown = await client.post('/courses/context', json={'context_ids': ['assignments:blackboard:unavailable']})
                assert unknown.json()['items'][0]['submitted'] is None
                evidence = (await client.post('/courses/context', json={'context_ids': ['assignments:blackboard:history']})).json()['items'][0]
                assert evidence['submission_status'] == 'submitted' and evidence['submission_evidence'] == 'submission_history'
                assert evidence['submitted_at'] == '2026-09-30T15:12:00+08:00'
                bb.auth.revision = 'different-account'
                assert (await client.get('/blackboard/snapshot')).json()['data']['assignments'] == []
        finally:
            package.stop(bb)


asyncio.run(check_cached_submissions())
print('blackboard: grade and submission-history evidence, unknown fallback, sync/cache/catalog/pending/AI context, availability, silently skipped announcements and file paths passed')
