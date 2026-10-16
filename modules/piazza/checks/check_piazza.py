import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from checks.module_support import load, sandbox
from backend.services.campus import Remote
from backend.services.auth import LoginRequired

package = load('piazza')
reader = sys.modules[package.__name__ + '.reader']
post = reader.parse_post({'history':[{'subject':'合成帖子','content':'<b>正文</b>'}], 'children':[{'id':'r1','history':[],'content':'回复','children':[{'id':'r2','history':[{'content':'嵌套回复'}]}]}]},'c1','p1')
assert post['body_text'] == '正文' and len(post['replies']) == 2


def handler(request):
    method = request.url.params.get('method')
    if method == 'user.status':
        return httpx.Response(200,json={'result':{'networks':[{'id':'c1','name':'合成课程','course_number':'CS 100','term':'Fall 2026'}]}})
    return httpx.Response(200,json={'result':{'feed':[{'id':'p1','subject':'合成帖子','snippet':'摘要'},{'subject':'无标识'}]}})


with sandbox('piazza',handler) as context:
    package.create_router(context)
    try:
        package._source.run()
        data = package._source.snapshot()
        assert data['status'] == 'partial' and data['data']['posts'][0]['course_id'] == 'piazza:c1'
    finally:
        package.stop(context)
print('piazza: dictionary course lists, malformed feed entries, nested replies and source identities passed')

def revised(request):
    if request.url.params.get('method') == 'user.status':
        return httpx.Response(200, json={'result': {'networks': [{'id':'c1','name':'Course','course_number':'CS100','term':'Fall 2026'}]}})
    return httpx.Response(200, json={'result': {'feed': [{'id':'p1','subject':'New title','snippet':'New content','updated':'2026-10-16T00:00:00Z'}]}})

with httpx.Client(transport=httpx.MockTransport(revised)) as client:
    result = reader.fetch(Remote(client, threading.Event(), ['piazza.com']), {'posts':[{'id':'piazza:c1:p1','body_text':'Obsolete body','updated_at':'2026-10-15T00:00:00+00:00'}]})
    assert result['posts'][0]['body_text'] == 'New content'
with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'error':'not logged in'}))) as client:
    try:
        reader.rpc(Remote(client, threading.Event(), ['piazza.com']), 'user.status', {})
        raise AssertionError('Expired sessions must be recognized even without result')
    except LoginRequired:
        pass
print('piazza: changed posts invalidate old bodies and expired sessions retain the login signal')
