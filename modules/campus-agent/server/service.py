import asyncio
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from backend.services.campus.analysis import account_revision
from backend.services.campus.data import digest

INSTRUCTION = Path(__file__).with_name('instruction.md').read_text(encoding='utf-8')
ZONE = ZoneInfo('Asia/Shanghai')


class Event(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    event_type: str = Field(pattern='^(activity|lecture|quiz|presentation)$')
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    location: str = Field(default='', max_length=200)
    quote: str = Field(min_length=4, max_length=1000)

    @model_validator(mode='after')
    def interval(self):
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError('结束时间须晚于开始时间。')
        return self


def normalized(text):
    return re.sub(r'\s+', '', text)


def source_content(value):
    if isinstance(value, list):
        return [source_content(item) for item in value]
    if isinstance(value, dict):
        ignored = {'updated_at', 'checked_at', 'generated_at', 'source_metadata'}
        if str(value.get('id', '')).startswith('mail:'):
            ignored |= {'body_text', 'body_html'}
        return {key: source_content(item) for key, item in value.items() if key not in ignored}
    return value


def review_key(value):
    return digest([value.get(key) for key in ('fingerprint', 'bucket', 'category', 'needs_check', 'event', 'by')])


def grounded(event, text, received_at=None):
    if normalized(event.quote) not in normalized(text):
        raise HTTPException(422, '活动依据必须来自本次读取的原文。')
    dated = re.sub(r'(?<=\d)\s+(?=[年月日:：/.-]|\d)|(?<=[年月日:：/.-])\s+(?=\d)', '', event.quote)
    quote = '\n'.join(part for part in re.split(r'[。；;\n]', dated)
                      if not re.search(r'报名|问卷|调查|反馈|申请|提交|截止|deadline|survey|registration', part, re.I))
    start = event.starts_at.astimezone(ZONE)
    dates = list(re.finditer(r'(?:(20\d{2})[年/.-])?(\d{1,2})[月/.-](\d{1,2})日?', quote))
    received_year = datetime.fromisoformat(received_at).astimezone(ZONE).year if received_at else None
    if not any(int(match[2]) == start.month and int(match[3]) == start.day and int(match[1] or received_year or 0) == start.year for match in dates):
        raise HTTPException(422, '活动日期缺少可核对的原文，请先核对。')
    clocks = [(int(match[1]), int(match[2] or 0)) for match in re.finditer(r'(\d{1,2})[:：点](\d{2})?', quote)]
    if (start.hour, start.minute) not in clocks:
        raise HTTPException(422, '活动开始时间缺少可核对的原文。')
    if event.ends_at and (event.ends_at.astimezone(ZONE).hour, event.ends_at.astimezone(ZONE).minute) not in clocks:
        raise HTTPException(422, '活动结束时间缺少可核对的原文。')
    return event.model_dump(mode='json', exclude={'quote'})


class Job:
    def __init__(self, service, owner, modules, pending):
        self.service, self.owner, self.modules, self.pending = service, owner, modules, set(pending)
        self.references, self.reviewed, self.synced = {}, {}, set()
        self.calls = 0

    def check(self):
        if self.service.cancelled.is_set() or self.owner != account_revision(self.service.context):
            raise HTTPException(409, '检查任务或账号状态已更新。')

    def index(self, module, value):
        if isinstance(value, dict):
            if isinstance(value.get('id'), str) and value.get('title'):
                text = '\n'.join(str(value.get(key) or '') for key in ('title', 'body_text', 'summary', 'starts_at', 'due_at', 'location'))
                self.references[(module, value['id'])] = {**value, 'text': text}
            for child in value.values():
                self.index(module, child)
        elif isinstance(value, list):
            for child in value:
                self.index(module, child)

    def selected_data(self, value):
        if isinstance(value, dict):
            if value.get('source') == 'group-messages':
                return None  # The selected-group workflow already owns extraction and notification.
            if (value.get('source') == 'mail' or str(value.get('id', '')).startswith('mail:')) and value.get('id') not in self.pending:
                return None
            return {key: self.selected_data(child) for key, child in value.items()}
        if isinstance(value, list):
            return [selected for child in value if (selected := self.selected_data(child)) is not None]
        return value

    async def read(self, module, path):
        self.check()
        info = self.modules.get(module)
        if not info:
            raise HTTPException(404, '请选择本次可用的服务。')
        route = urlsplit(path).path
        allowed = any(re.fullmatch(re.sub(r'\{[^}]+\}', '[^/]+', re.escape(candidate).replace(r'\{', '{').replace(r'\}', '}')), route) for candidate in info['reads'])
        if not allowed:
            raise HTTPException(422, '请选择服务目录中列出的只读接口。')
        value = self.selected_data(await self.service.api(module, path))
        self.check()
        self.index(module, value)
        content = json.dumps(value, ensure_ascii=False)
        return value if len(content) <= 22000 else {'text': content[:22000], 'truncated': True, 'hint': '使用课程、日期、关键字或条目标识缩小范围。'}

    async def review_context(self, message_id):
        if message_id not in self.pending:
            raise HTTPException(422, '本轮只复核待处理的邮件。')
        value = await self.service.api('mail', '/review-context?message_id=' + quote(message_id, safe=''))
        self.check()
        self.references[('mail', message_id)] = {'id': message_id, 'title': value['notification']['title'], 'text': '\n'.join(value['notification'].values()), 'received_at': value['received_at']}
        return value

    async def classify(self, value):
        self.check()
        if value['message_id'] not in self.pending:
            raise HTTPException(422, '邮件不属于本轮检查范围。')
        result = await self.service.api('mail', '/review-results', method='POST', body=value)
        self.check()
        self.reviewed[value['message_id']] = result
        return {'saved': True, 'bucket': result['bucket']}

    def reference(self, module, identity, quote):
        self.check()
        found = self.references.get((module, identity))
        if not found or not quote.strip() or normalized(quote) not in normalized(found['text']):
            raise HTTPException(422, '需要引用本次实际读取的资料原文。')
        return found


class CampusAgent:
    def __init__(self, context):
        self.context = context
        self.lock = threading.RLock()
        self.stopping, self.wake, self.cancelled = threading.Event(), threading.Event(), threading.Event()
        self.thread, self.running, self.force, self.retry_at = None, False, False, 0
        self.jobs, self.catalog = {}, {}
        self.origin = None

    def key(self, name):
        return name + ':' + account_revision(self.context)

    async def api(self, module, path='/snapshot', **kwargs):
        response = await self.context.api(module, path, **kwargs)
        if response.status_code >= 400:
            raise HTTPException(response.status_code, response.json().get('detail', '服务暂时不可用。'))
        return response.json()

    def settings(self):
        return self.context.store.read(self.key('settings'), {'enabled': True})

    def set_settings(self, enabled):
        self.context.store.write(self.key('settings'), {'enabled': enabled})
        if not enabled:
            self.cancelled.set()
        self.wake.set()
        return self.settings()

    def status(self):
        value = self.context.store.read(self.key('state'), {})
        return {'available': True, 'owner': account_revision(self.context), **self.settings(), 'running': self.running,
                'last_checked': value.get('last_checked'), 'summary': value.get('summary', '等待资料更新'), 'error': value.get('error'),
                'pending_count': len(value.get('pending', [])), 'last_run': value.get('last_run'), 'proposals': self.proposals()}

    def proposals(self):
        return self.context.store.read(self.key('proposals'), [])

    def request_check(self, origin):
        self.origin, self.force, self.retry_at = origin, True, 0
        self.wake.set()
        return {'queued': True}

    async def notice(self, identity, title, summary, revision, *, owner=None, why='', importance='normal', citations=None, proposal_id=None, event_at=None):
        return await self.api('notifications', '/imports', method='POST', body={'account_revision': owner or account_revision(self.context), 'id': identity, 'title': title[:120], 'summary': summary[:3000],
            'importance': importance, 'why': why[:1000], 'source_revision': revision, 'citations': citations or [], 'proposal_id': proposal_id, 'event_at': event_at})

    async def propose(self, owner, module, source, event):
        event_value = grounded(event, source['text'], source.get('received_at'))
        if event.starts_at <= datetime.now(timezone.utc):
            raise HTTPException(422, '这条活动已经开始，请查看原始资料核对。')
        identity = digest([module, source['id']])
        # shortcut: one dated activity per source item; split multi-session notices when needed.
        with self.lock:
            if owner != account_revision(self.context):
                raise HTTPException(409, '账号已更新。')
            values = self.proposals()
            item = next((item for item in values if item['id'] == identity), None)
            if item is None:
                item = {'id': identity, 'state': 'pending', 'source_id': source['id'], 'module': module, 'event': event_value,
                        'quote': event.quote, 'title': source['title'], 'url': source.get('url', ''), 'source_revision': source.get('classification', {}).get('input_revision'), 'created_at': datetime.now(timezone.utc).isoformat()}
                values.insert(0, item)
                self.context.store.write(self.key('proposals'), values)
            elif item['state'] in {'pending', 'withdrawn'}:
                item.update(state='pending', event=event_value, quote=event.quote, source_revision=source.get('classification', {}).get('input_revision'))
                self.context.store.write(self.key('proposals'), values)
        return item

    def reconcile_proposals(self, owner, messages):
        current = {item['id']: item['classification'] for item in messages}
        with self.lock:
            if owner != account_revision(self.context) or self.cancelled.is_set():
                raise HTTPException(409, '账号或模块状态已更新。')
            values, changed = self.proposals(), False
            for item in values:
                classification = current.get(item['source_id']) if item['module'] == 'mail' else None
                if item['state'] == 'pending' and classification and (classification.get('bucket') not in {'focus', 'recommend'} or classification.get('review_pending')):
                    item['state'] = 'withdrawn'
                    changed = True
            if changed:
                self.context.store.write(self.key('proposals'), values)

    async def decide(self, identity, action):
        with self.lock:
            owner = account_revision(self.context)
            item = next((item for item in self.proposals() if item['id'] == identity), None)
            if item is None:
                raise HTTPException(404, '当前账号没有这条日程建议。')
            if item['state'] == 'withdrawn':
                raise HTTPException(409, '这条建议已随邮件分类更新，请刷新通知。')
            if item['state'] != 'pending':
                return item
            if action == 'accept' and datetime.fromisoformat(item['event']['starts_at']) <= datetime.now(timezone.utc):
                raise HTTPException(409, '活动已经开始，请在时间表中手动核对。')
        result = None
        if action == 'accept':
            if item['module'] == 'mail':
                mail = await self.api('mail', '/intelligence')
                current = next((value['classification'] for value in mail['messages'] if value['id'] == item['source_id']), None)
                if not current or current.get('review_pending') or current['bucket'] not in {'focus', 'recommend'} or item.get('source_revision') != current.get('input_revision'):
                    raise HTTPException(409, '邮件分类或偏好已更新，请等待复核后确认安排。')
            if owner != account_revision(self.context) or self.stopping.is_set():
                raise HTTPException(409, '账号或模块状态已更新。')
            result = await self.api('timetable', '/events/import', method='POST', body={**item['event'], 'origin_id': 'campus-agent:' + identity,
                'account_revision': owner, 'notes': ('来源：' + item['title'] + '\n' + item['quote'])[:2000]})
        with self.lock:
            if owner != account_revision(self.context):
                raise HTTPException(409, '账号已更新。')
            values = self.proposals()
            current = next(value for value in values if value['id'] == identity)
            current.update(state='accepted' if action == 'accept' else 'dismissed', event_id=result['id'] if result else None)
            self.context.store.write(self.key('proposals'), values)
        return current

    async def collect(self):
        modules, snapshots = {}, {}
        infos = self.context.modules()['modules']
        managed_calendar = set()
        if any(info['id'] == 'group-messages' and info['status'] == 'ready' for info in infos):
            group_snapshot = await self.api('group-messages')
            managed_calendar = set(group_snapshot.get('data', {}).get('metadata', {}).get('managed_calendar_ids', []))
        for info in infos:
            if info['status'] != 'ready' or info['id'] in {self.context.id, 'notifications', 'group-messages'}:
                continue
            module = info['id']
            key = (module, info['revision'])
            if key not in self.catalog:
                response = await self.context.api(module, '/openapi.json')
                paths = response.json().get('paths', {}) if response.status_code == 200 else {}
                self.catalog[key] = [path for path, methods in paths.items() if 'get' in methods and not re.search(r'token|secret|/tools/|/agent/|/download|/file', path)]
            modules[module] = {'id': module, 'name': info['name'], 'reads': self.catalog[key]}
            if module == 'mail':
                modules[module]['reads'] = ['/preferences']
            elif module == 'academic-assistant':
                modules[module]['reads'] = ['/profile']
            if '/snapshot' in self.catalog[key]:
                snapshots[module] = await self.api(module)
                if module == 'timetable':
                    events = await self.api(module, '/events')
                    snapshots[module]['data']['events'] = [item for item in events['items'] if not item.get('origin_id', '').startswith('campus-agent:') and item['id'] not in managed_calendar]
        mail = await self.api('mail', '/intelligence') if 'mail' in modules else {'messages': [], 'preferences': {}}
        return modules, snapshots, mail

    async def handle_reviews(self, owner, identities):
        mail = await self.api('mail', '/intelligence')
        current = {item['id']: item for item in mail['messages']}
        handled = {}
        for identity in identities:
            item = current.get(identity)
            if item is None or not item['classification'].get('fingerprint'):
                continue
            review = item['classification']
            prepared = await self.api('mail', '/review-context?message_id=' + quote(identity, safe=''))
            if owner != account_revision(self.context) or self.cancelled.is_set():
                raise HTTPException(409, '账号或模块状态已更新。')
            if prepared['fingerprint'] != review['fingerprint']:
                continue
            source = {**item, 'text': '\n'.join(prepared['notification'].values())}
            proposal = None
            window = review.get('event_window')
            if review.get('event') and review['bucket'] in {'focus', 'recommend'} and not review.get('needs_check'):
                try:
                    event = Event.model_validate(review['event'])
                    # A known past time is not an uncertain time and needs no new invitation.
                    if event.starts_at > datetime.now(timezone.utc):
                        proposal = await self.propose(owner, 'mail', source, event)
                except (HTTPException, ValueError):
                    review = {**review, 'needs_check': True}
            revision = review_key(item['classification'])
            if review['bucket'] in {'focus', 'recommend'} and (proposal is None or proposal['state'] != 'dismissed'):
                notice_revision = digest([prepared['notification'], review['bucket'], review.get('needs_check'), review.get('event')])
                await self.notice('mail:' + digest(identity), item['title'], review['summary'], notice_revision, why=review['reason'] + (' 参加要求仍需核对。' if review.get('needs_check') and window else ' 活动时间需要核对。' if review.get('needs_check') else ' 可选择是否参加并加入时间表。' if proposal and proposal['state'] == 'pending' else ''),
                    owner=owner, importance='important' if review['bucket'] == 'focus' else 'normal', citations=[{'id': identity, 'title': item['title'], 'source': 'mail', 'url': item.get('url', '')}],
                    proposal_id=proposal['id'] if proposal else None, event_at=window['starts_at'] if window else proposal['event']['starts_at'] if proposal else None)
            handled[identity] = revision
        return handled

    async def check(self, force=False):
        owner = account_revision(self.context)
        job = Job(self, owner, {}, [])
        job.check()
        state_key = 'state:' + owner
        state = self.context.store.read(state_key, {})
        modules, snapshots, mail = await self.collect()
        job.check()
        self.reconcile_proposals(owner, mail['messages'])
        observed = {}
        for module, value in snapshots.items():
            if module in {'courses', 'assignments', 'dashboard', 'assistant', 'education'}:
                continue
            data = value.get('data', {})
            if module == 'mail':
                data = [{key: item.get(key) for key in ('id', 'title', 'received_at')} for item in data.get('messages', [])]
            health = value.get('status') if value.get('status') in {'error', 'login_required', 'verification_required'} else 'available'
            observed[module] = digest([health, value.get('message'), source_content(data)])
        mail_seen = {item['id']: item['classification'].get('input_revision') or digest([item['title'], item.get('received_at'), mail['preferences']]) for item in mail['messages']}
        changed = list(dict.fromkeys([*state.get('changes_pending', []), *(module for module, revision in observed.items() if state.get('observed', {}).get(module) != revision)]))
        changed = [module for module in changed if module in snapshots]
        pending = list(dict.fromkeys([*state.get('pending', []), *(item['id'] for item in mail['messages'] if item['classification'].get('review_pending', not item['classification'].get('fingerprint')))]))
        if not state and not force:
            changed = []
        elif force:
            pending = list(dict.fromkeys([*(item['id'] for item in mail['messages'][:3]), *pending]))
        manual = {item['id'] for item in mail['messages'] if item['classification'].get('by') == 'manual'}
        pending = [identity for identity in pending if identity in mail_seen and identity not in manual]
        state.update(observed=observed, mail_seen=mail_seen, pending=pending, changes_pending=changed, last_checked=datetime.now(timezone.utc).isoformat())
        job.check()
        self.context.store.write(state_key, state)
        for module in changed:
            value = snapshots[module]
            if value.get('status') in {'error', 'login_required', 'verification_required'}:
                await self.notice('service:' + module, modules[module]['name'] + '需要检查', value.get('message') or '请到设置检查连接，再重新同步。',
                                  digest([module, value.get('status'), value.get('message')]), owner=owner, importance='important')
                job.check()
            elif value.get('status') in {'ready', 'partial'}:
                notices = await self.api('notifications')
                job.check()
                if any(item['id'] == 'service:' + module for item in notices['items']):
                    await self.notice('service:' + module, modules[module]['name'] + '已恢复', '服务已重新同步，可继续查看资料。',
                                      digest([module, 'recovered']), owner=owner)
                    job.check()
        ready = [item['id'] for item in mail['messages'] if item['classification'].get('fingerprint') and state.get('review_seen', {}).get(item['id']) != review_key(item['classification'])][:4]
        handled = await self.handle_reviews(owner, ready) if ready else {}
        job.check()
        state['review_seen'] = {**state.get('review_seen', {}), **handled}
        cached = {item['id'] for item in mail['messages'] if item['classification'].get('fingerprint') and state['review_seen'].get(item['id']) == review_key(item['classification'])}
        cached_count = len(set(pending) & cached)
        pending = [identity for identity in pending if identity not in cached]
        if not pending and snapshots.get('mail', {}).get('status') not in {'error', 'login_required', 'verification_required'}:
            changed = [module for module in changed if module != 'mail']
        state.update(pending=pending, changes_pending=changed)
        self.context.store.write(state_key, state)
        ai = self.context.ai.settings()
        if not ai['enabled']:
            state.update(summary='资料已检查；配置 AI 后可进行综合整理。', error=None)
        elif not self.origin:
            state.update(summary='资料状态已检查，等待学习服务就绪。', error=None)
        elif not pending and not changed and not force:
            state.update(summary=f'已整理 {len(handled)} 封邮件的分类结果。' if handled else '服务与资料状态已检查，暂无新事项。', error=None)
        else:
            selected = pending[:max(0, 4 - len(handled))]
            job.modules, job.pending = modules, set(selected)
            token = secrets.token_urlsafe(32)
            self.jobs[token] = job
            try:
                payload = {'now': datetime.now(ZONE).isoformat(), 'services': list(modules.values()), 'changed': changed,
                           'states': {name: {'status': value.get('status'), 'issues': value.get('data', {}).get('issues', []), 'message': value.get('message')} for name, value in snapshots.items()},
                           'pending_mail': selected, 'preferences': mail['preferences']}
                def run():
                    # The account may change while this call waits for a worker thread.
                    job.check()
                    return self.context.ai.run(prompt=INSTRUCTION, context=json.dumps(payload, ensure_ascii=False), plugins=[self.context.id],
                        cancel_event=self.cancelled, plugin_env={'CAMPUS_PLUGIN_AGENT_URL': self.origin, 'CAMPUS_PLUGIN_AGENT_TOKEN': token})
                result = await asyncio.to_thread(run)
                job.check()
                handled.update(await self.handle_reviews(owner, job.reviewed) if job.reviewed else {})
                job.check()
                state['review_seen'].update(handled)
                state['last_run'] = {'completed_at': datetime.now(timezone.utc).isoformat(), 'mail_count': len(selected) + cached_count,
                                     'reviewed': len(job.reviewed), 'cached': cached_count, 'tool_calls': len(result['tools'])}
                state.update(pending=[identity for identity in pending if identity not in handled], changes_pending=[], summary=f'已复核 {len(handled)} 封邮件，并检查更新的服务资料。', error=None)
            finally:
                self.jobs.pop(token, None)
        job.check()
        self.context.store.write(state_key, state)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name='campus-agent', daemon=True)
        self.thread.start()
        if getattr(self.context, 'runtime', None):
            self.context.runtime.watch('资料变化检查', self.thread)

    def loop(self):
        while not self.stopping.is_set():
            self.wake.wait(25)
            self.wake.clear()
            if self.stopping.is_set():
                return
            if not self.settings()['enabled'] or time.monotonic() < self.retry_at:
                continue
            self.cancelled.clear()
            self.running = True
            owner = account_revision(self.context)
            force, self.force = self.force, False
            try:
                asyncio.run(self.check(force))
            except Exception as error:
                if not self.cancelled.is_set() and owner == account_revision(self.context):
                    message = str(error.detail) if isinstance(error, HTTPException) else '后台检查未完成（' + type(error).__name__ + '），稍后重试。'
                    state_key = 'state:' + owner
                    state = self.context.store.read(state_key, {})
                    state.update(error=message, summary='已保留现有资料与安排。')
                    self.context.store.write(state_key, state)
                    self.retry_at = time.monotonic() + 120
            finally:
                self.running = False

    def close(self):
        self.stopping.set(); self.cancelled.set(); self.wake.set()
        if self.thread:
            self.thread.join()
