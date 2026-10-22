import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from checks.module_support import load,sandbox

package=load('campus-agent')

async def check():
    with sandbox('campus-agent') as context:
        notices=[{'id':'one','source_revision':'v1','read':False,'importance':'important','title':'合成提醒','summary':'摘要'*300,
                  'why':'large explanation','citations':[{'source':'mail','id':'mail:1','title':'邮件','url':'https://example.invalid'}]}]
        calls=[]
        async def api(module,path='/snapshot',**kwargs):
            calls.append((module,path));return httpx.Response(200,json={'items':notices})
        context.api=api
        app=FastAPI();app.include_router(package.create_router(context))
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
                full=(await client.get('/status')).json()
                compact=(await client.get('/widget')).json()
                assert compact['owner']==full['owner'] and compact['notices'][0]['id']=='one'
                assert compact['notices'][0]['summary']==notices[0]['summary'][:160]
                assert compact['notices'][0]['citations']==[{'source':'mail'}]
                assert 'proposals' not in compact and 'why' not in compact['notices'][0]
                assert full['notices']==notices and calls==[('notifications','/snapshot')]*2
                async def changed(*args,**kwargs):
                    context.auth.revision='another';return httpx.Response(200,json={'items':notices})
                context.api=changed
                assert (await client.get('/widget')).status_code==409
        finally: package._service.close()
    print('agent widget: compact preview, source types, full status compatibility, reconciliation and account switch passed')

asyncio.run(check())
