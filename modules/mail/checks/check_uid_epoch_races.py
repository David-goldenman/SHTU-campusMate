"""Deterministic UID epoch/credential races; synthetic mailbox and blocked mocks only."""
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from checks.module_support import Auth, load, sandbox

package = load('mail')


class Box:
    def __init__(self, epoch):
        self.epoch = epoch
    def response(self, name):
        return name, [self.epoch.encode()]


class MailAuth(Auth):
    def __init__(self):
        super().__init__(lambda _: None)
        self.mailbox, self.epoch, self.session = True, '1', 'session-1'
    def get_status(self, provider):
        return {**super().get_status(provider), 'session_revision': self.session}
    @contextmanager
    def imap_connection(self, provider, **kwargs):
        yield Box(self.epoch)


def inbox(mailbox, previous):
    return {'messages': [{'id': 'mail:1', 'source': 'mail', 'source_id': '1', 'title': 'Synthetic notice',
                          'sender': '', 'received_at': None, 'unread': True, 'url': 'https://mail.shanghaitech.edu.cn/', 'body_text': ''}],
            'metadata': {'uid_validity': mailbox.epoch, 'transport': 'imap'}, 'issues': []}


@contextmanager
def fixture():
    with sandbox('mail') as context, patch.object(package, 'imap_inbox', inbox):
        context.auth = MailAuth()
        app = FastAPI()
        app.include_router(package.create_router(context))
        source = package._source
        source.run()
        try:
            with TestClient(app) as client:
                yield context, source, client
        finally:
            package.stop(context)


def body_race():
    with fixture() as (context, source, client), ThreadPoolExecutor(max_workers=2) as pool:
        read_started, read_release, fetch_done, publish_release = [threading.Event() for _ in range(4)]
        def read(mailbox, uid):
            if mailbox.epoch == '1':
                read_started.set()
                assert read_release.wait(4)
            text = 'OLD EPOCH BODY' if mailbox.epoch == '1' else 'NEW EPOCH BODY'
            return {'body_text': text, 'body_html': '<p>' + text + '</p>'}
        original_fetch = source.fetch
        def held_publish(remote, previous):
            result = original_fetch(remote, previous)
            fetch_done.set()
            assert publish_release.wait(4)
            return result
        with patch.object(package, 'imap_read_message', read):
            old = pool.submit(client.get, '/message', params={'message_id': 'mail:1'})
            assert read_started.wait(2)
            context.auth.epoch = '2'
            source.fetch = held_publish
            publication = pool.submit(source.run)
            try:
                assert fetch_done.wait(2)
                read_release.set()
                old_result = old.result(timeout=3)
            finally:
                read_release.set()
                publish_release.set()
            publication.result(timeout=3)
            source.fetch = original_fetch
            assert old_result.status_code == 409, 'An old-epoch read must not repopulate cache during the invalidation/publication gap'
            assert source.snapshot()['data']['metadata']['uid_validity'] == '2'
            current = client.get('/message', params={'message_id': 'mail:1'})
            assert current.status_code == 200 and current.json()['body_text'] == 'NEW EPOCH BODY', 'Reused UID must never return an old-epoch cached body'
            assert context.store.read('bodies')['value']['mail:1']['uid_validity'] == '2'


def labels_race():
    with fixture() as (context, source, client), ThreadPoolExecutor(max_workers=1) as pool:
        started, release = threading.Event(), threading.Event()
        token = client.post('/agent/token').json()['token']
        def generate(**kwargs):
            started.set()
            assert release.wait(4)
            return {'content': {'labels': [{'message_id': 'mail:1', 'label': 'OLD EPOCH LABEL'}]}}
        context.ai.generate = generate
        pending = pool.submit(client.post, '/ai-classify', json={'message_ids': ['mail:1']})
        try:
            assert started.wait(2)
            context.auth.epoch = '2'
            source.run()
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 409, 'Delayed AI classifications must reject a UID epoch change'
        assert all(value.get('label') != 'OLD EPOCH LABEL' for value in client.get('/labels').json()['labels'].values())
        assert client.get('/agent/pending', headers={'Authorization': 'Bearer ' + token}).status_code == 401, 'Agent tokens must be revoked across UID reuse'


def credential_race():
    with fixture() as (context, source, client):
        snapshot = client.get('/snapshot').json()
        assert snapshot['account_revision'] == source.owner() and snapshot['session_revision'] == 'session-1'
        original_api = context.api
        async def switch_session(module_id, path='/snapshot', **kwargs):
            result = await original_api(module_id, path, **kwargs)
            if module_id == 'campus-agent' and path == '/queue':
                # Account A -> B -> A can restore the owner while credentials change.
                context.auth.session = 'session-2'
            return result
        context.api = switch_session
        assert client.get('/intelligence').status_code == 409, 'Same-owner credential generations must reject mixed intelligence responses'


def legacy_imap_cache():
    with fixture() as (context, source, client):
        owner = source.owner()
        snapshot = context.store.read('snapshot')
        snapshot['data']['metadata'].pop('uid_validity')
        context.store.write('snapshot', snapshot)
        context.store.delete('imap-epoch')
        context.store.write('bodies', {'owner': owner, 'value': {'mail:1': {'body_text': 'UNQUALIFIED OLD BODY', 'body_html': '<p>old</p>'}}})
        context.store.write('labels', {'owner': owner, 'value': {'mail:1': {'label': 'UNQUALIFIED OLD LABEL', 'by': 'manual'}}})
        assert client.get('/message', params={'message_id': 'mail:1'}).status_code == 409, 'Legacy IMAP caches require a verified epoch before serving UID bodies'
        source.future.result(timeout=3)
        assert not context.store.read('bodies')['value']
        assert client.get('/labels').json()['labels'].get('mail:1', {}).get('label') != 'UNQUALIFIED OLD LABEL'


checks = {'body': body_race, 'labels': labels_race, 'credentials': credential_race, 'legacy': legacy_imap_cache}
for name, check in checks.items():
    if len(sys.argv) == 1 or sys.argv[1] == name:
        check()
        print('PASS: mail ' + name + ' epoch/credential race')
