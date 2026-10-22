"""Synthetic course-resource, bounded download and account-isolation checks."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backend.services.campus import SourceError
from checks.module_support import load, sandbox

package = load('piazza')
resources = sys.modules[package.__name__ + '.resources']
course_package = load('courses')
NETWORK = {'id': 'demo', 'name': 'Synthetic VLSI', 'course_number': 'EE291F', 'term': 'Fall 2026',
           'term_key': 'fall2026', 'school_ext': 'example.edu', 'short_number': 'ee291f',
           'config': {'resource_sections': [{'name': 'lecture_notes', 'title': 'Lecture notes'}]}}
FILE = {'id': 'slides', 'subject': 'Synthetic timing.pdf', 'content': 'timing.pdf',
        'created': '2026-10-01T00:00:00Z', 'updated': '2026-10-14T00:00:00Z',
        'config': {'resource_type': 'file', 'section': 'lecture_notes'}}
LINK = {'id': 'reading', 'subject': 'Reading', 'content': 'https://example.edu/reading',
        'config': {'resource_type': 'link', 'section': 'general'}}


def page(rows):
    return '<script>var RESOURCES = ' + json.dumps(rows).replace('</', '<\\/') + '; window.untrusted = true;</script>'


def parser_checks():
    values = resources.parse_resources(page([FILE, FILE, LINK, {**LINK, 'id': 'unsafe', 'content': 'javascript:alert(1)'}]), NETWORK)
    assert len(values) == 2 and values[0]['path'] == ['Lecture notes']
    assert values[0]['id'] == 'piazza:resource:demo:slides'
    assert values[0]['download_url'].startswith('/api/v1/modules/piazza/file?material_id=')
    assert values[0]['preview_url'].endswith('&inline=true')
    assert 'download_url' not in values[1], 'External links remain links, not authenticated download targets'
    assert resources.parse_resources(page([]), NETWORK) == []
    for html in ('<p>Unavailable</p>', '<script>var RESOURCES = fetch("/secret");</script>', page([{**FILE, 'id': '../other'}]), page({})):
        try:
            resources.parse_resources(html, NETWORK)
            raise AssertionError('Malformed resources must not replace cached files')
        except SourceError:
            pass
    for field in ('school_ext', 'term_key', 'short_number'):
        try:
            resources.resource_page({**NETWORK, field: '../escape'})
            raise AssertionError('Course routing segments cannot escape their path')
        except SourceError:
            pass


async def check_api():
    mode, calls = 'ready', []

    def upstream(request):
        nonlocal mode
        calls.append(str(request.url))
        assert request.url.host == 'piazza.com'
        if request.url.path == '/logic/api':
            body = json.loads(request.content)
            return httpx.Response(200, json={'result': {'networks': [NETWORK]} if body['method'] == 'user.status' else {'feed': []}})
        if request.url.path.endswith('/resources'):
            if mode == 'missing':
                return httpx.Response(503)
            return httpx.Response(200, text=page([] if mode == 'empty' else [FILE, LINK]), headers={'content-type': 'text/html'})
        assert request.url.path == '/class_profile/get_resource/demo/slides', request.url
        if mode == 'redirect':
            return httpx.Response(302, headers={'location': 'https://foreign.example/private.pdf'})
        if mode == 'oversized':
            return httpx.Response(200, content=b'small', headers={'content-type': 'application/pdf', 'content-length': str(31 * 1024 * 1024)})
        if mode == 'login':
            return httpx.Response(200, text='<html>Login</html>', headers={'content-type': 'text/html'})
        if mode == 'svg':
            return httpx.Response(200, content=b'<svg xmlns="http://www.w3.org/2000/svg"/>', headers={'content-type': 'image/svg+xml'})
        if mode == 'account':
            context.auth.revision = 'second-account'
        if mode == 'revision':
            saved = context.store.read('campus:snapshot')
            saved['data']['materials'][0]['updated_at'] = '2026-10-18T00:00:00Z'
            context.store.write('campus:snapshot', saved)
        return httpx.Response(200, content=b'%PDF-synthetic-material', headers={'content-type': 'application/pdf'})

    with sandbox('piazza', upstream) as context, sandbox('courses') as course_context:
        app = FastAPI()
        app.include_router(package.create_router(context), prefix='/piazza')
        source = package._source
        try:
            source.run()
            data = source.snapshot()['data']
            assert len(data['materials']) == 2 and not data['issues']
            material = data['materials'][0]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
                async def api(name, path='/snapshot', **options):
                    return await client.get('/piazza' + path) if name == 'piazza' else httpx.Response(404, json={})
                course_context.api = api
                app.include_router(course_package.create_router(course_context), prefix='/courses')
                catalog = (await client.get('/courses/catalog/courses')).json()['items']
                assert len(catalog) == 1 and catalog[0]['code'] == 'EE291F'
                detail = (await client.get('/courses/course', params={'course_id': catalog[0]['id']})).json()
                assert detail['materials'][0]['download_url'] == material['download_url']
                evidence = (await client.post('/courses/context', json={'course_id': catalog[0]['id']})).json()
                assert any(row['kind'] == 'materials' and row['source'] == 'piazza' for row in evidence['items'])
                before = len(calls)
                revision = (await client.get('/piazza/snapshot')).json()['account_revision']
                assert revision == source.owner()
                assert (await client.get('/piazza/file', params={'material_id': material['id'], 'account_revision': 'previous-account'})).status_code == 409
                assert len(calls) == before, 'A stale batch must not fetch files under another account'
                assert (await client.get('/piazza/file', params={'material_id': 'piazza:resource:other:slides'})).status_code == 404
                assert len(calls) == before, 'Unknown files must not trigger a remote request'
                for inline in (False, True):
                    result = await client.get('/piazza/file', params={'material_id': material['id'], 'inline': inline, 'account_revision': revision})
                    assert result.status_code == 200 and result.content == b'%PDF-synthetic-material'
                    assert result.headers['content-disposition'].startswith('inline;' if inline else 'attachment;')
                    assert not list((context.data_dir / 'tmp' / 'downloads').iterdir()), 'Response cleanup removes temporary files'
                mode = 'svg'
                result = await client.get('/piazza/file', params={'material_id': material['id'], 'inline': True})
                assert result.status_code == 200 and result.headers['content-disposition'].startswith('attachment;'), 'Only PDF files may render inline on the application origin'
                assert not list((context.data_dir / 'tmp' / 'downloads').iterdir())
                for mode in ('redirect', 'oversized', 'login'):
                    result = await client.get('/piazza/file', params={'material_id': material['id']})
                    assert result.status_code == 502, (mode, result.text)
                mode = 'missing'
                source.run()
                assert source.snapshot()['data']['materials'][0]['stale'] and source.snapshot()['data']['issues']
                mode = 'ready'
                source.run()
                mode = 'revision'
                assert (await client.get('/piazza/file', params={'material_id': material['id']})).status_code == 409
                mode = 'account'
                assert (await client.get('/piazza/file', params={'material_id': material['id']})).status_code == 409
                assert (await client.get('/piazza/snapshot')).json()['data']['materials'] == []
                assert (await client.get('/piazza/file', params={'material_id': material['id']})).status_code == 404
                assert not list((context.data_dir / 'tmp' / 'downloads').iterdir())
                context.auth.revision = 'synthetic-account-one'
                mode = 'empty'
                source.run()
                assert source.snapshot()['data']['materials'] == [], 'A successful empty catalog removes withdrawn files'
        finally:
            package.stop(context)


parser_checks()
asyncio.run(check_api())
print('Piazza resources: catalog parsing, course/context integration, preview/download, scope, redirects, bounds, cache retention, removal and account/revision races passed')
