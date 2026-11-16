"""Agent proxy status and diagnostics are preserved through the actual routes."""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from checks.module_support import load,sandbox

async def main():
    package=load('notifications')
    with sandbox('notifications') as context:
        status=503;calls=[]
        detail={'detail':'Synthetic unavailable','code':'module_unavailable','action':'Try again later','request_id':'test-request','operation_id':'test-operation'}
        async def api(module,path='/snapshot',**kwargs):
            calls.append((module,path,kwargs.get('method'),kwargs.get('body')))
            assert module=='campus-agent'
            if status>=400:return httpx.Response(status,json=detail)
            return httpx.Response(200 if path=='/settings' else 202,json={'enabled':True} if path=='/settings' else {'queued':True})
        context.api=api;app=FastAPI();app.include_router(package.create_router(context))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                for status in (404,409,422,503,504):
                    check=await client.post('/agent/check')
                    settings=await client.put('/agent/settings',json={'enabled':True})
                    assert check.status_code==status,'Failed checks must not report accepted tasks'
                    assert settings.status_code==status,'Failed settings updates must not report success'
                    assert check.json()==settings.json()==detail,'Keep safe upstream diagnostics and recovery instructions'
                assert (await client.get('/agent/status')).json()=={'available':False}
                status=200
                check=await client.post('/agent/check');settings=await client.put('/agent/settings',json={'enabled':True})
                assert check.status_code==202 and check.json()=={'queued':True}
                assert settings.status_code==200 and settings.json()=={'enabled':True}
                assert calls[-2:]==[('campus-agent','/check','POST',None),('campus-agent','/settings','PUT',{'enabled':True})]
        finally:package.stop(context)
    print('notification agent proxy: errors preserve status/diagnostics, success stays compatible and unavailable reads degrade gracefully')

asyncio.run(main())
