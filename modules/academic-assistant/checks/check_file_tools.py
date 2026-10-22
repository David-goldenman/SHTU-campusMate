"""Local file capabilities, per-operation approval, full access and edit conflicts."""
import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI, HTTPException
from checks.module_support import load, sandbox

study = load('academic-assistant')
files = sys.modules[study.__name__ + '.files']


async def rejected(operation, status):
    try:
        await operation
        raise AssertionError('Operation unexpectedly succeeded')
    except HTTPException as error:
        assert error.status_code == status, error.detail


async def check():
    with sandbox('academic-assistant') as context:
        app = FastAPI(); app.include_router(study.create_router(context))
        task = study.Task(context, '按我的要求读写测试文件')
        events = []
        task.emit = events.append
        study._agent.tasks['synthetic-token'] = task
        async def op(action, path='.', **kwargs):
            return await task.file_operation(files.FileOperation(action=action,path=str(path),**kwargs))
        settings = files.settings(context)
        root = Path(settings['workspace'])
        assert settings['mode'] == 'workspace' and root.is_dir()
        assert (await op('list'))['items']==[]
        await op('write','notes/复习.md',content='第一行\r\n第二行\r\n')
        assert (root/'notes/复习.md').read_bytes()=='第一行\r\n第二行\r\n'.encode()
        await rejected(op('write','notes/复习.md',content='不得盲目覆盖'),409)
        read=await op('read','notes/复习.md',limit=3)
        assert read['has_more'] and read['next_offset']==3 and read['items'][0]['source_id'] in task.references
        await op('edit','notes/复习.md',old_text='第二行',new_text='更正内容')
        assert (root/'notes/复习.md').read_bytes()=='第一行\r\n更正内容\r\n'.encode()
        await op('read','notes/复习.md')
        (root/'notes/复习.md').write_text('用户刚刚修改',encoding='utf-8')
        await rejected(op('edit','notes/复习.md',old_text='更正内容',new_text='旧模型修改'),409)
        assert (root/'notes/复习.md').read_text(encoding='utf-8')=='用户刚刚修改'
        await op('read','notes/复习.md')
        await rejected(op('edit','notes/复习.md',old_text='不存在',new_text='x'),409)
        outside=context.data_dir/'outside.txt'
        outside.write_text('外部文件',encoding='utf-8')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            async def decision(allow):
                for _ in range(100):
                    if task.files.pending:break
                    await asyncio.sleep(.01)
                assert task.files.pending
                identity=next(iter(task.files.pending))
                request=SimpleNamespace(method='POST',url=SimpleNamespace(path='/api/v1/modules/academic-assistant/files/approvals/'+identity),headers={'authorization':'Bearer synthetic-token'})
                assert not study.authorize_write(context,request), 'A task token cannot approve its own files'
                response=await client.post('/files/approvals/'+identity,json={'allow':allow,'account_revision':task.owner})
                assert response.status_code==200,response.text
                return identity
            pending=asyncio.create_task(op('read',outside))
            identity=await decision(False)
            await rejected(pending,403)
            assert not task.files.pending and events[-1]['type']=='file-approval-closed'
            assert (await client.post('/files/approvals/'+identity,json={'allow':True,'account_revision':task.owner})).status_code==409
            pending=asyncio.create_task(op('read',outside))
            await decision(True)
            assert (await pending)['text']=='外部文件'
            pending=asyncio.create_task(op('write',outside,content='已批准修改'))
            await decision(True)
            await pending
            assert outside.read_text(encoding='utf-8')=='已批准修改'
            # Path traversal resolves to the same outside path and still requires approval.
            relative=Path('..')/'..'/outside.name
            pending=asyncio.create_task(op('read',relative))
            await decision(False);await rejected(pending,403)
            task.files.approval_seconds=.02
            await rejected(op('read',outside),409)
            assert not task.files.pending
            task.files.approval_seconds=75
            task.cancel_event=threading.Event()
            pending=asyncio.create_task(op('read',outside))
            await asyncio.sleep(.02);task.cancel_event.set();await rejected(pending,409)
            task.cancel_event=None
            old=files.settings(context)
            response=await client.put('/files/settings',json={**{key:old[key] for key in ('workspace','account_revision')},'mode':'full','expected_revision':old['revision']})
            assert response.status_code==200,response.text
            assert files.settings(context)['mode']=='full'
            start=len(events)
            assert (await op('read',outside))['text']=='已批准修改'
            await op('write',outside,content='完全访问修改')
            assert not any(item['type']=='file-approval' for item in events[start:])
            assert (await client.put('/files/settings',json={**{key:old[key] for key in ('workspace','account_revision')},'mode':'workspace','expected_revision':old['revision']})).status_code==409
            current=files.settings(context)
            await client.put('/files/settings',json={**{key:current[key] for key in ('workspace','account_revision')},'mode':'workspace','expected_revision':current['revision']})
            reopened=study.Task(context,'继续读取保存的复习文件')
            assert (await reopened.file_operation(files.FileOperation(action='read',path='notes/复习.md')))['text']=='用户刚刚修改'
            pending=asyncio.create_task(op('read',outside))
            await asyncio.sleep(.02)
            context.auth.revision='another-account'
            await rejected(pending,409)
            assert files.settings(context)['mode']=='workspace' and files.settings(context)['workspace']!=str(root)
            assert not task.files.pending
        study._agent.work.close()


asyncio.run(check())
print('file tools: persistent workspace, previews, approve/deny/expiry/cancel, no self-approval, full mode, traversal, stale edits and account isolation passed')
