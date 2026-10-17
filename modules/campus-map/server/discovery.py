"""Module-owned polling of a fixed public notice list and the public mail API."""
import asyncio
import threading
from copy import deepcopy
from datetime import datetime, timedelta
from urllib.parse import quote
from urllib.request import getproxies
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.services.campus.analysis import account_revision
from .discovery_parser import NOTICE_LIST, public_notice_url, notice_links, notice_text, screen

ZONE = ZoneInfo('Asia/Shanghai')
INTERVAL = 30 * 60


class DiscoveryVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int
    account_revision: str


class DiscoverySettings(DiscoveryVersion):
    enabled: bool
    official: bool = True
    mail: bool = True


class Discovery:
    def __init__(self, context, places):
        self.context, self.places = context, places
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.thread = self.loop = self.task = None
        self.running_owner = self.force_owner = None
        self.generation = 0

    def owner(self):
        return account_revision(self.context)

    def read(self, owner):
        return deepcopy(self.context.store.read('discovery:' + owner, {
            'version': 0, 'settings': {'enabled': False, 'official': True, 'mail': True},
            'items': [], 'seen': {}, 'last_checked': None, 'next_check': None, 'sources': {}, 'error': ''}))

    def save(self, owner, state):
        if owner != self.owner() or self.stopping.is_set():
            raise HTTPException(409, '账号或检查任务已变化，请刷新。')
        state['version'] += 1
        self.context.store.write('discovery:' + owner, state)

    def public(self):
        with self.lock:
            owner = self.owner(); state = self.read(owner)
            if owner != self.owner():
                raise HTTPException(409, '账号已变化，请刷新。')
            return {key: value for key, value in state.items() if key != 'seen'} | {
                'account_revision': owner, 'running': self.running_owner == owner,
                'interval_minutes': 30, 'notice_url': NOTICE_LIST,
                'coverage': '校方公告首页近 90 天的文字；邮箱最近 100 封，每轮最多补读 20 封正文。附件与图片不识别。'}

    def capture(self, body):
        owner = self.owner(); state = self.read(owner)
        if body.account_revision != owner or body.version != state['version']:
            raise HTTPException(409, '账号或自动发现列表已变化，请刷新后重试。')
        return owner, state

    def check(self, owner, generation):
        if self.stopping.is_set() or owner != self.owner() or generation != self.generation:
            raise HTTPException(409, '自动发现已取消或账号已切换。')

    async def fetch(self, client, url, owner, generation):
        self.check(owner, generation)
        if not public_notice_url(url):
            raise ValueError('公告地址不在固定校方来源内。')
        async with asyncio.timeout(15), client.stream('GET', url) as response:
            response.raise_for_status()
            if 'text/html' not in response.headers.get('content-type', ''):
                raise ValueError('公告返回的不是 HTML 页面。')
            content = bytearray()
            async for part in response.aiter_bytes():
                self.check(owner, generation); content.extend(part)
                if len(content) > 1500000:
                    raise ValueError('公告页面超出读取范围。')
        return content.decode('utf-8', errors='replace')

    def ingest(self, owner, generation, sources):
        added = 0
        with self.lock:
            self.check(owner, generation); state = self.read(owner)
            for source in sources:
                proposal = screen(source, self.places, datetime.now(ZONE).date())
                identity = source['source'] + ':' + source['source_id']
                signature = [proposal.get(key) for key in ('title', 'action', 'evidence', 'source_date')] if proposal else [source['title'], None]
                prior = state['seen'].get(identity)
                if prior and prior['signature'] == signature:
                    continue
                for old in state['items']:
                    if old['source'] == source['source'] and old['source_id'] == source['source_id'] and old['state'] == 'pending':
                        old['state'] = 'superseded'
                if proposal:
                    if sum(item['state'] == 'pending' for item in state['items']) >= 300:
                        state['error'] = '待核实线索已达 300 条，请先处理；本轮剩余来源将稍后重试。'
                        break
                    proposal.update(id=uuid4().hex, state='pending', discovered_at=datetime.now(ZONE).isoformat(),
                                    source_revision=(prior or {}).get('revision', 0) + 1,
                                    flags=proposal['flags'] + (['同一来源的文字已更新，请对照既有记录核实。'] if prior else []))
                    state['items'].append(proposal); added += 1
                state['seen'][identity] = {'signature': signature, 'revision': (prior or {}).get('revision', 0) + 1,
                                           'at': datetime.now(ZONE).isoformat()}
            # Keep pending decisions and the latest 500 handled leads; recent-source window bounds seen entries.
            retired = [v for v in state['items'] if v['state'] != 'pending'][-500:]
            state['items'] = [v for v in state['items'] if v['state'] == 'pending'] + retired
            state['seen'] = dict(list(state['seen'].items())[-2000:])
            self.save(owner, state)
        return added

    async def scan(self, owner, generation):
        with self.lock:
            self.check(owner, generation); state = self.read(owner)
            state['error'] = ''; self.save(owner, state); settings = state['settings']
        results = {}; today = datetime.now(ZONE).date()
        if settings['official']:
            count = 0
            try:
                async with httpx.AsyncClient(timeout=8, follow_redirects=False,
                                             proxy=getproxies().get('https'), headers={'User-Agent': 'CampusFramework-campus-map/0.5'}) as client:
                    html = await self.fetch(client, NOTICE_LIST, owner, generation)
                    links = notice_links(html, today)
                    if '/page.htm' not in html:
                        raise ValueError('公告列表结构已变化。')
                    failures = 0
                    for source in links:
                        self.check(owner, generation)
                        try:
                            title, text = notice_text(await self.fetch(client, source['url'], owner, generation))
                            source.update(source='official', title=title or source['title'], text=text)
                            self.ingest(owner, generation, [source]); count += 1
                        except (httpx.HTTPError, ValueError, TimeoutError):
                            failures += 1
                    results['official'] = {'status': 'partial' if failures else 'ready', 'read': count,
                                           'message': f'公告首页近 90 天：读取 {count} 篇，失败 {failures} 篇；未覆盖历史分页、附件或内部公告。'}
            except (httpx.HTTPError, ValueError, OSError, TimeoutError):
                results['official'] = {'status': 'error', 'read': count, 'message': '校方公告暂不可读取，请检查网络或稍后重试；已有线索保留。'}
        if settings['mail']:
            try:
                self.check(owner, generation)
                initial = await self.context.api('mail', '/snapshot', timeout=10)
                self.check(owner, generation)
                if initial.status_code != 200:
                    raise ValueError('邮箱模块未启用或暂不可用，请在设置连接校园邮箱。')
                sync = await self.context.api('mail', '/sync', method='POST', timeout=10)
                self.check(owner, generation)
                snapshot = initial.json()
                for _ in range(5):
                    response = await self.context.api('mail', '/snapshot', timeout=10)
                    self.check(owner, generation)
                    if response.status_code != 200:
                        break
                    snapshot = response.json()
                    if snapshot.get('status') != 'syncing':
                        break
                    await asyncio.sleep(1)
                messages = snapshot.get('data', {}).get('messages', [])[:100]
                read = fetched = missed = 0
                for message in messages:
                    self.check(owner, generation)
                    source_id = str(message.get('id', ''))
                    if not source_id:
                        continue
                    text = message.get('body_text', '')
                    seen = self.read(owner)['seen'].get('mail:' + source_id)
                    if not text and seen:
                        continue
                    if not text:
                        if fetched >= 20:
                            missed += 1; continue
                        fetched += 1
                        detail = await self.context.api('mail', '/message?message_id=' + quote(source_id, safe=''), timeout=10)
                        self.check(owner, generation)
                        if detail.status_code != 200:
                            missed += 1; continue
                        text = detail.json().get('body_text', '')
                    received = str(message.get('received_at') or '')
                    try:
                        received_date = datetime.fromisoformat(received).astimezone(ZONE).date()
                    except ValueError:
                        received_date = None
                    if received_date and not today - timedelta(days=90) <= received_date <= today:
                        continue
                    self.ingest(owner, generation, [{'source': 'mail', 'source_id': source_id,
                        'title': str(message.get('title') or '无主题邮件')[:160], 'text': str(text)[:40000],
                        'source_date': received_date.isoformat() if received_date else '',
                        'url': 'https://mail.shanghaitech.edu.cn/coremail/'}]); read += 1
                partial = missed or sync.status_code not in {200, 202} or snapshot.get('status') not in {'ready', 'success'}
                results['mail'] = {'status': 'partial' if partial else 'ready', 'read': read,
                    'updated_at': snapshot.get('updated_at'),
                    'message': f'最近 {len(messages)} 封缓存，本轮筛查 {read} 封、待补读 {missed} 封。' +
                               ('同步或部分正文暂不可用，已读取可用缓存；请检查邮箱连接。' if partial else '已请求同步；正文读取不标为已读。')}
            except (httpx.HTTPError, ValueError, KeyError) as error:
                results['mail'] = {'status': 'error', 'message': str(error) if isinstance(error, ValueError) else '邮箱读取失败，请检查邮箱模块与连接。'}
        with self.lock:
            self.check(owner, generation); state = self.read(owner)
            state.update(last_checked=datetime.now(ZONE).isoformat(),
                         next_check=(datetime.now(ZONE) + timedelta(seconds=INTERVAL)).isoformat(), sources=results)
            self.save(owner, state)

    def review(self, body, item, before):
        """Called under our shared lock by the condition write; no automatic write path."""
        if not body.discovery_id:
            return None
        owner = self.owner(); state = self.read(owner)
        if body.discovery_account != owner:
            raise HTTPException(409, '邮箱或学校账号已变化，请重新核实线索。')
        lead = next((v for v in state['items'] if v['id'] == body.discovery_id), None)
        if not lead or lead['state'] != 'pending':
            raise HTTPException(409, '该线索已处理，请刷新。')
        if not body.evidence_confirmed:
            raise HTTPException(422, '请先阅读原文并确认行人影响。')
        if lead['action'] == 'reopening' or item.state == 'resolved':
            if not before or before['state'] != 'confirmed' or item.state != 'resolved':
                raise HTTPException(422, '恢复线索须关联一条已确认限制，并核实后确认恢复。')
        elif item.state != 'confirmed':
            raise HTTPException(422, '请核实线索后确认限制或提醒；不适用时忽略该线索。')
        if item.source_kind != ('mail' if lead['source'] == 'mail' else 'official') or item.source_url != lead['source_url']:
            raise HTTPException(422, '请保留自动发现的原文来源；其他依据可另建人工记录。')
        return owner, state, lead

    def reviewed(self, review, condition_id):
        if review:
            owner, state, lead = review
            lead.update(state='reviewed', condition_id=condition_id, reviewed_at=datetime.now(ZONE).isoformat())
            self.save(owner, state)

    def router(self):
        router = APIRouter()

        @router.get('/discovery')
        def status():
            return self.public()

        @router.put('/discovery/settings')
        def settings(body: DiscoverySettings):
            with self.lock:
                owner, state = self.capture(body)
                if not body.official and not body.mail:
                    raise HTTPException(422, '请至少选择一个发现来源。')
                state['settings'] = body.model_dump(include={'enabled', 'official', 'mail'})
                self.generation += 1; self.save(owner, state)
                if body.enabled:
                    self.force_owner = owner
            return self.public()

        @router.post('/discovery/check', status_code=202)
        def check(body: DiscoveryVersion):
            with self.lock:
                owner, _ = self.capture(body)
                if self.running_owner != owner:
                    self.force_owner = owner
            return {'queued': True}

        @router.post('/discovery/{identity}/dismiss')
        def dismiss(identity: str, body: DiscoveryVersion):
            with self.lock:
                owner, state = self.capture(body)
                item = next((v for v in state['items'] if v['id'] == identity), None)
                if not item or item['state'] != 'pending':
                    raise HTTPException(409, '线索已处理或不存在。')
                item.update(state='dismissed', reviewed_at=datetime.now(ZONE).isoformat())
                self.save(owner, state)
            return self.public()

        return router

    async def work(self):
        self.loop, self.task = asyncio.get_running_loop(), asyncio.current_task()
        while not self.stopping.is_set():
            owner = self.owner(); state = self.read(owner)
            due = not state['next_check'] or datetime.fromisoformat(state['next_check']) <= datetime.now(ZONE)
            if self.force_owner == owner or (state['settings']['enabled'] and due):
                self.force_owner = None; self.running_owner = owner; generation = self.generation
                try:
                    await self.scan(owner, generation)
                except HTTPException:
                    pass
                except asyncio.CancelledError:
                    raise
                except Exception:
                    with self.lock:
                        if owner == self.owner() and not self.stopping.is_set():
                            state = self.read(owner)
                            state.update(error='检查未完成，已有线索保留；稍后重试。',
                                         next_check=(datetime.now(ZONE)+timedelta(seconds=INTERVAL)).isoformat())
                            self.save(owner, state)
                finally:
                    self.running_owner = None
            await asyncio.sleep(1)

    def start(self):
        def run():
            try:
                asyncio.run(self.work())
            except asyncio.CancelledError:
                pass
        self.thread = threading.Thread(target=run, name='campus-map-discovery', daemon=True)
        self.thread.start()
        if runtime := getattr(self.context, 'runtime', None):
            runtime.watch('校园通行信息发现', self.thread)

    def close(self):
        self.stopping.set()
        if self.loop and self.task and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.task.cancel)
        if self.thread:
            self.thread.join(10)
            if self.thread.is_alive():
                raise RuntimeError('通行信息检查仍在退出，请稍后重试。')
