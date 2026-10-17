import asyncio
import json
import logging
import secrets
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from anyio import CancelScope

from backend.services.campus.analysis import account_revision
from .models import Answer, Attend, Chat, ConversationUpdate, CourseSearch, Document, Navigate, Profile, Query, Remember, ScheduleEdit, Search
from .conversations import Conversations
from .tools import Task, profile_owner, read_profile
from .workspace import Workspace, WorkCommand, WorkEdit
from .reader import Reader, ReaderSettings, settings as reader_settings, save_settings as save_reader_settings

INSTRUCTION = Path(__file__).with_name('instruction.md').read_text(encoding='utf-8')
PRESETS = json.loads((Path(__file__).parents[1] / 'harness' / 'prompts.json').read_text(encoding='utf-8'))
TOOL_NAMES = {'query': '查询学习资料', 'search': '检索课程原文', 'document': '读取作业或课件页码', 'course-search': '查询教务课程与大纲', 'remember': '更新学习档案', 'navigate': '打开工作台页面', 'attend': '确认参加并加入时间表', 'finish': '核对原文引用'}
TOOL_NAMES.update({'schedule-edit': '编辑时间表', 'capabilities': '查看助手能力', 'work-edit': '管理学习事务'})
_agent = None


class Agent:
    def __init__(self, context):
        self.context, self.lock, self.tasks = context, asyncio.Lock(), {}
        self.conversations = Conversations(context)
        self.work = Workspace(context)
        self.reader = Reader(context)

    def history(self):
        return self.conversations.messages()

    def task(self, request):
        authorization = request.headers.get('authorization', '')
        token = authorization.removeprefix('Bearer ')
        task = self.tasks.get(token) if authorization.startswith('Bearer ') else None
        if task is None:
            raise HTTPException(401, '学习工具需要当前任务的一次性令牌。')
        task.check()
        return task


def authorize_write(context, request):
    if request.method != 'POST' or request.url.path not in {'/api/v1/modules/' + context.id + '/tools/' + name for name in TOOL_NAMES}:
        return False
    try:
        _agent.task(request)
        return True
    except HTTPException:
        return False


def create_router(context):
    global _agent
    agent = _agent = Agent(context)
    router = APIRouter()

    @router.get('/reader/settings')
    def reading_settings():
        return {**reader_settings(context), 'vision': context.ai.vision_settings()}

    @router.put('/reader/settings')
    def update_reading_settings(body: ReaderSettings):
        return save_reader_settings(context, body)

    @router.get('/work')
    def work():
        return agent.work.snapshot()

    @router.post('/work/commands')
    async def work_command(body: WorkCommand):
        return await agent.work.command(body)

    @router.get('/presets')
    def presets():
        return {'items': PRESETS}

    @router.get('/chat')
    def history():
        owner = account_revision(context)
        identity = agent.conversations.index(owner)['active_id']
        messages = agent.conversations.messages(identity, owner) if identity else []
        if owner != account_revision(context):
            raise HTTPException(409, '账号已更新，请重新打开对话。')
        return {'messages': messages, 'conversation_id': identity, 'owner': owner}

    @router.get('/conversations')
    def conversations():
        return agent.conversations.index()

    @router.post('/conversations', status_code=201)
    async def new_conversation():
        # Navigation is synchronous local state; it must not wait for AI shutdown.
        return agent.conversations.create()

    @router.post('/conversations/{identity}/select')
    async def select_conversation(identity: str):
        return agent.conversations.select(identity)

    @router.put('/conversations/{identity}')
    async def update_conversation(identity: str, body: ConversationUpdate):
        async with agent.lock:
            return agent.conversations.update(identity, body.model_dump(exclude_none=True))

    @router.delete('/conversations/{identity}')
    async def delete_conversation(identity: str):
        async with agent.lock:
            agent.conversations.delete(identity)
        return {'deleted': True}

    @router.delete('/chat')
    async def clear_chat():
        async with agent.lock:
            identity = agent.conversations.index()['active_id']
            if identity:
                agent.conversations.delete(identity)
        return {'cleared': True}

    @router.get('/profile')
    def profile():
        value = read_profile(context)
        academic = value['academic']
        return {'profile': value['profile'], 'academic': {key: academic[key] for key in ('plan_title', 'updated_at') if key in academic}}

    @router.put('/profile')
    async def save_profile(body: Profile):
        async with agent.lock:
            if not context.auth.get_status('ids')['identity_verified']:
                raise HTTPException(409, '请先连接 IDS，再保存个人学习档案。')
            context.store.write('profile:' + profile_owner(context), body.model_dump())
        return profile()

    @router.delete('/profile')
    async def clear_profile():
        async with agent.lock:
            owner = profile_owner(context)
            context.store.delete('profile:' + owner)
            context.store.delete('academic:' + owner)
        return profile()

    @router.get('/activity')
    def activity():
        owner = account_revision(context)
        return {'active': any(task.owner == owner for task in agent.tasks.values()), 'steps': [step for task in agent.tasks.values() if task.owner == owner for step in task.activity]}

    async def reply(body, request, emit=None, cancel_event=None):
        if not body.message.strip():
            raise HTTPException(422, '请输入想让学习助手处理的问题。')
        async with agent.lock:
            identity = body.conversation_id or agent.conversations.index()['active_id'] or agent.conversations.create()['id']
            _, conversation = agent.conversations.find(identity)
            if conversation['archived']:
                raise HTTPException(409, '请先恢复这段归档对话，再继续发送消息。')
            task, token = Task(context, body.message, agent.work, agent.reader), secrets.token_urlsafe(32)
            task.cancel_event = cancel_event
            if emit:
                task.emit = emit
            agent.tasks[token] = task
            try:
                task.emit({'type': 'activity', 'steps': []})
                previous = agent.conversations.messages(identity)
                data = {'now': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'profile': read_profile(context)['profile'],
                        'history': [{'role': item['role'], 'text': item['text'][:2500]} for item in previous if item.get('context_version') == 2][-8:]}
                origin = request.url.scheme + '://' + request.url.netloc
                options = {}
                if emit:
                    loop = asyncio.get_running_loop()

                    def on_event(frame):
                        task.check()
                        if frame['type'] == 'start':
                            loop.call_soon_threadsafe(emit, {'type': 'reset'})
                        elif task.answer is not None and frame['type'] == 'chunk' and frame['chunk']['type'] == 'text-delta':
                            loop.call_soon_threadsafe(emit, {'type': 'delta', 'text': frame['chunk']['text']})

                    options = {'on_event': on_event, 'cancel_event': cancel_event}
                result = await run_in_threadpool(context.ai.run, prompt=INSTRUCTION + '\n用户本次请求：\n' + body.message,
                                                context=json.dumps(data, ensure_ascii=False), plugins=[context.id],
                                                plugin_env={'CAMPUS_PLUGIN_STUDY_URL': origin + '/api/v1/modules/' + context.id, 'CAMPUS_PLUGIN_STUDY_TOKEN': token}, **options)
                task.check()
                if cancel_event is not None and cancel_event.is_set():
                    raise HTTPException(409, '本次回答已停止。')
                if task.answer is None:
                    raise HTTPException(502, '学习助手尚未完成回答与原文核对，请重试。')
                # The final assistant message is the body already shown by streaming.
                # A legacy finish.text summary must not replace it when completion arrives.
                text = result['content'] or task.answer['text'] or ''
                if not text.strip() or len(text) > 24000:
                    raise HTTPException(502, '回答内容不完整，请重试。')
                created = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
                answer = {'role': 'assistant', **task.answer, 'text': text, 'conversation_id': identity,
                         'navigation': task.navigation, 'changes': task.changes, 'tools': result['tools'], 'created_at': created, 'model': result['model'], 'context_version': 2}
                pair = [{'role': 'user', 'text': body.message, 'created_at': created, 'context_version': 2}, answer]
                task.check()
                agent.conversations.append(identity, pair, task.owner)
                return answer
            except Exception:
                if task.changes:
                    task.check()
                    created = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
                    answer = {'role': 'assistant', 'text': '以下本地修改已保存。文字回答未完成，请查看操作回执；无需重复执行已完成的修改。',
                              'changes': task.changes, 'citations': [], 'created_at': created, 'conversation_id': identity, 'context_version': 2}
                    agent.conversations.append(identity, [{'role': 'user', 'text': body.message, 'created_at': created, 'context_version': 2}, answer], task.owner)
                    return answer
                raise
            finally:
                task.finished = True
                agent.tasks.pop(token, None)

    @router.post('/chat')
    async def chat(body: Chat, request: Request):
        return await reply(body, request)

    @router.post('/chat/stream')
    async def stream(body: Chat, request: Request):
        if not body.message.strip():
            raise HTTPException(422, '请输入想让学习助手处理的问题。')
        queue, cancelled = asyncio.Queue(), threading.Event()

        async def work():
            with CancelScope(shield=True):
                try:
                    answer = await reply(body, request, queue.put_nowait, cancelled)
                    queue.put_nowait({'type': 'complete', 'message': answer})
                except HTTPException as error:
                    queue.put_nowait({'type': 'error', 'status': error.status_code, 'detail': error.detail})
                except Exception as error:
                    logging.getLogger(__name__).error('Study chat failed: %s', type(error).__name__)
                    queue.put_nowait({'type': 'error', 'status': 502, 'detail': '学习助手暂时无法完成回答，请稍后重试。'})
                finally:
                    queue.put_nowait(None)

        async def events():
            worker = asyncio.create_task(work())
            try:
                while (event := await queue.get()) is not None:
                    yield json.dumps(event, ensure_ascii=False) + '\n'
            finally:
                cancelled.set()
                with CancelScope(shield=True):
                    await worker

        return StreamingResponse(events(), media_type='application/x-ndjson', headers={'X-Accel-Buffering': 'no'})

    async def perform(name, body, request):
        task = agent.task(request)
        if name != 'finish' and len(task.activity) >= 24:
            raise HTTPException(429, '本次工具调用已达 24 次，请先根据已读资料回答或缩小范围。')
        step = {'name': name, 'label': TOOL_NAMES[name], 'status': 'running'}
        task.answer = None
        task.activity.append(step)
        task.emit({'type': 'activity', 'steps': [dict(item) for item in task.activity]})
        try:
            result = await getattr(task, name.replace('-', '_'))(body)
            task.check()
            step['status'] = 'done'
            task.emit({'type': 'activity', 'steps': [dict(item) for item in task.activity]})
            return result
        except Exception:
            step['status'] = 'error'
            task.emit({'type': 'activity', 'steps': [dict(item) for item in task.activity]})
            raise

    @router.post('/tools/query')
    async def query(body: Query, request: Request):
        return await perform('query', body, request)

    @router.post('/tools/search')
    async def search(body: Search, request: Request):
        return await perform('search', body, request)

    @router.post('/tools/document')
    async def document(body: Document, request: Request):
        return await perform('document', body, request)

    @router.post('/tools/course-search')
    async def course_search(body: CourseSearch, request: Request):
        return await perform('course-search', body, request)

    @router.post('/tools/remember')
    async def remember(body: Remember, request: Request):
        return await perform('remember', body, request)

    @router.post('/tools/navigate')
    async def navigate(body: Navigate, request: Request):
        return await perform('navigate', body, request)

    @router.post('/tools/finish')
    async def finish(body: Answer, request: Request):
        return await perform('finish', body, request)

    @router.post('/tools/attend')
    async def attend(body: Attend, request: Request):
        return await perform('attend', body, request)

    @router.post('/tools/schedule-edit')
    async def schedule_edit(body: ScheduleEdit, request: Request):
        return await perform('schedule-edit', body, request)

    @router.post('/tools/capabilities')
    async def capabilities(request: Request):
        return await perform('capabilities', None, request)

    @router.post('/tools/work-edit')
    async def work_edit(body: WorkEdit, request: Request):
        return await perform('work-edit', body, request)

    return router


def start(context):
    _agent.reader.stopped.clear()
    _agent.work.start()


def stop(context):
    if _agent is not None:
        _agent.reader.stopped.set()
        for task in _agent.tasks.values():
            task.finished = True
        if not _agent.reader.lock.acquire(timeout=5):
            raise RuntimeError('资料读取任务仍在停止，请稍后重试。')
        _agent.reader.lock.release()
        _agent.work.close()
        _agent.tasks.clear()
