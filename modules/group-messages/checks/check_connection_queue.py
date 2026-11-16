"""Connection retries must reuse work and wait behind background delivery."""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

module = load('group-messages')
models = sys.modules[module.__name__ + '.models']
wechat = sys.modules[module.__name__ + '.wechat']


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, 'Worker did not reach the expected state'
        time.sleep(.01)


def check():
    with sandbox('group-messages') as context:
        service = module.Service(context)
        owner = service.owner()
        body = models.WechatConnection(database_dir='synthetic-db', pid=123, acknowledge_local_read=True)
        delivering, finish_delivery = threading.Event(), threading.Event()
        connecting, finish_connection = threading.Event(), threading.Event()
        calls = []

        async def delivery(_owner):
            if not delivering.is_set():
                delivering.set()
                while not finish_delivery.is_set() and not service.stopping.is_set():
                    await asyncio.sleep(.01)

        def connect(request, storage, cancelled, progress):
            calls.append(request)
            connecting.set()
            assert finish_connection.wait(5), 'Connection fixture was not released'
            return {'mode': 'native', 'database_dir': request.database_dir,
                    'groups': [{'id': 'g1', 'name': 'Synthetic course'}]}, {}

        with patch.object(service, 'deliver', delivery), patch.object(wechat, 'connect', connect):
            service.start()
            try:
                assert delivering.wait(5)
                # A periodic delivery is not a user operation: accept one pending connection.
                assert service.queue('connect', 'wechat', body)['queued']
                assert service.status()['queued_task'] == {'kind': 'connect', 'source': 'wechat'}
                assert service.queue('connect', 'wechat', body)['queued'], 'Queued retry must reuse the pending request'
                different = body.model_copy(update={'pid': 456})
                try:
                    service.queue('connect', 'wechat', different)
                except HTTPException as error:
                    assert error.status_code == 409
                else:
                    raise AssertionError('A different request must not replace the queued connection')
                finish_delivery.set()
                assert connecting.wait(5)
                result = service.queue('connect', 'wechat', body)
                assert result.get('running') and not result['queued'], 'Active retry must reuse the current connection'
                public = json.dumps(service.status())
                assert 'synthetic-db' not in public and 'acknowledge_local_read' not in public, 'Private request data must stay out of status'
                finish_connection.set()
                wait_for(lambda: service.status()['sources']['wechat']['connected'] and not service.status()['running'])
                assert len(calls) == 1, 'Repeated submissions must perform one authorization'
                assert len(service.status()['sources']['wechat']['groups']) == 1
                assert not service.status()['queued'] and service.status()['queued_task'] is None
            finally:
                finish_delivery.set()
                finish_connection.set()
                service.close()


if __name__ == '__main__':
    check()
    print('PASS: connection queues behind delivery, retries reuse queued/running authorization, status excludes request data')
