from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import Field
from .models import Decision, ExtractRequest, QQConnection, Selection, Strict, WechatConnection
from .service import Service
from . import wechat

_service = None
SourceName = Literal['wechat', 'qq']


class SnapshotConnection(Strict):
    path: str = Field(min_length=1, max_length=2000)


def create_router(context):
    global _service
    service = _service = Service(context)
    router = APIRouter()

    # Setup and raw-message routes are intentionally absent from the AI-readable catalog.
    @router.get('/status', include_in_schema=False)
    def status():
        return service.status()

    @router.get('/wechat/discovery', include_in_schema=False)
    def discover():
        return wechat.discovery()

    @router.post('/wechat/connect')
    def connect_wechat(body: WechatConnection):
        return service.queue('connect', 'wechat', body)

    @router.post('/wechat/snapshot')
    def connect_snapshot(body: SnapshotConnection):
        return service.queue('snapshot', 'wechat', body)

    @router.post('/qq/connect')
    def connect_qq(body: QQConnection):
        return service.queue('connect', 'qq', body)

    @router.put('/sources/{source}')
    async def select(source: SourceName, body: Selection):
        return await service.select(source, body)

    @router.post('/sources/{source}/pause')
    def pause(source: SourceName):
        return service.pause(source)

    @router.post('/sources/{source}/sync')
    def sync(source: SourceName):
        return service.queue('sync', source)

    @router.post('/wechat/compatibility')
    def compatibility():
        return service.queue('compatibility', 'wechat')

    @router.delete('/sources/{source}')
    def forget(source: SourceName):
        return service.forget(source)

    @router.post('/extract')
    def extract(body: ExtractRequest):
        return service.queue('extract', body.source, body)

    @router.post('/stop')
    def stop_current():
        return service.stop_current()

    @router.get('/courses', include_in_schema=False)
    async def courses():
        return await service.course_options()

    @router.get('/messages', include_in_schema=False)
    async def messages(source: SourceName, group_id: str = Query(min_length=1, max_length=200), offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
        owner = service.owner()
        await service.refresh_course_scope(owner)
        with service.lock:
            service.check(owner)
            config, _group = service.selected_group(owner, source, group_id)
            return service.messages.rows(owner, source, config['connection'], group_id, limit=limit, offset=offset)

    @router.get('/senders', include_in_schema=False)
    async def senders(source: SourceName, group_id: str = Query(min_length=1, max_length=200)):
        owner = service.owner()
        await service.refresh_course_scope(owner)
        with service.lock:
            service.check(owner)
            config, _group = service.selected_group(owner, source, group_id)
            rows = service.messages.rows(owner, source, config['connection'], group_id, limit=20000)['items']
            values = {row['sender_id']: {'id': row['sender_id'], 'name': row['sender_name']} for row in reversed(rows) if row['sender_id']}
            return {'items': list(values.values())}

    @router.get('/items', include_in_schema=False)
    def items():
        return service.items()

    @router.post('/items/{item_id}/decision')
    async def decide(item_id: str, body: Decision):
        owner = service.owner()
        with service.lock:
            item = service.current_item(owner, item_id)
            if item['revision'] != body.expected_revision:
                raise HTTPException(409, '事项已更新，请刷新后核对。')
        if body.action == 'apply':
            result = await service.effects.apply(owner, item_id, body.expected_revision)
        elif body.action == 'undo':
            result = await service.effects.undo(owner, item_id, body.expected_revision)
        else:
            with service.lock:
                service.check(owner)
                item = service.current_item(owner, item_id)
                if item['revision'] != body.expected_revision:
                    raise HTTPException(409, '事项已更新，请刷新后核对。')
                item.update(status='accepted' if body.action == 'accept' else 'dismissed', revision=uuid4().hex, automatic_ready=False)
                service.save_item(owner, item)
                result = item
        try:
            await service.effects.publish(owner, result)
        except HTTPException:
            pass  # The worker retries independently; the local decision remains durable.
        return service.current_item(owner, item_id)

    @router.get('/snapshot')
    def snapshot():
        """Only confirmed findings; no client connection details or raw chat history."""
        data = {key: [] for key in ('courses', 'assignments', 'materials', 'announcements', 'posts', 'lessons', 'timetable', 'messages')}
        scope = service.items()
        all_items = scope['items']
        for item in all_items:
            if item['status'] not in {'accepted', 'applied'} or item['action'] in {'question', 'uncertain', 'cancel'}:
                continue
            course = item.get('course', {})
            if not course.get('course_ids'):
                continue
            data['announcements'].append({'id': item['id'], 'source': 'group-messages', 'course_id': course['course_ids'][0],
                'title': item['title'], 'body_text': item['summary'] + '\n原文依据：\n' + '\n'.join(ref['quote'] for ref in item['citations']),
                'url': '#group-messages', 'updated_at': item['updated_at'], 'term': course.get('term', ''), 'managed_notification': True})
        data.update(metadata={'managed_notifications': True, 'scope': '用户确认或按可信规则应用的课程群事项',
                              'managed_calendar_ids': [item['target']['id'] for item in service.all_items(scope['account_revision']).values() if (item.get('target') or {}).get('module') == 'timetable']}, issues=[])
        return {'status': 'ready', 'data': data, 'updated_at': max((item['updated_at'] for item in data['announcements']), default=None)}

    @router.get('/facts/{item_id}')
    def fact(item_id: str):
        item = service.current_item(service.owner(), item_id)
        if item['status'] not in {'accepted', 'applied'}:
            raise HTTPException(404, '这条群消息尚未确认。')
        return {key: item[key] for key in ('id', 'title', 'summary', 'kind', 'action', 'date', 'due_at', 'starts_at', 'ends_at', 'location', 'course')}

    return router


def start(context):
    _service.start()


def stop(context):
    if _service:
        _service.close()
