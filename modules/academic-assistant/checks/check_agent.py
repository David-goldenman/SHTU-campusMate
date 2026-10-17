import asyncio
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi import FastAPI, HTTPException
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox
from backend.services.campus.data import validate_bundle

package = load('academic-assistant')
extract = package.Task.document.__globals__['extract']


def slides():
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="2" r:id="r2"/><p:sldId id="1" r:id="r1"/></p:sldIdLst></p:presentation>')
        archive.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="r1" Target="slides/slide1.xml"/><Relationship Id="r2" Target="/ppt/slides/slide2.xml"/></Relationships>')
        for number, text in [(1, 'Vectors are added by components.'), (2, 'Vector superposition is the sum of vectors.')]:
            archive.writestr('ppt/slides/slide' + str(number) + '.xml', '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p><a:r><a:t>' + text + '</a:t></a:r></a:p></p:sld>')
    return data.getvalue()


def check_documents():
    assert extract(slides(), 'application/zip', 'notes.pptx')['pages'][0].startswith('Vector superposition')
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 72 700 Td (Synthetic assignment text) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    data = io.BytesIO()
    writer.write(data)
    assert 'Synthetic assignment text' in extract(data.getvalue(), 'application/pdf', 'assignment.pdf')['pages'][0]
    try:
        extract(b'unsupported', 'application/octet-stream', 'unknown.bin')
        raise AssertionError('Unsupported documents must not invent page text')
    except HTTPException as error:
        assert error.status_code == 422


async def check():
    with sandbox('academic-assistant') as context:
        original_status = context.auth.get_status
        context.auth.get_status = lambda provider: {**original_status(provider), 'identity_verified': True}
        material = {'id': 'blackboard:slides', 'source': 'blackboard', 'title': 'Synthetic slides.pptx', 'url': 'https://example.edu/course', 'download_url': '/api/v1/modules/blackboard/file?material_id=blackboard%3Aslides'}
        assignment = {'id': 'gradescope:hw', 'source': 'gradescope', 'title': '合成作业', 'due_at': '2026-10-20T20:00:00+08:00', 'submitted': False, 'actionable': True}

        async def api(name, path='/snapshot', **options):
            if name == 'blackboard':
                return httpx.Response(200, content=slides(), headers={'content-type': 'application/zip'})
            if name == 'assignments':
                return httpx.Response(200, json={'data': {'assignments': [assignment]}, 'pending': [assignment]})
            if name == 'courses':
                return httpx.Response(200, json={'data': validate_bundle({'assignments': [assignment], 'materials': [material], 'metadata': {'source_metadata': {'blackboard': {'updated_at': 'synthetic-revision'}}}})})
            raise AssertionError((name, path))

        context.api = api
        app = FastAPI()
        router = package.create_router(context)
        app.include_router(router, prefix='/api/v1/modules/academic-assistant')
        loop = asyncio.get_running_loop()
        mode, last_token = 'valid', None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:17668') as client:
            base = '/api/v1/modules/academic-assistant'

            async def tools(token):
                headers = {'Authorization': 'Bearer ' + token}
                request = SimpleNamespace(method='POST', url=SimpleNamespace(path=base + '/tools/query'), headers=httpx.Headers(headers))
                assert package.authorize_write(context, request)
                request.url.path = base + '/profile'
                assert not package.authorize_write(context, request)
                response = await client.post(base + '/tools/query', json={'area': 'assignments', 'pending': True}, headers=headers)
                assert response.status_code == 200, response.text
                source = response.json()['items'][0]
                response = await client.post(base + '/tools/document', json={'record_id': material['id'], 'q': 'superposition'}, headers=headers)
                assert response.status_code == 200, response.text
                document = response.json()['items'][0]
                assert document['page'] == 1 and 'superposition' in document['text']
                response = await client.post(base + '/tools/remember', json={'profile': {'weekly_hours': 10}, 'quote': '每周10小时'}, headers=headers)
                assert response.status_code == 200, response.text
                assert (await client.post(base + '/tools/remember', json={'profile': {'major': '不存在的专业'}, 'quote': '每周10小时'}, headers=headers)).status_code == 422
                assert (await client.post(base + '/tools/navigate', json={'category': 'assignments'}, headers=headers)).status_code == 200
                citations = [{'source_id': source['source_id'], 'quote': 'title: 合成作业\nsubmitted: false'}, {'source_id': document['source_id'], 'quote': 'Vector  superposition'}]
                rejected = await client.post(base + '/tools/finish', json={'text': '合成回答', 'citations': [{'source_id': source['source_id'], 'quote': '不存在的作业'}]}, headers=headers)
                assert rejected.status_code == 422
                while len(package._agent.tasks[token].activity) < 24:
                    assert (await client.post(base + '/tools/query', json={'area': 'assignments'}, headers=headers)).status_code == 200
                assert (await client.post(base + '/tools/query', json={'area': 'assignments'}, headers=headers)).status_code == 429
                response = await client.post(base + '/tools/finish', json={**({} if mode == 'stream' else {'text': '请先复习向量叠加，再安排合成作业。'}), 'citations': citations}, headers=headers)
                assert response.status_code == 200 and response.json()['accepted']

            def run(prompt, context, plugins, plugin_env, on_event=None, cancel_event=None):
                nonlocal last_token
                last_token = plugin_env['CAMPUS_PLUGIN_STUDY_TOKEN']
                assert last_token not in prompt + context and plugins == ['academic-assistant']
                assert 'historical-private-context' not in context
                assert len(json.loads(context)['history']) == {'valid':0,'stream':2,'invalid':4,'changed':4,'cancelled':4}[mode]
                if mode == 'changed':
                    original.auth.revision = 'synthetic-account-two'
                    return {'content': json.dumps({'text': 'old-account-result'}), 'tools': [], 'model': 'synthetic'}
                if mode == 'cancelled':
                    assert cancel_event.wait(5)
                    return {'content': 'synthetic-cancelled-answer', 'tools': [], 'model': 'synthetic'}
                if on_event:
                    on_event({'type': 'chunk', 'chunk': {'type': 'text-delta', 'text': 'synthetic-unverified-body'}})
                if mode in {'valid', 'stream'}:
                    asyncio.run_coroutine_threadsafe(tools(last_token), loop).result(10)
                if on_event:
                    on_event({'type': 'start'})
                    on_event({'type': 'chunk', 'chunk': {'type': 'reasoning-delta', 'text': 'synthetic-private-thought'}})
                    for text in ['## 复习计划\n\n', '**向量叠加** [1]']:
                        on_event({'type': 'chunk', 'chunk': {'type': 'text-delta', 'text': text}})
                if mode == 'stream':
                    return {'content': '## 复习计划\n\n**向量叠加** [1]', 'tools': [], 'model': 'synthetic'}
                return {'content': '已完成', 'tools': [{'name': 'study_query', 'is_error': False}], 'model': 'synthetic'}

            original = context
            context.ai.run = run
            original.store.write('chat:' + package.account_revision(original), [{'role': 'user', 'text': '历史问题'}, {'role': 'assistant', 'text': 'historical-private-context'}])
            assert (await client.post(base + '/tools/query', json={'area': 'assignments'})).status_code == 401
            assert (await client.post(base + '/chat', json={'message': '记住我每周10小时，帮我准备作业。'})).status_code == 200
            value = (await client.get(base + '/chat')).json()['messages']
            assert len(value) == 4 and value[-1]['navigation'] == 'assignments'
            assert value[-1]['citations'][1]['page'] == 1
            assert value[-1]['citations'][1]['quote'] == 'Vector superposition'
            assert 'due_at:' in value[-1]['citations'][0]['quote']
            assert (await client.get(base + '/profile')).json()['profile']['weekly_hours'] == 10
            assert (await client.post(base + '/tools/query', json={'area': 'assignments'}, headers={'Authorization': 'Bearer ' + last_token})).status_code == 401
            mode = 'stream'
            response = await client.post(base + '/chat/stream', json={'message': '记住我每周10小时，帮我准备作业。'})
            events = [json.loads(line) for line in response.text.splitlines()]
            assert response.headers['content-type'].startswith('application/x-ndjson')
            assert len([event for event in events if event['type'] == 'delta']) == 2
            assert events[-1]['type'] == 'complete' and events[-1]['message']['text'].startswith('## 复习计划')
            assert events[-1]['message']['citations'][1]['page'] == 1
            assert 'synthetic-private-thought' not in response.text and 'synthetic-unverified-body' not in response.text and last_token not in response.text
            mode = 'cancelled'
            from starlette.requests import Request
            endpoint = next(route.endpoint for route in router.routes if route.path == '/chat/stream')
            request = Request({'type': 'http', 'scheme': 'http', 'server': ('test', 80), 'path': base + '/chat/stream', 'headers': []})
            response = await endpoint(package.Chat(message='停止合成任务'), request)
            await anext(response.body_iterator)
            await response.body_iterator.aclose()
            assert not package._agent.tasks and len((await client.get(base + '/chat')).json()['messages']) == 6
            mode = 'invalid'
            assert (await client.post(base + '/chat', json={'message': '再规划一次。'})).status_code == 502
            response = await client.post(base + '/chat/stream', json={'message': '再规划一次。'})
            assert json.loads(response.text.splitlines()[-1])['type'] == 'error'
            assert len((await client.get(base + '/chat')).json()['messages']) == 6
            mode = 'changed'
            response = await client.post(base + '/chat', json={'message': '处理中切换账号。'})
            assert response.status_code == 409 and 'old-account-result' not in response.text
            assert (await client.get(base + '/chat')).json()['messages'] == []
            assert (await client.get(base + '/profile')).json()['profile']['weekly_hours'] is None
        package.stop(context)


check_documents()
asyncio.run(check())
print('academic assistant: PDF/PPTX page order, task-bound tools, exact citations, explicit profile updates, navigation, history and account isolation passed')
