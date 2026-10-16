import sys
import threading
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import HTTPException
from backend.services.campus import course
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('notifications')
with sandbox('notifications') as context:
    raw = course('gradescope','1','合成课程','CS100','Fall 2026','https://www.gradescope.com/courses/1')
    data = validate_bundle({'courses':[{'id':'group:1','source':'catalog','title':'合成课程','term':'2026-fall','current':True,'course_ids':[raw['id']],'sources':[raw]}]})
    async def api(module,path='/snapshot',**kwargs):
        return httpx.Response(200,json={'data':data})
    context.api = api
    context.ai.result['content'] = {'notifications':[{'title':'合成提醒','summary':'合成安排','importance':'important','why':'需要关注','event_at':None,'citation_ids':['courses:gradescope:1']}]}
    package.create_router(context)
    service = package._service
    first = service.generate()
    key = first['items'][0]['id']
    service.mark_read(key,True)
    assert service.generate()['unchanged']
    assert service.generate(force=True)['items'][0]['read'] is True
    raw['title'] = '课程资料更新'
    assert service.generate(force=True)['items'][0]['read'] is False
    context.ai.result['content']['notifications'][0]['citation_ids'] = ['invented']
    try:
        service.generate(force=True)
        raise AssertionError('Unverified notifications must preserve previous results')
    except HTTPException as error:
        assert error.status_code == 502
    assert service.snapshot()['items'][0]['id'] == key and service.snapshot()['error']
    context.auth.revision = 'new-account'
    assert service.snapshot()['items'] == []
    context.ai.result['content']['notifications'][0]['citation_ids'] = ['courses:gradescope:1']
    called = threading.Event()
    original = context.ai.generate
    def generated(**kwargs):
        called.set()
        return original(**kwargs)
    context.ai.generate = generated
    service.start()
    service.set_settings(True)
    assert called.wait(2)
    service.close()
    assert not service.thread.is_alive()
    assert service.snapshot()['error'] is None
print('notifications: deduplication, read-state revisions, verified references, cache preservation, account isolation and worker cleanup passed')
