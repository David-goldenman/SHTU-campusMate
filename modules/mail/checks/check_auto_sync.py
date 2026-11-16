"""Synthetic IMAP lifecycle checks; no real credentials, mail, or AI."""
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from checks.module_support import Auth, load, sandbox
from backend.services.auth import ImapUnavailable, LoginRequired

package = load('mail')
auto_module = sys.modules[package.__name__ + '.auto_sync']


class Mailbox:
    def __init__(self):
        self.uids, self.flags, self.epoch = [1, 2], {}, '1'
        self.headers = self.bodies = self.scans = self.closed = 0
        self.failure = None
        self.header_failure = False
        self.hook = None
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.sock = self

    def shutdown(self, _):
        self.release.set()

    def select(self, folder, readonly=True):
        assert folder == 'INBOX' and readonly
        return 'OK', [str(len(self.uids)).encode()]

    def response(self, name):
        assert name == 'UIDVALIDITY'
        return name, [self.epoch.encode()]

    def uid(self, command, *args):
        if command == 'SEARCH':
            self.scans += 1
            if self.failure:
                raise self.failure
            if self.hook:
                hook, self.hook = self.hook, None
                hook()
            if self.block:
                self.entered.set()
                assert self.release.wait(3), 'Cancellation must close a blocked probe'
                raise OSError('connection closed')
            return 'OK', [' '.join(map(str, self.uids)).encode()]
        assert command == 'FETCH'
        values = [int(uid) for uid in args[0].split(',')]
        if args[1] == '(UID FLAGS)':
            return 'OK', [f'{uid} (UID {uid} FLAGS ({self.flags.get(uid, "")}))'.encode() for uid in values]
        if 'HEADER.FIELDS' in args[1]:
            assert 'BODY.PEEK' in args[1]
            if self.header_failure:
                raise OSError('synthetic headers unavailable')
            self.headers += 1
            return 'OK', [(f'{uid} (UID {uid} FLAGS ({self.flags.get(uid, "")}))'.encode(),
                           f'From: fixture@example.edu\r\nSubject: Notice {uid}\r\nDate: Thu, 22 Oct 2026 12:00:00 +0800\r\n\r\n'.encode()) for uid in values]
        assert args[1] == '(BODY.PEEK[])'
        self.bodies += 1
        return 'OK', [(b'1 (BODY[]', b'Content-Type: text/plain; charset=utf-8\r\n\r\nSynthetic body')]


class ImapAuth(Auth):
    def __init__(self, mailbox):
        super().__init__(lambda _: None)
        self.mailbox, self.session, self.state = mailbox, 'session-1', 'ready'

    def get_status(self, provider):
        return {**super().get_status(provider), 'status': self.state, 'session_revision': self.session}

    @contextmanager
    def imap_connection(self, provider, **kwargs):
        assert 0 < kwargs['timeout'] <= 20
        try:
            yield self.mailbox
            self.state = 'ready'
        except LoginRequired:
            self.state = 'login_required'
            raise
        except ImapUnavailable:
            self.state = 'error'
            raise
        finally:
            self.mailbox.closed += 1


@contextmanager
def fixture():
    with sandbox('mail') as context:
        box = Mailbox()
        context.auth = ImapAuth(box)
        context.ai.generate = lambda **_: (_ for _ in ()).throw(AssertionError('Automatic sync must not invoke AI'))
        app = FastAPI()
        app.include_router(package.create_router(context))
        try:
            yield context, box, package._source, package._auto_sync, app
        finally:
            package.stop(context)


def check(controller, source):
    controller.deadline = 0
    controller.check()
    if source.future:
        source.future.result(timeout=4)


with fixture() as (context, box, source, auto, app):
    check(auto, source)
    assert source.snapshot()['status'] == 'ready'
    assert box.headers == 1 and box.bodies == 0
    stable = auto.status()['revision']
    updated = source.snapshot()['updated_at']
    check(auto, source)
    assert box.headers == 1 and box.bodies == 0 and auto.status()['revision'] == stable
    assert source.snapshot()['updated_at'] == updated
    box.flags[2] = r'\Recent'
    check(auto, source)
    assert box.headers == 1 and auto.status()['revision'] == stable
    box.uids = [2, 3]  # same count, simultaneous delete + receive
    check(auto, source)
    assert [m['source_id'] for m in source.snapshot()['data']['messages']] == ['3', '2']
    box.uids = list(range(1, 151))  # a batch, cap at newest 100
    check(auto, source)
    data = source.snapshot()['data']
    assert len(data['messages']) == 100 and data['metadata']['total'] == 150
    assert data['messages'][0]['source_id'] == '150' and data['messages'][-1]['source_id'] == '51'
    box.flags[150] = r'\Seen'
    check(auto, source)
    assert source.snapshot()['data']['messages'][0]['unread'] is False
    owner = source.owner()
    model = package._intelligence
    first = source.snapshot()['data']['messages'][0]
    preferences = model.preferences()
    before_fingerprint = model._prepared(first, preferences, context.ai.settings(), owner)['fingerprint']
    context.store.write('bodies', {'owner': owner, 'value': {'mail:150': {'body_text': 'old epoch'}}})
    context.store.write('labels', {'owner': owner, 'value': {'mail:150': {'by': 'manual', 'label': 'old'}}})
    context.store.write('reviews:' + owner, {'mail:150': {'old': True}})
    context.store.write('preferences:' + owner, {'major': 'preserved'})
    box.epoch = '2'
    check(auto, source)
    assert source.snapshot()['data']['messages'][0]['body_text'] == ''
    new_first = source.snapshot()['data']['messages'][0]
    assert model._prepared(new_first, preferences, context.ai.settings(), owner)['fingerprint'] != before_fingerprint
    assert context.store.read('bodies')['value'] == {}
    assert context.store.read('labels')['value'].get('mail:150', {}).get('by') != 'manual'
    assert context.store.read('reviews:' + owner, {}) == {}
    assert context.store.read('preferences:' + owner)['major'] == 'preserved'
    with TestClient(app) as client:
        status = client.get('/auto-sync').json()
        assert status['enabled'] and status['interval_seconds'] == 60
        assert not any('password' in key or 'secret' in key for key in status)
        assert client.put('/auto-sync', json={'enabled': False, 'owner': 'stale'}).status_code == 409
        assert client.put('/auto-sync', json={'enabled': False, 'owner': owner}).json()['state'] == 'paused'
        scans = box.scans
        check(auto, source)
        assert box.scans == scans
        replacement = auto_module.AutoSync(context, source)
        assert replacement.status()['enabled'] is False  # persistence across reload
        source.on_change = auto.source_changed
        context.auth.revision = 'account-two'
        assert auto.status()['enabled'] is True
        context.auth.revision = 'synthetic-account-one'
        assert auto.status()['enabled'] is False

with fixture() as (context, box, source, auto, _):
    check(auto, source)
    updated = source.snapshot()['updated_at']
    for delay in (60, 120, 240, 300, 300):
        box.failure = OSError('synthetic offline')
        check(auto, source)
        assert auto.status()['state'] == 'retrying'
        assert delay - 1 < auto.deadline - time.monotonic() <= delay, (delay, auto.failures)
        assert source.snapshot()['updated_at'] == updated
        assert source.snapshot()['status'] == 'error'
        failed = context.store.read(source.sync_key)
        assert failed['last_success_at'] == updated, 'Probe failures must retain the last successful synchronization'
        assert failed['diagnostic']['code'] == 'source_service_error' and failed['diagnostic']['operation_id']
    box.failure = None
    check(auto, source)
    assert auto.status()['state'] == 'watching' and auto.failures == 0
    box.failure = LoginRequired('synthetic rejection')
    check(auto, source)
    assert auto.status()['state'] == 'login_required'
    scans = box.scans
    check(auto, source)
    assert box.scans == scans
    box.failure, context.auth.session = None, 'session-2'
    check(auto, source)
    assert auto.status()['state'] == 'watching'
    box.uids.append(3)
    box.hook = lambda: setattr(context.auth, 'session', 'session-3')
    old = source.snapshot()['updated_at']
    check(auto, source)
    assert source.snapshot()['updated_at'] == old  # old credential result discarded
    check(auto, source)
    assert len(source.snapshot()['data']['messages']) == 3
    box.hook = lambda: setattr(context.auth, 'revision', 'account-two')
    check(auto, source)
    assert source.snapshot()['data']['messages'] == []

with fixture() as (context, box, source, auto, _):
    box.header_failure = True
    for delay in (60, 120, 240, 300):
        check(auto, source)
        auto.source_changed()  # duplicate queue notification must not double backoff
        assert delay - 1 < auto.deadline - time.monotonic() <= delay
    box.header_failure = False
    check(auto, source)
    assert auto.status()['state'] == 'watching'

for action in ('pause', 'close'):
    with fixture() as (context, box, source, auto, _):
        box.block = True
        auto.start()  # lifecycle starts and checks without a browser
        assert box.entered.wait(2)
        if action == 'pause':
            auto.set_enabled(False)
            until = time.monotonic() + 2
            while auto.active and time.monotonic() < until:
                time.sleep(.01)
            assert not auto.active and auto.status()['state'] == 'paused'
        else:
            auto.close()
            assert not auto.thread.is_alive() and not auto.active
        assert context.auth.state != 'login_required' and box.closed

with fixture() as (context, box, source, auto, _):
    check(auto, source)
    before = source.snapshot()['updated_at']
    prior_state = context.store.read(source.sync_key)
    reports = []
    context.runtime = type('Runtime', (), {'watch': lambda *args: None,
        'record_source': lambda self, key, state, **kwargs: reports.append(state)})()
    box.block = True
    source.sync(automatic=True)
    assert box.entered.wait(2)
    auto.set_enabled(False)
    source.future.result(timeout=3)
    assert source.snapshot()['status'] == 'ready' and source.snapshot()['updated_at'] == before
    assert auto.status()['state'] == 'paused'
    assert context.store.read(source.sync_key) == prior_state, 'Pausing background sync must preserve last-success and diagnostics'
    assert reports[-1]['status'] == 'ready', 'Runtime diagnostics must observe the restored source state'

for changed in ('session', 'revision'):
    with fixture() as (context, box, source, auto, _):
        auto.observe()
        box.block = True
        source.sync()
        assert box.entered.wait(2)
        setattr(context.auth, changed, 'replacement-' + changed)
        auto.observe()
        assert box.release.is_set(), 'Credential/account changes must close old in-flight IMAP sockets'
        source.future.result(timeout=3)
        assert not source.snapshot()['data']['messages'], 'Old connection must never publish into the replacement identity'

with fixture() as (context, box, source, auto, _):
    auto.observe()
    box.block = True
    assert source.sync()['queued']
    assert box.entered.wait(2)
    assert not source.sync()['queued']
    auto.check()
    assert box.scans == 1, 'Manual and automatic work must share the queue'
    auto.close()
    source.future.result(timeout=3)

print('mail auto-sync: UID/flags, batches, no-op reads, retry/auth recovery, epochs, ownership, pause, cleanup and queue coalescing passed')
