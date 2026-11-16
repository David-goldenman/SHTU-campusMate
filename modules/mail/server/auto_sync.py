"""Account-scoped IMAP metadata checks, owned by the mail module lifecycle."""
import secrets
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from backend.core.diagnostics import operation_scope
from backend.core.errors import failure_metadata
from backend.services.auth import ImapUnavailable, LoginRequired
from backend.services.campus import Source
from .imap import scan

INTERVAL = 60
RETRY_DELAYS = (60, 120, 240, 300)
IO_TIMEOUT = 5


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MailSource(Source):
    """Publish queue/completion changes without polling full snapshots in the UI."""
    on_change = None
    automatic = False

    def identity(self):
        return self.owner(), self.context.auth.get_status('coremail').get('session_revision', 'initial')

    def snapshot(self):
        with self.lock:
            identity = self.identity()
            result = super().snapshot()
            if identity != self.identity():
                raise HTTPException(409, '邮箱账号或凭据已更新，请重新读取。')
            return {**result, 'account_revision': identity[0], 'session_revision': identity[1]}

    def sync(self, *, automatic=False):
        with self.lock:
            if self.future is None or self.future.done():
                self.previous_state = self.context.store.read(self.sync_key, {})
                self.automatic = automatic
            elif not automatic:
                self.automatic = False  # a manual request now shares this work
            result = super().sync()
        if self.on_change:
            self.on_change()
        return result

    def run(self):
        owner, self.abandoned = self.owner(), False
        try:
            super().run()
        finally:
            if self.abandoned and not self.cancelled.is_set() and owner == self.owner():
                saved = self.context.store.read(self.snapshot_key, {})
                status = ('partial' if saved['data'].get('issues') else 'ready') if saved.get('owner') == owner else 'not_synced'
                previous = getattr(self, 'previous_state', {})
                state = previous if previous.get('owner') == owner else {'owner': owner, 'status': status}
                self.context.store.write(self.sync_key, state)
                self._report(state, saved.get('updated_at') if saved.get('owner') == owner else None)
            if self.on_change:
                self.on_change(completed=True)


class AutoSync:
    def __init__(self, context, source: MailSource) -> None:
        self.context, self.source = context, source
        self.lock = threading.RLock()
        self.stopping, self.wake = threading.Event(), threading.Event()
        self.thread: threading.Thread | None = None
        self.active: dict = {}
        self.identity: tuple | None = None
        self.enabled, self.configured = True, False
        self.state, self.message = 'starting', ''
        self.last_checked_at = self.last_synced_at = None
        self.deadline, self.failures = 0.0, 0
        self.blocked = None
        self.serial, self.instance = 0, secrets.token_hex(6)
        self.source_signature = None
        self.source.on_change = self.source_changed

    def credentials(self) -> tuple:
        status = self.context.auth.get_status('coremail')
        configured = bool(getattr(self.context.auth, 'imap_enabled', lambda _: False)('coremail'))
        return self.source.owner(), status.get('session_revision', 'initial'), configured, status.get('status')

    def _state(self, state: str, message: str = '') -> None:
        if (state, message) != (self.state, self.message):
            self.state, self.message = state, message
            self.serial += 1

    def observe(self) -> tuple:
        owner, session, configured, auth_state = self.credentials()
        identity = (owner, session, configured)
        stale_connections = []
        with self.lock:
            if identity != self.identity:
                stale_connections = [mailbox for mailbox, (_, opened_identity) in self.active.items()
                                     if opened_identity != identity]
                self.identity = identity
                self.enabled = self.context.store.read('auto-sync:' + owner, {}).get('enabled', True)
                self.configured = configured
                self.blocked, self.failures, self.deadline = None, 0, 0.0
                saved = self.context.store.read('auto-sync-check:' + owner, {})
                self.last_checked_at = saved.get('last_checked_at')
                snapshot = self.context.store.read(self.source.snapshot_key, {})
                self.last_synced_at = snapshot.get('updated_at') if snapshot.get('owner') == owner else None
                self.source_signature = None
                self.serial += 1
                self._state('starting' if configured else 'not_configured')
            self.source.stale_after = None if configured else 21600
            if not configured:
                self._state('not_configured', '配置 IMAP 后即可在后台自动同步。')
            elif not self.enabled:
                self._state('paused', '自动同步已暂停，仍可手动同步。')
            elif self.blocked == identity and auth_state == 'ready':
                self.blocked, self.deadline = None, 0.0
                self._state('starting')
        for mailbox in stale_connections:
            self.interrupt(mailbox)
        return identity

    def status(self) -> dict:
        identity = self.observe()
        with self.lock:
            declared = self.context.store.read('imap-epoch', {})
            snapshot = self.context.store.read(self.source.snapshot_key, {})
            epoch = declared.get('value') if declared.get('owner') == identity[0] else snapshot.get('data', {}).get('metadata', {}).get('uid_validity') if snapshot.get('owner') == identity[0] else None
            pending = self.enabled and self.configured and self.blocked is None and not self.stopping.is_set()
            return {'enabled': self.enabled, 'configured': self.configured, 'mode': 'polling',
                    'interval_seconds': INTERVAL, 'state': self.state, 'message': self.message,
                    'last_checked_at': self.last_checked_at, 'last_synced_at': self.last_synced_at,
                    'next_check_at': (datetime.now(timezone.utc) + timedelta(seconds=max(0, self.deadline-time.monotonic()))).isoformat() if pending else None,
                    'owner': identity[0], 'session_revision': identity[1], 'uid_validity': epoch, 'revision': f'{self.instance}:{identity[0]}:{self.serial}'}

    def set_enabled(self, enabled: bool, owner: str | None = None) -> dict:
        identity = self.observe()
        with self.lock:
            if owner is not None and owner != identity[0]:
                raise HTTPException(409, '邮箱账号已变化，请刷新后重试。')
            self.context.store.write('auto-sync:' + identity[0], {'enabled': enabled})
            self.enabled, self.deadline = enabled, 0.0
            self.serial += 1
            self._state('starting' if enabled else 'paused')
            probes = [mailbox for mailbox, (purpose, _) in self.active.items()
                      if purpose == 'probe' or purpose == 'sync' and self.source.automatic]
        if not enabled:
            for mailbox in probes:
                self.interrupt(mailbox)
        self.wake.set()
        return self.status()

    @staticmethod
    def interrupt(mailbox) -> None:
        connection = getattr(mailbox, 'sock', None)
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    @contextmanager
    def connection(self, purpose: str = 'sync'):
        identity = self.credentials()[:3]
        with self.context.auth.imap_connection('coremail', timeout=IO_TIMEOUT) as mailbox:
            with self.lock:
                self.active[mailbox] = (purpose, identity)
            # Connection establishment remains bounded; larger header/body reads
            # retain the existing timeout and can be interrupted through the socket.
            if purpose != 'probe' and hasattr(getattr(mailbox, 'sock', None), 'settimeout'):
                mailbox.sock.settimeout(20)
            def cancelled():
                return (self.stopping.is_set() or identity != self.credentials()[:3] or
                        not self.enabled and (purpose == 'probe' or purpose == 'sync' and self.source.automatic))
            try:
                if cancelled():
                    raise HTTPException(409, '邮箱账号或模块状态已更新。')
                yield mailbox
                if cancelled():
                    raise HTTPException(409, '邮箱账号或模块状态已更新，已忽略旧结果。')
            except Exception:
                if cancelled():
                    if purpose == 'sync':
                        self.source.abandoned = True
                    raise HTTPException(409, '邮箱检查已取消，登录信息保持不变。') from None
                raise
            finally:
                with self.lock:
                    self.active.pop(mailbox, None)

    def source_changed(self, *, completed=False) -> None:
        if self.stopping.is_set():
            return
        owner = self.source.owner()
        state = self.context.store.read(self.source.sync_key, {})
        snapshot = self.context.store.read(self.source.snapshot_key, {})
        if state.get('owner') != owner:
            return
        with self.lock:
            if self.identity is None or self.identity[0] != owner:
                return
            signature = (owner, state.get('status'), state.get('message'), snapshot.get('updated_at'))
            if signature == self.source_signature and state.get('status') not in ('error', 'login_required', 'verification_required'):
                return
            if signature != self.source_signature:
                self.source_signature = signature
                self.serial += 1
            if snapshot.get('owner') == owner:
                self.last_synced_at = snapshot.get('updated_at')
            if not self.enabled:
                return
            status = state.get('status')
            if status == 'syncing':
                self._state('syncing', '发现邮件变化，正在同步。')
            elif status in ('ready', 'partial'):
                self.failures, self.blocked = 0, None
                self._state('watching', '后台每分钟检查，有变化时自动同步。')
            elif completed and status in ('login_required', 'verification_required', 'error'):
                self._schedule_failure(status, state.get('message', '邮箱暂时无法同步。'))
        self.wake.set()

    def _schedule_failure(self, status: str, message: str) -> None:
        if status in ('login_required', 'verification_required'):
            self.blocked = self.identity
            self._state('login_required', message)
        else:
            delay = RETRY_DELAYS[min(self.failures, len(RETRY_DELAYS)-1)]
            self.failures += 1
            self.deadline = time.monotonic() + delay
            self._state('retrying', message)

    def check(self) -> None:
        """One due attempt; also exposed to deterministic, synthetic checks."""
        identity = self.observe()
        with self.lock:
            if (self.stopping.is_set() or not self.configured or not self.enabled or
                    self.blocked == identity or time.monotonic() < self.deadline):
                return
            if self.source.future is not None and not self.source.future.done():
                return
        try:
            with self.connection('probe') as mailbox:
                observed = scan(mailbox)
            if identity != self.observe() or not self.enabled or self.stopping.is_set():
                return
            with self.lock:
                self.last_checked_at = now()
                self.context.store.write('auto-sync-check:' + identity[0], {'last_checked_at': self.last_checked_at})
                self.deadline = time.monotonic() + INTERVAL
            snapshot = self.context.store.read(self.source.snapshot_key, {})
            previous = snapshot.get('data', {}).get('metadata', {}).get('imap_state') if snapshot.get('owner') == identity[0] else None
            state = self.context.store.read(self.source.sync_key, {})
            if previous != observed or state.get('status') not in ('ready', 'partial'):
                self.source.sync(automatic=True)
            else:
                with self.lock:
                    self.failures = 0
                    self._state('watching', '后台每分钟检查，有变化时自动同步。')
        except Exception as error:
            if self.stopping.is_set() or identity != self.observe() or not self.enabled:
                return
            if isinstance(error, HTTPException) and error.status_code == 409:
                self.wake.set()
                return
            status = 'login_required' if isinstance(error, LoginRequired) else 'error'
            message = str(error) if isinstance(error, LoginRequired) else str(error.detail) if isinstance(error, HTTPException) else '邮箱检查暂时失败，已保留登录信息和缓存，将稍后重试。'
            with self.lock:
                self.last_checked_at = now()
                self.context.store.write('auto-sync-check:' + identity[0], {'last_checked_at': self.last_checked_at})
            with operation_scope(self.context.id, 'auto-sync', new=True):
                code = 'login_required' if status == 'login_required' else 'source_service_error'
                action = '请检查邮箱账号连接，再重新同步。' if status == 'login_required' else '已保存资料仍可查看，后台会自动重试。'
                state = {'owner': identity[0], 'status': status, 'message': message,
                         'last_success_at': self.source._last_success(identity[0]), 'finished_at': now(),
                         'diagnostic': failure_metadata(code, action)}
                self.context.store.write(self.source.sync_key, state)
                cached = self.context.store.read(self.source.snapshot_key, {})
                self.source._report(state, cached.get('updated_at') if cached.get('owner') == identity[0] else None)
            self.source_changed(completed=True)

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self.loop, name='mail-auto-sync', daemon=True)
        self.thread.start()
        if getattr(self.context, 'runtime', None):
            self.context.runtime.watch('邮箱自动同步', self.thread)

    def loop(self) -> None:
        while not self.stopping.is_set():
            try:
                self.check()
            except Exception:
                if not self.stopping.is_set():
                    with self.lock:
                        self._schedule_failure('error', '暂时无法读取邮箱设置，将稍后重试。')
            # This only checks local credential/settings changes; remote checks
            # have their own 60-second or backoff deadline.
            self.wake.wait(5)
            self.wake.clear()

    def close(self) -> None:
        self.stopping.set()
        self.source.cancelled.set()
        self.wake.set()
        with self.lock:
            connections = list(self.active)
        for mailbox in connections:
            self.interrupt(mailbox)
        if self.thread is not None:
            self.thread.join()
        self.source.on_change = None
