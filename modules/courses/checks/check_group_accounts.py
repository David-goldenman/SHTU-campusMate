"""Course grouping ownership, legacy migration and stale edits via actual routes."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.campus import course
from backend.services.campus.analysis import account_revision
from backend.services.campus.data import validate_bundle
from checks.module_support import load,sandbox

package=load('courses')
group={'id':'personal','title':'Account A private grouping','course_ids':['gradescope:shared','piazza:shared']}


async def check(legacy=False):
    with sandbox('courses') as context:
        sources={name:{'status':'ready','data':validate_bundle({'courses':[course(name,'shared','Shared course','CS100','2026-fall')]})}
                 for name in ('gradescope','piazza')}
        switch_during_read=False
        async def api(module,path='/snapshot',**kwargs):
            if switch_during_read and module=='assignments':context.auth.revision='account-b'
            return httpx.Response(200,json=sources[module]) if module in sources else httpx.Response(404)
        context.api=api;context.auth.revision='account-a';owner_a=account_revision(context)
        if legacy:context.store.write('groups',[group])
        app=FastAPI();app.include_router(package.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            if not legacy:
                assert (await client.put('/groups',json={'groups':[group],'account_revision':owner_a})).status_code==200
            # The first read after initialization can be by B; legacy data still belongs to A.
            context.auth.revision='account-b';owner_b=account_revision(context)
            value=(await client.get('/groups')).json()
            assert value['groups']==[],'A different account must not inherit saved group names or associations'
            assert value['account_revision']==owner_b
            assert (await client.get('/snapshot')).json()['data']['courses'][0]['title']!='Account A private grouping'
            assert (await client.put('/groups',json={'groups':[],'account_revision':owner_a})).status_code==409,'An old account form must be rejected'
            assert (await client.put('/groups',json={'groups':[]})).status_code==422,'Unowned writes cannot silently use the current account'
            assert (await client.put('/groups',json={'groups':[],'account_revision':owner_b})).status_code==200
            context.auth.revision='account-a'
            assert (await client.get('/groups')).json()['groups']==[group],'Resetting B cannot erase A groups'
            assert (await client.get('/snapshot')).json()['data']['courses'][0]['title']=='Account A private grouping'
            assert (await client.get('/identities')).json()['items'][0]['title']=='Account A private grouping'
            switch_during_read=True
            assert (await client.put('/groups',json={'groups':[],'account_revision':owner_a})).status_code==409
            switch_during_read=False;context.auth.revision='account-a'
            assert (await client.get('/groups')).json()['groups']==[group],'Switching during async validation cannot save the edit'
        # A reload while B is active must not reassign legacy ownership.
        context.auth.revision='account-b'
        reloaded=FastAPI();reloaded.include_router(package.create_router(context))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reloaded),base_url='http://test') as client:
            assert (await client.get('/groups')).json()['groups']==[]
            context.auth.revision='account-a'
            assert (await client.get('/groups')).json()['groups']==[group]
            assert (await client.put('/groups',json={'groups':[],'account_revision':owner_a})).status_code==200
            assert (await client.get('/groups')).json()['groups']==[],'An explicit reset must not revive legacy groups'


asyncio.run(check());asyncio.run(check(legacy=True))
print('course groups: account isolation, reset, stale/missing owner, async account switch, legacy ownership and reload passed')
