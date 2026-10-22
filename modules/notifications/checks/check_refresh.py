import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import HTTPException
from checks.module_support import load, sandbox

package=load('notifications')

async def check():
    with sandbox('notifications') as context:
        service=package.Notifications(context)
        gate, entered=asyncio.Event(),asyncio.Event()
        calls=[]
        async def assignments():
            calls.append('assignments');entered.set();await gate.wait()
        async def mail(): calls.append('mail')
        service.reconcile_assignments=assignments
        service.reconcile_mail=mail
        first=asyncio.create_task(service.refresh())
        await entered.wait()
        second=asyncio.create_task(service.refresh())
        await asyncio.sleep(0)
        gate.set()
        await asyncio.gather(first,second)
        assert calls==['assignments','mail'] and not service.reconciliations
        await service.refresh()
        assert calls==['assignments','mail']*2, 'A subsequent read must reconcile again'
        gate.clear();entered.clear()
        changed=asyncio.create_task(service.refresh())
        await entered.wait();context.auth.revision='other-account';gate.set()
        try: await changed
        except HTTPException as error: assert error.status_code==409
        else: raise AssertionError('Mixed-account notice data must not be returned')
        assert not service.reconciliations
        gate.clear();entered.clear()
        leader=asyncio.create_task(service.refresh())
        await entered.wait()
        follower=asyncio.create_task(service.refresh());await asyncio.sleep(0)
        follower.cancel()
        try: await follower
        except asyncio.CancelledError: pass
        gate.set();await leader
        service.close()
        try: await service.refresh()
        except HTTPException as error: assert error.status_code==409
        else: raise AssertionError('Stopped modules must not start reconciliation')
    print('notification refresh: shared in-flight reconciliation, fresh later reads, account switch, cancelled follower and module stop passed')

asyncio.run(check())
