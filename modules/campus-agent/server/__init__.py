from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.campus.analysis import account_revision
from backend.services.campus.data import digest
from .service import CampusAgent, Event

_service = None


class Settings(BaseModel):
    enabled: bool


class Read(BaseModel):
    module_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')
    path: str = Field(min_length=1, max_length=2000)


class Mail(BaseModel):
    message_id: str = Field(min_length=1, max_length=300)


class Classification(Mail):
    fingerprint: str = Field(min_length=1, max_length=100)
    decision: dict


class Reference(BaseModel):
    module_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')
    source_id: str = Field(min_length=1, max_length=300)


class Proposal(Reference):
    event: Event


class Notice(Reference):
    quote: str = Field(min_length=2, max_length=1000)
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=3000)
    importance: str = Field(default='normal', pattern='^(normal|important|urgent)$')


class Sync(BaseModel):
    module_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')


def job(request, count=True):
    header = request.headers.get('authorization', '')
    value = _service.jobs.get(header.removeprefix('Bearer ')) if header.startswith('Bearer ') else None
    if value is None:
        raise HTTPException(401, '工具需要当前检查任务的一次性令牌。')
    value.check()
    if count:
        value.calls += 1
        if value.calls > 24:
            raise HTTPException(429, '本轮已完成 24 次工具调用，请先结束检查。')
    return value


def authorize_write(context, request):
    if request.method != 'POST' or request.url.path not in {'/api/v1/modules/campus-agent/tools/' + name for name in ('read', 'mail', 'classify', 'propose', 'notice', 'sync')}:
        return False
    try:
        job(request, count=False)
        return True
    except HTTPException:
        return False


def create_router(context):
    global _service
    service = _service = CampusAgent(context)
    router = APIRouter()

    def origin(request):
        service.origin = request.url.scheme + '://' + request.url.netloc + '/api/v1/modules/campus-agent'

    @router.get('/status')
    async def status(request: Request):
        # Only a browser request supplies the application's loopback address.
        if request.url.hostname in {'127.0.0.1', 'localhost', '[::1]', '::1'}:
            origin(request)
        value = service.status()
        response = await context.api('notifications', '/snapshot')
        value['notices'] = response.json().get('items', []) if response.status_code == 200 else []
        return value

    @router.put('/settings')
    def settings(body: Settings):
        return service.set_settings(body.enabled)

    @router.post('/check', status_code=202)
    def check(request: Request):
        if request.url.hostname in {'127.0.0.1', 'localhost', '::1'}:
            origin(request)
        if not service.settings()['enabled']:
            raise HTTPException(409, '请先开启后台助手。')
        service.force = True; service.retry_at = 0; service.wake.set()
        return {'queued': True}

    @router.get('/proposals')
    def proposals():
        return {'items': service.proposals()}

    @router.post('/proposals/{identity}/accept')
    async def accept(identity: str):
        return await service.decide(identity, 'accept')

    @router.post('/proposals/{identity}/dismiss')
    async def dismiss(identity: str):
        return await service.decide(identity, 'dismiss')

    @router.post('/tools/read')
    async def read(body: Read, request: Request):
        return await job(request).read(body.module_id, body.path)

    @router.post('/tools/mail')
    async def mail(body: Mail, request: Request):
        return await job(request).review_context(body.message_id)

    @router.post('/tools/classify')
    async def classify(body: Classification, request: Request):
        return await job(request).classify(body.model_dump())

    @router.post('/tools/propose')
    async def propose(body: Proposal, request: Request):
        task = job(request)
        source = task.reference(body.module_id, body.source_id, body.event.quote)
        if str(source['id']).startswith('mail:'):
            raise HTTPException(422, '邮件活动请放在 campus_classify 的 event 中，由程序生成通知和安排建议。')
        value = await service.propose(task.owner, body.module_id, source, body.event)
        await service.notice('proposal:' + value['id'], body.event.title, '发现一项与你有关的安排。确认参加后可加入时间表。', digest(value['event']), owner=task.owner,
            citations=[{'id': body.source_id, 'title': source['title'], 'source': body.module_id, 'url': source.get('url', '')}], proposal_id=value['id'], event_at=body.event.starts_at.isoformat())
        return value

    @router.post('/tools/notice')
    async def notice(body: Notice, request: Request):
        task = job(request)
        source = task.reference(body.module_id, body.source_id, body.quote)
        if str(source['id']).startswith('mail:'):
            raise HTTPException(422, '邮件通知根据 campus_classify 的结果生成，请直接提交分类。')
        return await service.notice('source:' + digest([body.module_id, body.source_id]), body.title, body.summary, digest(source['text']), owner=task.owner,
            why=body.quote, importance=body.importance, citations=[{'id': body.source_id, 'title': source['title'], 'source': body.module_id, 'url': source.get('url', '')}])

    @router.post('/tools/sync')
    async def sync(body: Sync, request: Request):
        task = job(request)
        if body.module_id not in task.modules or body.module_id in task.synced:
            raise HTTPException(409, '每轮只能为可用服务重试一次同步。')
        task.synced.add(body.module_id)
        state = await service.api(body.module_id)
        if state.get('status') != 'error':
            raise HTTPException(409, '只为同步失败的服务重试；账号验证请在设置中完成。')
        return await service.api(body.module_id, '/sync', method='POST')

    return router


def start(context):
    _service.start()


def stop(context):
    if _service is not None:
        _service.close()
