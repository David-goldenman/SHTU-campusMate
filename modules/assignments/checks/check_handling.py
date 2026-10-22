"""Team submissions remain source-unsubmitted while local reminders stay resolved."""
import asyncio
import copy
import sys
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.campus.analysis import account_revision
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox


async def check():
    with ExitStack() as stack:
        names = ('assignments', 'courses', 'timetable', 'dashboard', 'notifications')
        contexts = {name: stack.enter_context(sandbox(name)) for name in names}
        modules = {name: load(name) for name in names}
        app = FastAPI()
        for name in names:
            app.include_router(modules[name].create_router(contexts[name]), prefix='/' + name)
        source = modules['timetable']._source
        stack.callback(source.close)
        stack.callback(modules['notifications']._service.close)
        owner = account_revision(contexts['assignments'])
        now = datetime.now(timezone.utc)
        persistence = sys.modules[modules['timetable'].__name__ + '.persistence']
        term = persistence.expected_semester(now.astimezone(persistence.ZONE).date())
        year, season = term.split('-')
        metadata = {'semester': f"{year}-{int(year)+1}学年" + {'fall':'秋季','spring':'春季','summer':'夏季'}[season], 'semester_id':'fixture'}
        raw = validate_bundle({'courses': [{'id':'blackboard:c','source':'blackboard','title':'合成课程','code':'CS100','term':term}],
            'assignments': [{'id':'blackboard:team','source':'blackboard','course_id':'blackboard:c','title':'合成团队作业',
                'submitted':False,'submission_status':'not_submitted','availability':'open','actionable':True,'due_at':(now+timedelta(hours=2)).isoformat()},
                {'id':'blackboard:solo','source':'blackboard','course_id':'blackboard:c','title':'合成个人作业',
                'submitted':False,'submission_status':'not_submitted','availability':'open','actionable':True,'due_at':(now+timedelta(hours=3)).isoformat()}]})
        original = copy.deepcopy(raw)
        contexts['timetable'].store.write('snapshot', {'owner':source.owner(),'data':validate_bundle({'metadata':metadata}), 'updated_at':now.isoformat()})
        contexts['timetable'].store.write('sync', {'owner':source.owner(),'status':'ready'})
        contexts['timetable'].store.write('semester:'+source.owner()+':fixture', {'week_one':(now.date()-timedelta(days=7)).isoformat()})
        def notice(identity, ids, title='合成作业截止提醒'):
            return {'id':identity,'title':title,'summary':'作业待提交','read':False,'importance':'normal',
                    'created_at':now.isoformat(),'citations':[{'id':item,'source':'assignments','title':'合成作业'} for item in ids]}
        contexts['notifications'].store.write('imports:'+owner, [notice('team',['blackboard:team']),
            notice('mixed',['blackboard:team','blackboard:solo']),notice('grade',['blackboard:team'],'合成作业成绩反馈'),
            {**notice('manual',['blackboard:team']),'read_source':'manual'}])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://fixture') as client:
            async def api(name,path='/snapshot',method='GET',body=None,**kwargs):
                if name in modules:
                    return await client.request(method,'/'+name+path,json=body)
                if name == 'blackboard':
                    return httpx.Response(200,json={'status':'ready','data':copy.deepcopy(raw),'updated_at':now.isoformat()})
                return httpx.Response(404,json={})
            for context in contexts.values():
                context.api = api
            async def snapshot():
                response = await client.get('/assignments/snapshot')
                assert response.status_code == 200, response.text
                return response.json()
            initial = await snapshot()
            assert len(initial['pending']) == 2
            body = {'assignment_id':'blackboard:team','status':'waived','reason':'team_submitted','note':'老师要求小组只交一份',
                    'expected_revision':'','account_revision':owner}
            for invalid, status in (({'account_revision':'old'},409),({'assignment_id':'unknown'},404),
                                    ({'reason':None},422),({'reason':'other','note':' '},422)):
                assert (await client.put('/assignments/handling',json={**body,**invalid})).status_code == status
            writes = await asyncio.gather(*(client.put('/assignments/handling',json=body) for _ in range(2)))
            assert sorted(item.status_code for item in writes) == [200,409], 'Stale tabs cannot overwrite a newer choice'
            saved = next(item.json()['handling'] for item in writes if item.status_code == 200)
            for _ in range(3):
                value = await snapshot()
                team = next(item for item in value['data']['assignments'] if item['id']=='blackboard:team')
                assert team['category']=='waived' and not team['pending'] and not team['overdue']
                assert team['submission_status']=='not_submitted' and team['submitted'] is False and not team.get('exempt')
                assert team['handling']==saved and value['summary']['waived']==1 and value['summary']['unsubmitted']==2
                assert value['counts']['waived']==1 and [item['id'] for item in value['pending']]==['blackboard:solo']
            recreated = modules['assignments'].create_router(contexts['assignments'])
            assert (await next(route.endpoint for route in recreated.routes if route.path=='/handling' and 'GET' in route.methods)())['items']['blackboard:team']==saved
            detail = (await client.get('/assignments/detail?assignment_id=blackboard:team')).json()
            assert detail['assignment']['handling']==saved
            course = (await client.get('/courses/catalog/assignments?pending=true&current=true')).json()
            assert [item['id'] for item in course['items']]==['blackboard:solo']
            selected = (await client.post('/courses/context',json={})).json()
            assert next(item for item in selected['items'] if item['id']=='assignments:blackboard:team')['reminder_suppressed']
            schedule = (await client.get('/timetable/schedule')).json()
            assert [item['id'] for item in schedule['homework']['items']]==['blackboard:solo']
            assert not any(item['id']=='blackboard:team' for item in schedule['data']['events'])
            ics = (await client.get('/timetable/calendar/export/homework.ics')).text
            assert '合成团队作业' not in ics and '合成个人作业' in ics
            home = (await client.get('/dashboard/snapshot')).json()
            assert home['stats']['pending']==1 and home['pending'][0]['id']=='blackboard:solo'
            notices = {item['id']:item for item in (await client.get('/notifications/snapshot')).json()['items']}
            assert notices['team']['read'] and notices['team']['auto_read']['reason']=='assignment_not_required'
            assert all(not notices[key]['read'] for key in ('mixed','grade','manual'))
            assert raw==original, 'No source data or personal submission status is modified'
            restored = await client.put('/assignments/handling',json={**body,'status':'required','expected_revision':saved['revision']})
            assert restored.status_code==200 and len((await snapshot())['pending'])==2
            assert (await client.put('/assignments/handling',json=body)).status_code==409, 'Restoration retains a version against obsolete writes'
            assert not next(item for item in (await client.get('/notifications/snapshot')).json()['items'] if item['id']=='team')['read']
            assert len((await client.get('/timetable/schedule')).json()['homework']['items'])==2
            for context in contexts.values():
                context.auth.revision='other-account'
            assert (await client.get('/assignments/handling')).json()['items']=={}
            assert (await client.put('/assignments/handling',json=body)).status_code==409


asyncio.run(check())
print('assignment handling: persistence, conflict/account guards, source truth, course/AI/dashboard/calendar/ICS consistency, mixed notices and restoration passed')
