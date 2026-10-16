import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError
from backend.services.campus import Remote
import httpx

package = load('elrc')
reader = sys.modules[package.__name__ + '.reader']
issues = []
tree = [{'info':{'guid_':'a','chapter_name':'章节'},'childInfo':[{'info':{'guid_':'b','chapter_name':'资料','chapter_describe':'<p>说明</p>'}}]}]
items = reader.chapters(tree,'c1','https://elrc.shanghaitech.edu.cn/learn/',issues)
assert items[1]['path'] == ['章节','资料'] and items[1]['body_text'] == '说明'
voice = {'data':[{'type':'model_sobey_smart_voice_','metadata':[{'textLanguage':'{"text_source":"合成转写"}','_in':'10000000','_out':'20000000'}, {'text':'保留文字','_in':'bad','_out':None},{'text':'删除项','delete':'1'}]}]}
result = reader.parse_transcript(voice,[{'chapterTitle':'章节摘要','chapterContent':'<b>摘要</b>'}])
assert len(result['transcript']) == 2 and result['transcript'][0]['start'] == 1
assert result['transcript'][1]['start'] is None and result['issues']
assert result['summary'][0]['body_text'] == '摘要'


class Repeated:
    def json(self,*args,**kwargs):
        return {'status':200,'data':{'results':[{'id':1}] * 50}}


try:
    list(reader.pages(Repeated(),'/example',{},'page','size'))
    raise AssertionError('Repeated full pages must stop')
except SourceError:
    pass
print('elrc: chapter paths, string language metadata, missing timestamps, deleted lines and repeated pagination passed')

def csrf(request):
    assert request.headers['CsrfToken'] == 'synthetic-token'
    return httpx.Response(200, json={'data': []})

with httpx.Client(transport=httpx.MockTransport(csrf)) as client:
    client.cookies.set('CsrfToken', 'synthetic-token', domain='elrc.shanghaitech.edu.cn')
    assert reader.api(Remote(client, threading.Event(), ['elrc.shanghaitech.edu.cn']), '/rman/v1/smart/voice/select', payload={'contentid':'stream'}) == []
print('elrc: shared source forwards the platform CSRF cookie for transcript requests')
