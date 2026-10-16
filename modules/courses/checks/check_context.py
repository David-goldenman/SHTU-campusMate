import asyncio
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from backend.services.campus import course
from backend.services.campus.analysis import account_revision, citations
from backend.services.campus.data import validate_bundle
from backend.services.campus.remote import SourceError
from checks.module_support import load, sandbox

build_context = sys.modules[load('courses').__name__ + '.context'].build_context


async def check():
    with sandbox('analysis') as context:
        raw = course('gradescope','1','合成课程','CS100','Fall 2026','https://www.gradescope.com/courses/1')
        data = validate_bundle({'courses':[{'id':'group:1','source':'catalog','title':'合成课程','term':'2026-fall','current':True,'course_ids':[raw['id']],'sources':[raw]}], 'messages':[{'id':'mail:1','source':'mail','title':'合成邮件','body_text':'合成正文','url':'https://mail.shanghaitech.edu.cn/'}]})
        selected = build_context(data, account_revision(context))
        assert len(selected['items']) == 2
        assert (build_context(data, account_revision(context),context_ids=[]))['items'] == []
        scoped = build_context(data, account_revision(context),course_id='group:1')
        assert all(item['kind'] != 'messages' for item in scoped['items'])
        assert citations([selected['items'][0]['id']],selected)[0]['url'] == raw['url']
        try:
            citations(['invented:source'],selected)
            raise AssertionError('Model citations must belong to the chosen records')
        except SourceError:
            pass
        data['messages'] = [{'id':'mail:' + str(index),'source':'mail','title':'合成邮件','body_text':'合成正文' * 1000,'url':'https://mail.shanghaitech.edu.cn/'} for index in range(100)]
        bounded = build_context(data, account_revision(context))
        assert bounded['context']['truncated'] and len(bounded['text']) <= 85000


asyncio.run(check())
print('analysis: course scope, explicit empty selections, size limits and source-backed citations passed')
