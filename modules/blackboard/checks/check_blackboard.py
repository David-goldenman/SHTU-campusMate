import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from fastapi import HTTPException

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

course = {'id':'blackboard:_9_1','source_id':'_9_1','url':'https://elearning.shanghaitech.edu.cn:8443/webapps/blackboard/execute/launcher?type=Course&id=_9_1'}
page = '<div id="announcementList"><li id="_11_1"><h3 class="item">开学通知</h3><div class="details"><div class="vtbegenerated">第一周停课。</div></div></li><li id="_12_1"><div class="details"><div class="vtbegenerated">缺少标题</div></div></li></div>'
announcements = reader.announcements(page,course)
assert len(announcements) == 1 and announcements[0]['id'] == 'blackboard:_9_1:_11_1' and announcements[0]['title'] == '开学通知' and announcements[0]['body_text'] == '第一周停课。'
assert reader.announcements('<html><body>系统维护</body></html>',course) is None
assert reader.announcements('<div id="announcementForm"></div>',course) == []


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


old = {'id':'blackboard:_9_1:_11_1','source':'blackboard','course_id':'blackboard:_9_1','title':'旧公告','body_text':'','url':course['url']}
unreadable = reader.fetch(Remote(HTTPException(403,'forbidden')),{'announcements':[old],'courses':[]})
assert unreadable['announcements'] == [old] and not unreadable['issues'] and unreadable['courses'][0]['title'] == '数字电路 【2026 Spring】'
changed = reader.fetch(Remote('<html><body>系统维护</body></html>'),{'announcements':[old],'courses':[]})
assert changed['announcements'] == [old] and not changed['issues']
broken = reader.fetch(Remote(RuntimeError('unexpected page')),{'announcements':[old],'courses':[]})
assert broken['announcements'] == [old] and not broken['issues']
readable = reader.fetch(Remote(page),{'announcements':[old],'courses':[]})
assert [item['title'] for item in readable['announcements']] == ['开学通知'] and not readable['issues']
assert readable['courses'][0]['term'] == '2026-2027学年秋季学期' and readable['courses'][0]['semester'] == '2026-fall'
print('blackboard: availability windows, unknown states, submission evidence, cyclic folders, stable file paths and silently skipped announcements passed')
