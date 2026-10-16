"""Offline integration check for the QJQ/WYT contribution; synthetic data only."""
import asyncio
import json
import sys
import tempfile
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import httpx

from backend.core.store import Store  # noqa: E402 -- allow direct script execution
from backend.main import create_app  # noqa: E402
from backend.services.auth import LoginRequired  # noqa: E402


class MemoryVault:
    def transaction(self):
        from contextlib import nullcontext
        return nullcontext()
    def __init__(self):
        self.values = {}

    def get(self, key):
        return deepcopy(self.values.get(key, {}))

    def save(self, key, value):
        self.values[key] = deepcopy(value)

    def delete(self, key):
        self.values.pop(key, None)


class Sources:
    def __init__(self):
        self.fail_post = False
        self.fail_voice = False
        self.blocked = False
        self.calls = []
        self.ai_calls = 0
        self.forge_quote = False

    def handle(self, request):
        self.calls.append((request.url.host, request.url.path))
        path = request.url.path
        if path.endswith('/semester/manage/current'):
            value = {"data": {"currentSemester": {"showSemester": "2026-fall"}, "semesterDataList": [{"showSemester": "2026-fall", "name": "2026年秋季"}, {"showSemester": "2025-fall", "name": "2025年秋季"}]}}
        elif path.endswith('/participated/courses/list'):
            value = {"data": {"results": [{"entityData": {"contentId_": cid, "courseNumber": "DEMO101", "name_": "合成电场课程", "semester_show_name": term}} for cid, term in [("demo-course", "2026年秋季"), ("old-course", "2025年秋季")]]}}
        elif path.endswith('/course/get/course/details'):
            value = {"data": {"contentId": request.url.params['contentId'], "courseId": "recording", "entityData": {"course_semester_id": 1}}}
        elif path.endswith('/homepage/chapter/info'):
            value = {"data": []}
        elif path.endswith('/course/video/review/1'):
            value = {"data": {"results": [{"id": 7, "courseId": "recording", "showSemester": "2026-fall"}]}}
        elif path.endswith('/course/recording/video/info'):
            value = {"data": {"courseId": "recording", "recordingVideoInfoShows": [{"week": "1", "recordInfoDetailList": [{"weekDate": "2026-10-12", "section": "1-2", "videoInfoList": [{"videoId": "teacher", "videoName": "教师全景", "scheduleId": "lesson"}]}]}]}}
        elif path.endswith('/smart/voice/select'):
            if self.fail_voice:
                return httpx.Response(200, json={"success": False})
            value = {"data": {"data": [{"type": "model_sobey_smart_voice_", "metadata": [{"_in": 300000000 + i * 10000000, "_out": 310000000 + i * 10000000, "text": f"电场是矢量，应按矢量叠加。第 {i} 段"} for i in range(105)]}]}}
        elif path.endswith('/knowledge/summary'):
            value = {"data": [{"chapterTitle": "电场叠加", "chapterContent": "学校 AI 摘要：合成教学资料。", "inPoint": 300000000, "outPoint": 500000000}]}
        elif path == '/logic/api':
            payload = json.loads(request.content)
            assert payload['method'] in {'network.get_my_feed', 'content.get'}
            if payload['method'] == 'network.get_my_feed':
                value = {"result": {"feed": [{"id": "post1"}, {"id": "post2"}]}}
            elif self.fail_post and payload['params']['cid'] == 'post2':
                value = {"error": "synthetic upstream error; do not echo"}
            else:
                value = {"result": {"id": payload['params']['cid'], "nr": 1, "created": "2026-10-15T08:00:00Z", "history": [{"subject": "作业 Deadline", "content": '<p>Please submit by Friday.</p><img src="https://piazza.com/uploads/example.png"><a href="javascript:alert(1).pdf">unsafe</a><script>hidden script</script>'}], "children": [{"subject": "补充回复：需要核对原文。"}]}}
        else:
            raise AssertionError(str(request.url))
        return httpx.Response(200, json=value)

    @contextmanager
    def authenticated_client(self, provider, target=None):
        assert (provider, target) in {('ids', 'elrc'), ('piazza', None)}
        if self.blocked:
            raise LoginRequired('合成登录已失效。')
        with httpx.Client(transport=httpx.MockTransport(self.handle)) as client:
            yield client

    def chat(self, messages, format):
        self.ai_calls += 1
        assert format == 'json'
        body = json.loads(messages[1]['content'])
        source = body['sources'][0]
        return {"model": "synthetic", "content": {"mode": body['mode'], "answer": "这是一份用于集成检查的合成回答。", "citations": [{"source_id": source['source_id'], "quote": "伪造引文" if self.forge_quote else source['text'][:10]}], "uncertainty": [], "next_steps": []}}

    def run(self, prompt, context, plugins):
        assert plugins == ['deadlines']
        source = next(item for item in json.loads(context)['items'] if item['kind'] == 'lessons')
        answer = {'text': '已根据所选课程资料整理。', 'insufficient_context': False, 'citation_ids': [source['id']], 'labels': []}
        return {'model': 'synthetic', 'content': json.dumps(answer), 'tools': [{'id': 'synthetic-call', 'name': 'order_deadlines', 'is_error': False}]}


def app_fixture(data):
    data.mkdir(parents=True, exist_ok=True)
    app = create_app(active_port=17667, store=Store(data / 'settings.sqlite3'), vault=MemoryVault(), modules_root=ROOT / 'modules', data_dir=data)
    fixture = Sources()
    app.state.auth.authenticated_client = fixture.authenticated_client
    app.state.auth.browser = SimpleNamespace(close_all=lambda: None)
    app.state.ai.chat = fixture.chat
    app.state.ai.run = fixture.run
    return app, fixture


async def seed(client):
    initial = (await client.get('/api/v1/bootstrap')).json()
    owned = [item for item in initial['modules'] if item['id'] in {'elrc', 'education', 'piazza'}]
    assert len(owned) == 3 and all(item['status'] == 'ready' for item in owned), initial
    client.headers['X-Framework-Token'] = initial['csrf_token']
    assert (await client.post('/api/v1/modules/elrc/discover', json={})).status_code == 200
    response = await client.post('/api/v1/modules/elrc/courses/demo-course/sync', json={})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'ready'
    await client.put('/api/v1/modules/piazza/courses', json={'courses': [{'id': 'demo-network', 'name': '合成课程 Piazza'}]})
    assert (await client.post('/api/v1/modules/piazza/courses/demo-network/sync', json={})).status_code == 200


async def check(data):
    app, fixture = app_fixture(data)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17667') as client:
            # GET operations must stay offline, and writes retain the host's CSRF protection.
            assert (await client.get('/api/v1/modules/elrc/catalog')).json()['courses'] == []
            assert not fixture.calls
            assert (await client.post('/api/v1/modules/elrc/discover', json={})).status_code == 403
            await seed(client)
            catalog = (await client.get('/api/v1/modules/elrc/catalog')).json()
            assert len(catalog['courses']) == 1 and catalog['courses'][0]['transcript_count'] == 1
            lesson = (await client.get('/api/v1/modules/elrc/courses/demo-course/lessons/7-lesson?offset=100')).json()
            assert lesson['total'] == 105 and len(lesson['transcript']) == 5
            assert lesson['summary'][0]['start_seconds'] == 30
            calls_before = len(fixture.calls)
            shared = (await client.get('/api/v1/modules/courses/snapshot')).json()
            assert shared['data']['metadata']['current_semester'] == '2026-fall'
            assert len(shared['data']['lessons']) == 1
            assert '电场是矢量' in shared['data']['lessons'][0]['body_text']
            assert len(shared['data']['posts']) == 2
            assert (await client.get('/api/v1/modules/dashboard/snapshot')).status_code == 200
            selected = (await client.get('/api/v1/modules/assistant/context')).json()
            assert any(item['kind'] == 'lessons' and item['body_text'] for item in selected['items'])
            plugins = (await client.get('/api/v1/ai/plugins')).json()['plugins']
            assert next(item for item in plugins if item['id'] == 'deadlines')['status'] == 'ready'
            task = await client.post('/api/v1/modules/assistant/run', json={'prompt': '整理课程资料', 'plugins': ['deadlines']})
            assert task.status_code == 200 and task.json()['citations'] and not task.json()['tools'][0]['is_error'], task.text
            assert (await client.put('/api/v1/modules/deadlines', json={'enabled': False})).status_code == 200
            assert next(item for item in (await client.get('/api/v1/ai/plugins')).json()['plugins'] if item['id'] == 'deadlines')['status'] == 'disabled'
            assert (await client.get('/api/v1/modules/assistant/chat')).status_code == 200
            assert (await client.put('/api/v1/modules/deadlines', json={'enabled': True})).status_code == 200
            assert len(fixture.calls) == calls_before, 'Aggregates must read the existing caches offline'
            assert (await client.get('/api/v1/modules/elrc/sync')).json()['course_id'] == 'demo-course'
            print('PASS shared integration: legacy caches, official semester, dashboard, assistant context and separate sync state')
            hits = (await client.get('/api/v1/modules/elrc/search?q=电场')).json()['items']
            assert hits and hits[0]['start_seconds'] == 30
            assert (await client.get('/api/v1/modules/elrc/search?q=电场&semester=2025-fall')).json()['items'] == []
            assert (await client.get('/api/v1/modules/elrc/search?q=电场&course_id=other')).status_code == 400
            assert (await client.get('/api/v1/modules/elrc/courses/demo-course/lessons/7-lesson?offset=-1')).status_code == 422
            fixture.fail_voice = True
            refreshed = await client.post('/api/v1/modules/elrc/courses/demo-course/sync', json={'force': True})
            assert refreshed.json()['status'] == 'partial'
            lesson = (await client.get('/api/v1/modules/elrc/courses/demo-course/lessons/7-lesson')).json()
            assert lesson['voice_state'] == 'stale' and lesson['total'] == 105
            print('PASS ELRC: discovery, term isolation, sync, 100ns timestamps, paging, failed-refresh preservation')

            body = {'question': '如何叠加电场？', 'mode': 'answer', 'sources': [hits[0]]}
            assert (await client.post('/api/v1/modules/education/preview', json=body)).json()['calls_ai'] is False
            assert fixture.ai_calls == 0
            assert (await client.post('/api/v1/modules/education/answer', json=body)).status_code == 200
            fixture.forge_quote = True
            invalid = await client.post('/api/v1/modules/education/answer', json=body)
            assert invalid.status_code == 502 and '伪造引文' not in invalid.text
            duplicate = await client.post('/api/v1/modules/education/preview', json={**body, 'sources': [hits[0], hits[0]]})
            assert duplicate.status_code == 422
            print('PASS education: local preview, shared AI, quote verification, duplicate-source rejection')

            listing = (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).json()
            assert listing['total'] == 2 and listing['items'][0]['level'] == 'high'
            post = listing['items'][0]
            assert len(post['attachments']) == 1 and 'hidden script' not in post['body'] and '补充回复' in post['body']
            await client.put('/api/v1/modules/piazza/courses/demo-network/posts/post1/read', json={'read': True})
            await client.post('/api/v1/modules/piazza/courses/demo-network/sync', json={})
            listing = (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).json()
            assert listing['total'] == 2 and next(post for post in listing['items'] if post['id'] == 'post1')['read']
            fixture.fail_post = True
            partial = (await client.post('/api/v1/modules/piazza/courses/demo-network/sync', json={})).json()
            assert partial['status'] == 'partial' and partial['failed_ids'] == ['post2'] and partial['next_offset'] == 0
            fixture.blocked = True
            blocked = await client.post('/api/v1/modules/piazza/courses/demo-network/sync', json={})
            assert blocked.status_code == 401
            assert (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).json()['total'] == 2
            print('PASS Piazza: replies, safe links, rule triage, deduplication, read state, failed-page retry, offline cache')

            owners = {provider: app.state.auth.get_status(provider)['account_revision'] for provider in ('ids','piazza')}
            for provider in owners:
                app.state.auth.store.write('auth:revision:' + provider, 'synthetic-second-account')
            assert (await client.get('/api/v1/modules/elrc/catalog')).json()['courses'] == []
            assert (await client.get('/api/v1/modules/elrc/courses/demo-course')).status_code == 400
            assert (await client.get('/api/v1/modules/elrc/search?q=电场')).json()['items'] == []
            assert (await client.get('/api/v1/modules/piazza/courses')).json()['courses'] == []
            assert (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).status_code == 404
            shared = (await client.get('/api/v1/modules/courses/snapshot')).json()['data']
            assert not shared['lessons'] and not shared['posts']
            for provider, owner in owners.items():
                app.state.auth.store.write('auth:revision:' + provider, owner)
            assert (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).json()['total'] == 2
            assert (await client.get('/api/v1/modules/elrc/search?q=电场')).json()['items']
            print('PASS legacy account isolation: catalog, lesson, search, watched courses, posts, aggregates and switch-back')

            for mid in ('elrc', 'education', 'piazza'):
                assert (await client.get(f'/api/v1/modules/{mid}/openapi.json')).status_code == 200
                disabled = await client.put('/api/v1/modules/' + mid, json={'enabled': False})
                assert disabled.status_code == 200
                assert (await client.get(f'/api/v1/modules/{mid}/openapi.json')).status_code == 404
                assert (await client.put('/api/v1/modules/' + mid, json={'enabled': True})).status_code == 200
            reloaded = (await client.post('/api/v1/modules/reload')).json()['modules']
            assert all(item['status'] == 'ready' for item in reloaded if item['id'] in {'elrc', 'education', 'piazza'})
            assert (await client.get('/api/v1/modules/piazza/posts?course_id=demo-network')).json()['total'] == 2
            print('PASS host integration: registration, CSRF, OpenAPI, disable/enable/reload with preserved state')


if __name__ == '__main__':
    temp = ROOT / '.codex' / 'tmp'
    temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='learning-check-', dir=temp) as directory:
        asyncio.run(check(Path(directory)))
