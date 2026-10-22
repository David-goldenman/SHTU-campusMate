"""Conditional public assets must update, while private API responses stay uncached."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
import backend.main as main
from backend.core.store import Store
from checks.module_support import Memory

async def check():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(dir=root/'.codex/tmp',prefix='static-cache-') as directory:
        folder=Path(directory);web=folder/'web';web.mkdir();data=folder/'private';data.mkdir()
        asset=web/'fixture.js';asset.write_text('export const value = 1;',encoding='utf-8')
        original_web=main.WEB
        main.WEB=web
        try:
            app=main.create_app(active_port=19783,store=Store(data/'state.sqlite3'),vault=Memory(),modules_root=folder/'modules',data_dir=data)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1:19783') as client:
                    first=await client.get('/assets/fixture.js')
                    assert first.status_code==200 and first.headers['cache-control']=='private, no-cache'
                    old=first.headers['etag']
                    second=await client.get('/assets/fixture.js',headers={'If-None-Match':old})
                    assert second.status_code==304 and not second.content
                    changed=asset.stat().st_mtime+2
                    asset.write_text('export const value = 2;',encoding='utf-8');os.utime(asset,(changed,changed))
                    third=await client.get('/assets/fixture.js',headers={'If-None-Match':old})
                    assert third.status_code==200 and third.headers['etag']!=old and 'value = 2' in third.text
                    assert (await client.get('/api/v1/bootstrap')).headers['cache-control']=='no-store'
                    assert (await client.get('/assets/missing.js')).headers['cache-control']=='no-store'
        finally: main.WEB=original_web
    print('static assets: conditional 304, changed content refresh, missing assets and uncached private APIs passed')

asyncio.run(check())
