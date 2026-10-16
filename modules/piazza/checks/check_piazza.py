import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from checks.module_support import load, sandbox

package = load('piazza')
reader = sys.modules[package.__name__ + '.reader']
post = reader.parse_post({'history':[{'subject':'合成帖子','content':'<b>正文</b>'}], 'children':[{'id':'r1','history':[],'content':'回复','children':[{'id':'r2','history':[{'content':'嵌套回复'}]}]}]},'c1','p1')
assert post['body_text'] == '正文' and len(post['replies']) == 2


def handler(request):
    method = request.url.params.get('method')
    if method == 'user_profile.get_profile':
        return httpx.Response(200,json={'result':{'all_classes':{'c1':{'nid':'c1','name':'合成课程','num':'CS 100','term':'Fall 2026'}}}})
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
