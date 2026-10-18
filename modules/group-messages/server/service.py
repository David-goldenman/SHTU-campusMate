"""One module-owned worker for local collection, extraction and delivery."""
import asyncio
import copy
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from backend.services.campus.analysis import account_revision
from . import extraction, qq, wechat
from .effects import Effects
from .messages import Messages, identity, stamp
from .native.crypto import NativeError

SOURCES = ('wechat', 'qq')
ERRORS = {
    'wechat_live_windows_required': '本机微信读取需要 Windows 64 位环境；也可导入已有可读快照。',
    'wechat_live_keys_incomplete': '当前授权无法完整读取数据库，请重新连接自己的微信。',
    'wechat_live_key_changed': '微信密钥已变化，请重新授权。',
    'wechat_live_source_busy': '微信正在写入数据，本轮保留旧快照，稍后重试。',
    'wechat_live_page_integrity_failed': '微信数据校验失败，已保留上次快照。',
    'wechat_live_version_unavailable': '无法确认微信版本，已暂停；请正常打开微信后重新检查。',
    'wechat_live_versions_ambiguous': '发现多个微信版本，已暂停；请退出多余版本后检查。',
    'wechat_live_version_changed_during_check': '读取期间微信发生更新，结果已丢弃，请重新检查兼容性。',
    'wechat_live_disk_full': '本机可用空间不足，请释放空间后重试。',
    'wechat_live_storage_limit': '微信数据超过本轮读取上限，已保留旧快照。',
    'wechat_message_limit': '所选群单轮超过 20000 条消息，请缩短读取范围。',
    'wechat_snapshot_in_use': '请选择已完成导出的静态快照，活动 WAL 数据应使用本机同步。',
    'wechat_snapshot_encrypted': '这是加密数据库，请使用本机授权入口或选择已有可读快照。',
}


class Service:
    def __init__(self, context):
        self.context = context
        self.lock = threading.RLock()
        self.stopping, self.cancelled, self.wake = threading.Event(), threading.Event(), threading.Event()
        self.thread, self.queued, self.running = None, None, None
        self.next_sync, self.next_extract, self.next_version = {}, {}, {}
        self.messages = Messages(context.data_dir)
        self.effects = Effects(self)

    def owner(self):
        return account_revision(self.context)

    def check(self, owner, *, job=False, source=None, revision=None):
        if self.stopping.is_set() or owner != self.owner() or job and self.cancelled.is_set():
            raise HTTPException(409, '账号或处理状态已更新，本次结果未继续写入。')
        if source and self.sources(owner).get(source, {}).get('revision') != revision:
            raise HTTPException(409, '来源或选群设置已变化，请重新处理。')

    def sources(self, owner=None):
        return self.context.store.read('sources:' + (owner or self.owner()), {})

    def save_source(self, owner, source, config):
        values = self.sources(owner)
        values[source] = config
        self.context.store.write('sources:' + owner, values)

    def secret_key(self, owner, source, connection):
        return 'connection:' + owner + ':' + source + ':' + connection

    def storage(self, owner, connection):
        return self.context.data_dir / 'wechat' / owner / connection

    def progress(self, phase, current, total):
        with self.lock:
            if self.running:
                self.running.update(phase=phase, current=current, total=total)

    def configuration(self, owner, source):
        config = self.sources(owner).get(source)
        if source not in SOURCES or not config:
            raise HTTPException(409, '请先连接消息来源。')
        return config

    def selected_group(self, owner, source, gid):
        config = self.configuration(owner, source)
        group = next((row for row in config.get('selected', []) if row['id'] == gid), None)
        if group is None:
            raise HTTPException(404, '这个群未被选择。')
        return config, group

    def all_items(self, owner):
        return self.context.store.read('items:' + owner, {})

    def visible(self, item, sources):
        config = sources.get(item['source'], {})
        return config.get('connection') == item['connection'] and any(group['id'] == item['group_id'] for group in config.get('selected', []))

    def current_item(self, owner, item_id):
        self.check(owner)
        item = self.all_items(owner).get(item_id)
        if item is None or not self.visible(item, self.sources(owner)):
            raise HTTPException(404, '事项不属于当前选群范围。')
        return item

    def save_item(self, owner, item):
        values = self.all_items(owner)
        values[item['id']] = item
        self.context.store.write('items:' + owner, values)

    def items(self):
        with self.lock:
            owner = self.owner()
            sources = self.sources(owner)
            return {'items': sorted((item for item in self.all_items(owner).values() if self.visible(item, sources)), key=lambda item: item['updated_at'], reverse=True),
                    'account_revision': owner}

    def status(self):
        with self.lock:
            owner = self.owner()
            values = self.sources(owner)
            public = {}
            for source in SOURCES:
                config = values.get(source, {})
                public[source] = {key: config.get(key) for key in ('connection', 'mode', 'account_label', 'base_url', 'database_dir', 'enabled', 'selected', 'groups',
                    'history_days', 'interval_seconds', 'allow_ai', 'last_synced_at', 'last_extracted_at', 'error', 'coverage', 'approved_version', 'pending_version', 'compatible', 'revision')}
                public[source]['connected'] = bool(config)
                if not config:
                    public[source]['error'] = self.context.store.read('connection-error:' + owner + ':' + source)
            ai = self.context.ai.settings()
            return {'sources': public, 'running': copy.deepcopy(self.running) if self.running and self.running['owner'] == owner else None,
                    'queued': bool(self.queued and self.queued['owner'] == owner), 'account_revision': owner,
                    'ai': {key: ai.get(key) for key in ('enabled', 'provider', 'model', 'key_saved')},
                    'notice': '只处理所选群。每次同步更新近 7/30 天的聊天窗口；提取事项及引用保留至清除模块数据。图片、语音和附件正文暂未读取。'}

    def queue(self, kind, source, body=None):
        if source not in SOURCES:
            raise HTTPException(404, '未知消息来源。')
        with self.lock:
            if self.running or self.queued:
                raise HTTPException(409, '正在处理上一项操作，可先暂停并等待结束。')
            owner = self.owner()
            if kind == 'extract':
                self.selected_group(owner, source, body.group_id)
            elif kind in {'sync', 'compatibility'}:
                self.configuration(owner, source)
            self.queued = {'kind': kind, 'source': source, 'body': body, 'owner': owner}
            if kind == 'extract':
                self.queued.update(group_id=body.group_id, manual=True)
            self.wake.set()
        return {'queued': True}

    async def select(self, source, body):
        owner = self.owner()
        with self.lock:
            current = self.configuration(owner, source)
            revision = current['revision']
            if body.expected_revision != revision:
                raise HTTPException(409, '来源设置已变化，请重新读取后保存。')
            known = {row['id']: row for row in current['groups']}
        ids = [row.id for row in body.groups]
        if len(ids) != len(set(ids)) or any(gid not in known for gid in ids):
            raise HTTPException(422, '请选择当前连接提供的群，不能重复选择。')
        if source == 'wechat' and body.interval_seconds not in {300, 900, 1800}:
            raise HTTPException(422, '微信同步间隔为 5、15 或 30 分钟。')
        if any(row.auto_extract for row in body.groups) and not body.allow_ai:
            raise HTTPException(422, '开启自动整理前，请确认将所选群的相关正文发送至当前 AI 服务。')
        catalog = {}
        if any(row.course_id for row in body.groups):
            response = await self.context.api('courses', '/snapshot')
            if response.status_code != 200:
                raise HTTPException(409, '课程中心不可用，请先启用后关联课程。')
            catalog = {row['id']: row for row in response.json()['data']['courses']}
        selected = []
        for row in body.groups:
            course = catalog.get(row.course_id)
            if row.course_id and course is None:
                raise HTTPException(409, '所选课程已更新，请刷新课程列表。')
            value = row.model_dump()
            value.update(name=known[row.id]['name'], course={key: course[key] for key in ('id', 'title', 'term', 'course_ids') if key in course} if course else {})
            selected.append(value)
        with self.lock:
            self.check(owner, source=source, revision=revision)
            config = self.configuration(owner, source)
            if config.get('pending_version'):
                if body.enabled and (not body.confirm_compatible or not config.get('compatible')):
                    raise HTTPException(409, '微信版本已变化，请检查兼容性并确认后恢复同步。')
                if body.confirm_compatible and config.get('compatible'):
                    config['approved_version'] = config.pop('pending_version')
                    config['client_executable'] = config.pop('pending_executable', config.get('client_executable'))
                    config.pop('compatible', None)
            old = {row['id']: row for row in config.get('selected', [])}
            for row in selected:
                policy = lambda item: {key: item.get(key) for key in ('course', 'trusted_senders', 'auto_extract', 'auto_apply')}
                if row['id'] not in old or policy(row) != policy(old[row['id']]):
                    self.context.store.delete(self.cursor_key(owner, source, config['connection'], row['id']))
            config.update(selected=selected, enabled=body.enabled, interval_seconds=body.interval_seconds,
                          history_days=body.history_days, allow_ai=body.allow_ai, revision=uuid4().hex, error=None, source_state=None)
            self.cancelled.set()
            self.save_source(owner, source, config)
            self.context.store.delete('connection-error:' + owner + ':' + source)
            self.next_sync[(owner, source)] = 0
            self.wake.set()
        return self.status()

    def pause(self, source):
        with self.lock:
            owner = self.owner()
            config = self.configuration(owner, source)
            config.update(enabled=False, revision=uuid4().hex)
            self.save_source(owner, source, config)
            self.cancelled.set()
            if self.queued and self.queued['source'] == source:
                self.queued = None
            self.wake.set()
        return self.status()

    def forget(self, source):
        with self.lock:
            if self.running or self.queued:
                self.cancelled.set()
                raise HTTPException(409, '正在停止读取，请等待结束后移除连接。')
            owner = self.owner()
            config = self.configuration(owner, source)
            self.context.secrets.delete(self.secret_key(owner, source, config['connection']))
            values = self.sources(owner)
            values.pop(source, None)
            self.context.store.write('sources:' + owner, values)
        return self.status()

    def stop_current(self):
        with self.lock:
            self.cancelled.set()
            task = self.running or self.queued
            self.queued = None
            if task and task['owner'] == self.owner() and task['source'] in self.sources():
                self.pause(task['source'])
        return self.status()

    def cursor_key(self, owner, source, connection, gid):
        return 'cursor:' + owner + ':' + identity(source, connection, gid)

    def _connect(self, task):
        owner, source, body = task['owner'], task['source'], task['body']
        old = self.sources(owner).get(source, {})
        connection = uuid4().hex
        storage = self.storage(owner, connection)
        if task['kind'] == 'snapshot':
            result, secret = wechat.inspect_snapshot(body.path), {}
        elif source == 'wechat':
            result, secret = wechat.connect(body, storage, self.cancelled, self.progress)
        else:
            result, secret = qq.connect(body, self.cancelled)
        with self.lock:
            self.check(owner, job=True)
            # Reauthorizing the same account keeps stable message IDs, but requires a fresh selection.
            same = old and (source == 'qq' and old.get('account') == result.get('account') or source == 'wechat' and
                           old.get('mode') == result.get('mode') and (old.get('database_dir') or old.get('snapshot')) == (result.get('database_dir') or result.get('snapshot')))
            if same:
                connection = old['connection']
            config = {**result, 'connection': connection, 'revision': uuid4().hex, 'selected': [], 'enabled': False,
                      'allow_ai': False, 'interval_seconds': 300 if source == 'wechat' else 20, 'history_days': 7, 'coverage': {}, 'error': None,
                      'account_label': ('QQ · ' + result['account'][-4:]) if source == 'qq' else '已连接的本机微信'}
            if secret:
                self.context.secrets.save(self.secret_key(owner, source, connection), secret)
            if old and old.get('connection') != connection:
                self.context.secrets.delete(self.secret_key(owner, source, old['connection']))
            self.save_source(owner, source, config)
            self.context.store.delete('connection-error:' + owner + ':' + source)

    def _sync(self, task):
        owner, source = task['owner'], task['source']
        with self.lock:
            config = self.configuration(owner, source)
            revision = config['revision']
            if not config.get('selected'):
                raise HTTPException(409, '请先选择需要同步的群。')
            secret = self.context.secrets.get(self.secret_key(owner, source, config['connection']))
        storage = self.storage(owner, config['connection'])
        report = None
        try:
            def pause_for_version(client):
                with self.lock:
                    self.check(owner, job=True, source=source, revision=revision)
                    current = self.configuration(owner, source)
                    current.update(enabled=False, pending_version=client.version, compatible=False, error='已暂停同步，正在检查微信版本兼容性。')
                    self.save_source(owner, source, current)
            report = (wechat.synchronize(config, secret, storage, self.cancelled, self.progress, compatibility=task['kind'] == 'compatibility', pause_for_version=pause_for_version) if source == 'wechat'
                      else qq.synchronize(config, secret, self.cancelled))
            with self.lock:
                self.check(owner, job=True, source=source, revision=revision)
                current = self.configuration(owner, source)
                if report.get('unchanged'):
                    current.update(last_synced_at=stamp(), error=None)
                    self.save_source(owner, source, current)
                    return
                since = (datetime.now(timezone.utc) - timedelta(days=config['history_days'])).isoformat()
                changed = 0
                for gid, rows in report.get('messages', {}).items():
                    changed += self.messages.ingest(owner, source, config['connection'], gid, rows, since)
                current.update(last_synced_at=stamp(), error=None, last_changed=changed)
                for key in ('source_state', 'next_expiry', 'snapshot', 'coverage', 'wal_commits'):
                    if key in report:
                        current[key] = report[key]
                if source == 'wechat':
                    current['coverage'] = {group['id']: {'last_success': current['last_synced_at'], 'history_days': config['history_days'],
                        'possible_gap': False, 'scope': '电脑微信已同步到本机的所选范围；不包含客户端尚未下载的历史。'} for group in config['selected']}
                if report.get('failed_groups'):
                    current['error'] = '部分群读取失败，已保留其旧记录；请查看各群覆盖状态。'
                self.save_source(owner, source, current)
            if source == 'wechat':
                wechat.prune(report, storage)
        except wechat.VersionChanged as error:
            with self.lock:
                self.check(owner, job=True, source=source, revision=revision)
                current = self.configuration(owner, source)
                current.update(enabled=False, pending_version=error.client.version, pending_executable=error.client.executable,
                               compatible=error.compatible, error='微信版本需要确认；本机读取检查通过，可核对选群后恢复。' if error.compatible else '现有授权未通过兼容检查，请重新连接。', revision=uuid4().hex)
                self.save_source(owner, source, current)
        except Exception:
            if source == 'wechat' and report and self.sources(owner).get(source, {}).get('snapshot') != report.get('snapshot'):
                wechat.discard(report, storage)
            raise

    def _extract(self, task):
        owner, source, gid = task['owner'], task['source'], task['group_id']
        with self.lock:
            config, group = self.selected_group(owner, source, gid)
            revision = config['revision']
            if not task.get('manual') and not (config['enabled'] and config['allow_ai'] and group['auto_extract']):
                return
            if not self.context.ai.settings().get('enabled'):
                raise HTTPException(409, '请先在设置中配置并启用 AI；已同步聊天保留在本机。')
            key = self.cursor_key(owner, source, config['connection'], gid)
            cursor = self.context.store.read(key, 0)
            batch = self.messages.batch(owner, source, config['connection'], gid, cursor)
            if batch is None:
                return
            existing = [item for item in self.all_items(owner).values() if item['source'] == source and item['connection'] == config['connection'] and item['group_id'] == gid]
            if any(self.context.store.read('operation:' + owner + ':' + item['id']) for item in existing):
                raise HTTPException(409, '上次更新的结果尚未确认，请先在事项卡片重试原操作；新增消息仍保留。')
            self.check(owner, job=True)
        results = extraction.run(self.context, batch, group, existing, self.cancelled)
        with self.lock:
            self.check(owner, job=True, source=source, revision=revision)
            if not self.messages.versions_match(owner, batch['versions']):
                raise HTTPException(409, '原消息已更新，请重新整理。')
            values = self.all_items(owner)
            for finding in results:
                iid = finding['target_id'] or 'group-item:' + identity(config['connection'], gid, group.get('course_id'), finding['kind'], finding['object_key'].strip().casefold())
                old = values.get(iid)
                refs = {(ref['message_id'], ref['quote']): ref for ref in (old or {}).get('citations', []) + finding['citations']}
                core = {key: finding[key] for key in ('object_key', 'kind', 'action', 'title', 'summary', 'date', 'due_at', 'starts_at', 'ends_at', 'location')}
                unchanged = old and all(old.get(key) == value for key, value in core.items())
                new_refs = [ref for ref in finding['citations'] if ref['message_id'] in batch['new_ids']]
                trusted = bool(new_refs) and all(ref['sender_id'] in group['trusted_senders'] for ref in new_refs)
                uncertain = any(re.search(r'[?？]|可能|听说|据说|暂定|待定|是不是', ref['quote']) for ref in new_refs)
                automatic = bool(group['auto_apply'] and trusted and not uncertain and finding['action'] in {'announce', 'change'} and
                                 finding['time_verified'] and (finding['has_time'] or finding['kind'] in {'notice', 'material'}) and group.get('course_id') and finding['kind'] != 'activity')
                item = {**(old or {}), **core, 'id': iid, 'source': source, 'connection': config['connection'], 'group_id': gid, 'group_name': group['name'],
                        'course': group.get('course', {}), 'citations': list(refs.values())[-50:], 'revision': uuid4().hex,
                        'content_revision': old['content_revision'] if unchanged else uuid4().hex, 'time_verified': finding['time_verified'],
                        'automatic_ready': automatic, 'updated_at': stamp(), 'status': old['status'] if unchanged or old and old['status'] == 'dismissed' else 'pending',
                        'apply_error': (old or {}).get('apply_error') if unchanged else None,
                        'reason': '可信来源与时间已核对。' if automatic else '请核对来源、时间、课程与原事项；活动需要明确参加。'}
                values[iid] = item
            self.context.store.write('items:' + owner, values)
            self.context.store.write(key, batch['cursor'])
            current = self.configuration(owner, source)
            current.update(last_extracted_at=stamp(), error=None)
            self.save_source(owner, source, current)

    async def deliver(self, owner):
        for item in self.all_items(owner).values():
            self.check(owner, job=True)
            if not self.visible(item, self.sources(owner)):
                try:
                    await self.effects.publish(owner, item)
                except HTTPException:
                    pass  # Retry withdrawal when the optional notification module is available.
                continue
            config, group = self.selected_group(owner, item['source'], item['group_id'])
            if config.get('enabled') and config.get('allow_ai') and group.get('auto_apply') and item['status'] == 'pending' and item.get('automatic_ready') and not item.get('apply_error'):
                try:
                    item = await self.effects.apply(owner, item['id'], item['revision'], automatic=True)
                except HTTPException as error:
                    with self.lock:
                        self.check(owner, job=True)
                        current = self.current_item(owner, item['id'])
                        current['apply_error'] = str(error.detail)
                        self.save_item(owner, current)
                        item = current
            try:
                await self.effects.publish(owner, item)
            except HTTPException as error:
                with self.lock:
                    self.check(owner, job=True)
                    current = self.current_item(owner, item['id'])
                    current['publish_error'] = str(error.detail)
                    self.save_item(owner, current)

    def _automatic_task(self, owner):
        now = time.monotonic()
        sources = self.sources(owner)
        # Collect every due source before spending another batch on a large AI backlog.
        for source, config in sources.items():
            if not config.get('enabled') or not config.get('selected'):
                continue
            if now >= self.next_sync.get((owner, source), 0):
                self.next_sync[(owner, source)] = now + config['interval_seconds']
                return {'kind': 'sync', 'source': source, 'owner': owner}
            if source == 'wechat' and config.get('mode') == 'native' and now >= self.next_version.get(owner, 0):
                self.next_version[owner] = now + 60
                try:
                    client = wechat.version.observe_version(config.get('client_executable', ''))
                    if client.version != config.get('approved_version'):
                        return {'kind': 'compatibility', 'source': source, 'owner': owner}
                except NativeError:
                    return {'kind': 'compatibility', 'source': source, 'owner': owner}
        for source, config in sources.items():
            if not config.get('enabled') or not config.get('selected'):
                continue
            if not config.get('allow_ai') or not self.context.ai.settings().get('enabled'):
                continue
            for group in config['selected']:
                key = self.cursor_key(owner, source, config['connection'], group['id'])
                if group['auto_extract'] and now >= self.next_extract.get(key, 0) and self.messages.batch(owner, source, config['connection'], group['id'], self.context.store.read(key, 0)):
                    return {'kind': 'extract', 'source': source, 'group_id': group['id'], 'owner': owner}
        return None

    def loop(self):
        delivery_at = 0
        while not self.stopping.is_set():
            self.wake.wait(1)
            self.wake.clear()
            with self.lock:
                if self.stopping.is_set():
                    return
                owner = self.owner()
                task = self.queued
                self.queued = None
                if task and task['owner'] != owner:
                    task = None
                task = task or self._automatic_task(owner)
                if task is None and time.monotonic() >= delivery_at:
                    task = {'kind': 'deliver', 'source': '', 'owner': owner}
                    delivery_at = time.monotonic() + 30
                if task is None:
                    continue
                self.cancelled.clear()
                self.running = {'kind': task['kind'], 'source': task['source'], 'owner': owner, 'phase': 'working'}
            try:
                if task['kind'] in {'connect', 'snapshot'}:
                    self._connect(task)
                elif task['kind'] in {'sync', 'compatibility'}:
                    self._sync(task)
                elif task['kind'] == 'extract':
                    self._extract(task)
                self.check(owner, job=True)
                asyncio.run(self.deliver(owner))
            except Exception as error:
                with self.lock:
                    if owner == self.owner() and not self.cancelled.is_set() and not self.stopping.is_set() and task['source']:
                        source = task['source']
                        config = self.sources(owner).get(source)
                        text = str(error.detail) if isinstance(error, HTTPException) else ERRORS.get(str(error), str(error) if isinstance(error, qq.APIError) else '本轮处理未完成，请检查连接后重试。')
                        if config:
                            config['error'] = text
                            if isinstance(error, NativeError) and str(error) != 'wechat_live_source_busy' or isinstance(error, qq.APIError) and error.category in {'auth', 'account'}:
                                config.update(enabled=False, revision=uuid4().hex)
                            self.save_source(owner, source, config)
                        else:
                            self.context.store.write('connection-error:' + owner + ':' + source, text)
                        if task['kind'] == 'extract' and config:
                            self.next_extract[self.cursor_key(owner, source, config['connection'], task['group_id'])] = time.monotonic() + 120
            finally:
                with self.lock:
                    self.running = None

    def start(self):
        with self.lock:
            if self.context.store.read('session-running', False):
                owner = self.owner()
                for source, config in self.sources(owner).items():
                    config.update(enabled=False, revision=uuid4().hex, error='上次服务异常退出，请核对范围后重新开启同步。')
                    self.save_source(owner, source, config)
            self.context.store.write('session-running', True)
        self.thread = threading.Thread(target=self.loop, name='group-messages', daemon=True)
        self.thread.start()
        if getattr(self.context, 'runtime', None):
            self.context.runtime.watch('群消息同步与整理', self.thread)

    def close(self):
        self.stopping.set(); self.cancelled.set(); self.wake.set()
        if self.thread:
            self.thread.join()
        self.context.store.write('session-running', False)
