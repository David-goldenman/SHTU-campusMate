"""Exercise playback with synthetic school responses, no real account or video."""
import importlib.util
import json
from pathlib import Path
import re
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('elrc_playback_checks', ROOT / 'modules/elrc/server/__init__.py', submodule_search_locations=[str(ROOT / 'modules/elrc/server')])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
playback = sys.modules[spec.name + '.playback']


class Fixture:
    def __init__(self, media=None):
        self.owner = 'account-one'
        self.media = media or bytes(range(256)) * 20000
        self.calls = []
        self.mode = ''
        self.address = '/bucket-z/teacher.webm'
        self.source = SimpleNamespace(owner=lambda: self.owner, cancelled=threading.Event(), hosts=['elrc.shanghaitech.edu.cn'])
        self.context = SimpleNamespace(auth=SimpleNamespace(authenticated_client=self.authenticated_client))
        self.item = {'id': 'elrc:lesson:demo:second', 'title': '合成录播', 'url': 'https://elrc.shanghaitech.edu.cn/learn/videoreview/course?id=review', 'stream_ids': ['video-2']}
        self.player = playback.Playback(self.context, self.source, lambda: {'data': {'lessons': [self.item]}})
        self.app = FastAPI()
        self.app.include_router(self.player.router, prefix='/api/v1/modules/elrc')

    @contextmanager
    def authenticated_client(self, provider, target=None, cancelled=None):
        assert (provider, target) == ('ids', 'elrc')
        with httpx.Client(transport=httpx.MockTransport(self.handle)) as client:
            yield client

    def handle(self, request):
        self.calls.append((request.method, str(request.url), request.headers.get('range')))
        assert request.url.host == 'elrc.shanghaitech.edu.cn'
        assert request.headers.get('referer') == self.item['url']
        path = request.url.path
        if path.endswith('/recording/video/info'):
            data = {'courseId': 'course', 'courseNo': 'CS100', 'recordingVideoInfoShows': [
                {'week': str(i), 'recordInfoDetailList': [{'weekDate': f'2026-10-{i + 10}', 'weekDay': '星期一', 'section': '1-2', 'videoInfoList': [{'videoId': f'video-{i}', 'scheduleId': f'schedule-{i}'}]}]} for i in (1, 2)]}
        elif path.endswith('/relation/videos'):
            query = json.loads(request.content)
            assert query['scheduleIds'] in [['schedule-1'], ['schedule-2']]
            data = {'data': [{'contentId_': 'teacher', 'seat': 'TchPan'}, {'contentId_': 'screen', 'seat': 'Screen'}]}
        elif path.endswith('/download/fileinfo'):
            assert json.loads(request.content) == ['teacher', 'screen']
            if self.mode == 'switch':
                self.owner = 'account-two'
            data = [{'contentId': item, 'fileGroups': [{'files': [{'downloadAddress': self.address if item == 'teacher' else '/bucket-z/screen.webm'}]}]} for item in ('teacher', 'screen')]
        else:
            if self.mode == 'redirect':
                return httpx.Response(302, headers={'Location': 'https://example.invalid/private'})
            if self.mode == 'denied':
                return httpx.Response(403)
            if self.mode == 'login':
                return httpx.Response(200, headers={'content-type': 'text/html'}, content=b'<html>login</html>')
            if self.mode == 'oversize':
                return httpx.Response(200, headers={'content-type': 'video/webm'}, content=self.media)
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', request.headers['range'])
            start, end = match.groups()
            start, end = (int(start), min(int(end), len(self.media) - 1)) if start else (max(0, len(self.media) - int(end)), len(self.media) - 1)
            if start >= len(self.media):
                return httpx.Response(416, headers={'Content-Range': f'bytes */{len(self.media)}'})
            content = self.media[start:end + 1]
            if self.mode == 'truncated':
                content = content[:-1]
            return httpx.Response(206, headers={'content-type': 'video/webm', 'Content-Range': f'bytes {start}-{end}/{len(self.media)}', 'content-length': str(len(content))}, content=content)
        return httpx.Response(200, json={'success': True, 'data': data})


def check():
    fixture = Fixture()
    with TestClient(fixture.app) as client:
        base = '/api/v1/modules/elrc/playback'
        assert client.get(base, params={'lesson_id': 'unknown'}).status_code == 404
        assert not fixture.calls
        opened = client.get(base, params={'lesson_id': fixture.item['id']}).json()
        token = opened['token']
        assert opened['selected'] == '1' and len(opened['lessons']) == 2
        selection = f'{base}/{token}/sources'
        assert client.get(selection, params={'lesson': '99'}).status_code == 404
        selected = client.get(selection, params={'lesson': '1'})
        assert selected.status_code == 200, selected.text
        assert 'downloadAddress' not in selected.text and 'elrc.shanghaitech.edu.cn' not in selected.text
        assert [value['label'] for value in selected.json()['sources']] == ['全景画面', '屏幕画面']
        url = selected.json()['sources'][0]['url']
        first = client.get(url)
        assert first.status_code == 206 and len(first.content) == playback.CHUNK
        assert first.content == fixture.media[:playback.CHUNK]
        assert first.headers['content-range'] == f'bytes 0-{playback.CHUNK - 1}/{len(fixture.media)}'
        assert first.headers['cache-control'] == 'no-store'
        rest = client.get(url, headers={'Range': f'bytes={playback.CHUNK}-'})
        assert rest.content == fixture.media[playback.CHUNK:]
        assert client.get(url, headers={'Range': 'bytes=90-120'}).content == fixture.media[90:121]
        assert client.get(url, headers={'Range': 'bytes=-100'}).content == fixture.media[-100:]
        assert client.head(url, headers={'Range': 'bytes=90-120'}).content == b''
        for value in ('bytes=5-1', 'bytes=-0', 'bytes=0-1,5-9', 'bytes=12345678901234567-', 'wrong'):
            count = len(fixture.calls)
            assert client.get(url, headers={'Range': value}).status_code == 416
            assert len(fixture.calls) == count
        assert client.get(url, headers={'Range': 'bytes=99999999-'}).status_code == 416
        for mode, status in [('denied', 403), ('login', 502), ('redirect', 502), ('oversize', 502), ('truncated', 502)]:
            fixture.mode = mode
            response = client.get(url)
            assert response.status_code == status, (mode, response.text)
        fixture.mode = ''
        fixture.address = 'https://example.invalid/private'
        assert client.get(selection, params={'lesson': '1'}).status_code == 502
        fixture.address = '/bucket-z/teacher.webm'
        fixture.mode = 'switch'
        assert client.get(selection, params={'lesson': '1'}).status_code == 409
        assert client.get(url).status_code == 409
        fixture.owner = 'account-one'; fixture.mode = ''
        fixture.player.sessions[token]['used'] -= playback.IDLE_SECONDS + 1
        assert client.get(url).status_code == 404
        for _ in range(10):
            assert client.get(base, params={'lesson_id': fixture.item['id']}).status_code == 200
        assert len(fixture.player.sessions) == 8
        fixture.player.close()
        assert not fixture.player.sessions
        fixture.source.cancelled.set()
        assert client.get(base, params={'lesson_id': fixture.item['id']}).status_code == 409
    print('PASS: known recordings, lesson matching, multi-angle sources, local-only media URLs, bounded ranges, seeking, account changes, expiry, redirects, failures and cleanup')


if __name__ == '__main__':
    check()
