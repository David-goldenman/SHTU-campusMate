"""Expired activity reminders leave unread views without deleting their history."""
import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from backend.services.campus.analysis import account_revision
from checks.module_support import load, sandbox

package=load('notifications')
expiry=sys.modules[package.__name__+'.expiry']
service_module=sys.modules[package.__name__+'.service']


async def check():
    with sandbox('notifications') as context:
        context.ai.settings=lambda:{'enabled':False}
        now=datetime.now(timezone.utc)
        old=(now-timedelta(days=2)).isoformat(); future=(now+timedelta(days=1)).isoformat()
        window={'starts_at':old,'expires_at':old,'basis':'event_end'}
        mail={'mail:fire':{'bucket':'focus','needs_check':True,'event_window':window},
              'mail:other':{'bucket':'focus','event_window':{**window,'expires_at':future}},
              'mail:unknown':{'bucket':'focus','event_window':None}}
        unavailable=False; switched=False
        async def api(name,path='/snapshot',**kwargs):
            if switched:context.auth.revision='other-account'
            if unavailable:return httpx.Response(404,json={})
            if name=='mail':return httpx.Response(200,json={'messages':[{'id':key,'classification':value} for key,value in mail.items()]})
            if name=='campus-agent':return httpx.Response(200,json={'items':[]})
            return httpx.Response(404,json={})
        context.api=api
        router=package.create_router(context);service=package._service;owner=account_revision(context)
        endpoint=next(route.endpoint for route in router.routes if route.path=='/snapshot')
        def notice(identity,ids):
            return {'id':identity,'title':'合成消防培训','summary':'合成活动','importance':'important','read':False,'event_at':None,
                    'source_revision':'v1','created_at':old,'citations':[{'id':key,'source':'mail','title':'合成资料'} for key in ids]}
        items=[notice('fire',['mail:fire']),notice('multi',['mail:fire','mail:other']),notice('unknown',['mail:unknown']),
               {**notice('feedback',['mail:fire']),'title':'培训反馈与补签要求'},
               {**notice('manual',['mail:fire']),'read_source':'manual'},
               {**notice('assignment',['blackboard:hw']),'title':'逾期作业仍开放','event_at':old,'citations':[{'id':'blackboard:hw','source':'assignments'}]}]
        context.store.write('imports:'+owner,items)
        first={item['id']:item for item in (await endpoint())['items']}
        assert first['fire']['read'] and first['fire']['expired'] and first['fire']['auto_read']['reason']=='event_expired'
        assert not first['manual']['read'] and first['manual']['expired']
        assert all(not first[key]['read'] and not first[key]['expired'] for key in ('multi','unknown','assignment','feedback'))
        assert len(first)==len(items), 'Expired notices remain in history'
        auto=copy.deepcopy(first['fire']['auto_read'])
        assert next(item for item in (await endpoint())['items'] if item['id']=='fire')['auto_read']==auto
        body=package.ImportedNotice(**{**{key:value for key,value in items[0].items() if key not in {'read','created_at'}},'account_revision':owner})
        assert service.import_notice(body)['auto_read']==auto, 'Repeated imports retain expiry and read state'
        unavailable=True
        assert next(item for item in (await endpoint())['items'] if item['id']=='fire')['read'], 'Known expiry survives optional source outages'
        unavailable=False
        mail['mail:fire']['event_window']={**window,'starts_at':future,'expires_at':future}
        changed={item['id']:item for item in (await endpoint())['items']}
        assert not changed['fire']['read'] and not changed['fire']['expired'] and changed['fire']['event_at']==future
        mail['mail:fire']['event_window']=window
        await endpoint()
        mail['mail:fire']['event_window']=None
        assert not next(item for item in (await endpoint())['items'] if item['id']=='fire')['read'], 'Invalidated date evidence reopens auto-resolved notices'
        mail['mail:fire']['event_window']=window
        await endpoint();service.mark_read('fire',False)
        assert not next(item for item in (await endpoint())['items'] if item['id']=='fire')['read'], 'An explicit unread choice wins'
        # The clock itself triggers expiry even when no content changes and AI is off.
        context.store.write('imports:'+owner,[{**notice('clock',[]),'expiry':{'at':future,'basis':'event_end'}}])
        class Later(datetime):
            @classmethod
            def now(cls,tz=None):return now+timedelta(days=2)
        with patch.object(service_module,'datetime',Later):
            assert service.snapshot()['items'][0]['read']
        before=copy.deepcopy(context.store.read('imports:'+owner))
        switched=True
        await service.reconcile_mail()
        assert context.store.read('imports:'+owner)==before and service.snapshot()['items']==[]
        service.close()


asyncio.run(check())
print('notification expiry: clock-only cleanup, history, mixed citations, actionable overdue work, reimports, changed dates, manual choices, offline and account isolation passed')
