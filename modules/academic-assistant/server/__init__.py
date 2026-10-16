import asyncio
import json
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from backend.services.campus.analysis import account_revision
from .models import Answer, Chat, CourseSearch, Document, Navigate, Profile, Query, Remember, Search
from .tools import Task, profile_owner, read_profile

INSTRUCTION = Path(__file__).with_name('instruction.md').read_text(encoding='utf-8')
PRESETS = json.loads((Path(__file__).parents[1] / 'harness' / 'prompts.json').read_text(encoding='utf-8'))
TOOL_NAMES = {'query': '查询学习资料', 'search': '检索课程原文', 'document': '读取作业或课件页码', 'course-search': '查询教务课程与大纲', 'remember': '更新学习档案', 'navigate': '打开工作台页面', 'finish': '核对回答与原文引用'}
_agent = None


class Agent:
    def __init__(self, context):
        self.context, self.lock, self.tasks = context, asyncio.Lock(), {}

    def history(self):
        return self.context.store.read('chat:' + account_revision(self.context), [])

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

    @router.get('/presets')
    def presets():
        return {'items': PRESETS}

    @router.get('/chat')
    def history():
        return {'messages': agent.history()}

    @router.delete('/chat')
    async def clear_chat():
        async with agent.lock:
            context.store.delete('chat:' + account_revision(context))
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

    @router.post('/chat')
    async def chat(body: Chat, request: Request):
        if not body.message.strip():
            raise HTTPException(422, '请输入想让学习助手处理的问题。')
        async with agent.lock:
            task, token = Task(context, body.message), secrets.token_urlsafe(32)
            agent.tasks[token] = task
            try:
                previous = agent.history()
                data = {'now': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'profile': read_profile(context)['profile'],
                        'history': [{'role': item['role'], 'text': item['text'][:2500]} for item in previous if item.get('context_version') == 2][-8:]}
                origin = request.url.scheme + '://' + request.url.netloc
                result = await run_in_threadpool(context.ai.run, prompt=INSTRUCTION + '\n用户本次请求：\n' + body.message,
                                                context=json.dumps(data, ensure_ascii=False), plugins=[context.id],
                                                plugin_env={'CAMPUS_PLUGIN_STUDY_URL': origin + '/api/v1/modules/' + context.id, 'CAMPUS_PLUGIN_STUDY_TOKEN': token})
                task.check()
                if task.answer is None:
                    raise HTTPException(502, '学习助手尚未完成回答与原文核对，请重试。')
                created = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
                reply = {'role': 'assistant', **task.answer,
                         'navigation': task.navigation, 'tools': result['tools'], 'created_at': created, 'model': result['model'], 'context_version': 2}
                pair = [{'role': 'user', 'text': body.message, 'created_at': created, 'context_version': 2}, reply]
                task.check()
                context.store.write('chat:' + task.owner, (previous + pair)[-60:])
                return reply
            finally:
                agent.tasks.pop(token, None)

    async def perform(name, body, request):
        task = agent.task(request)
        if name != 'finish' and len(task.activity) >= 24:
            raise HTTPException(429, '本次工具调用已达 24 次，请先根据已读资料回答或缩小范围。')
        step = {'name': name, 'label': TOOL_NAMES[name], 'status': 'running'}
        task.activity.append(step)
        try:
            result = await getattr(task, name.replace('-', '_'))(body)
            task.check()
            step['status'] = 'done'
            return result
        except Exception:
            step['status'] = 'error'
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

    return router


def stop(context):
    if _agent is not None:
        _agent.tasks.clear()
