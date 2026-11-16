"""Account-scoped ELRC playback; upstream credentials stay on the local server."""
import re
import secrets
import threading
import time
from urllib.parse import parse_qs, urljoin, urlsplit

from fastapi import APIRouter, HTTPException, Query, Request, Response

from backend.services.auth import LoginRequired
from backend.services.campus import Remote, SourceError, rows
from .reader import BASE, api

CHUNK = 4 * 1024 * 1024
IDLE_SECONDS = 30 * 60


def media_url(address):
    if not isinstance(address, str) or not address.strip() or any(ord(c) <= 32 or c == '\\' or ord(c) == 127 for c in address):
        raise SourceError('录播地址格式不正确。')
    value = urljoin(BASE, address)
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.hostname != 'elrc.shanghaitech.edu.cn' or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment:
        raise SourceError('录播地址不属于教学社区。')
    if '/bucket-z/' in parsed.path and 'isSysAuth' not in parse_qs(parsed.query):
        value += ('&' if parsed.query else '?') + 'isSysAuth=true'
    return value


def lessons(data, course_id):
    if not isinstance(data, dict) or str(data.get('courseId')) != course_id:
        raise SourceError('录播课程与所选课程不一致。')
    result = []
    for week in rows(data.get('recordingVideoInfoShows')):
        for day in rows(week.get('recordInfoDetailList')):
            live = day.get('courseLiveInfo') or {}
            if not isinstance(live, dict) or live.get('courseId') and str(live['courseId']) != course_id:
                raise SourceError('录播课次与所选课程不一致。')
            videos = rows(day.get('videoInfoList'))
            schedule_ids = list(dict.fromkeys(str(value) for value in [live.get('scheduleId'), *(v.get('scheduleId') for v in videos)] if value))
            number = next((str(value) for value in [live.get('courseNo'), day.get('courseNo'), day.get('course_number'), day.get('courseNumber'), data.get('courseNo'), data.get('course_number'), data.get('courseNumber')] if value), '')
            query = {'courseId': course_id, 'courseNo': number, 'week': str(week.get('week') or ''), 'weekDay': str(day.get('weekDay') or ''), 'section': str(day.get('section') or ''), 'scheduleIds': schedule_ids}
            if not all(query.values()):
                continue
            result.append({'id': str(len(result)), 'title': f"第 {query['week']} 周 · {day.get('weekDate') or query['weekDay']} · 第 {query['section']} 节", 'query': query,
                           'stream_ids': [str(v['videoId']) for v in videos if v.get('videoId')]})
    if not result:
        raise SourceError('暂无信息完整的可播放课次，请在教学社区查看。')
    return result


def sources(remote, query):
    page = api(remote, '/rman/v1/search/new/relation/videos', payload=query)
    videos = rows(page, 'data')
    ids = [str(item.get('contentId_') or '') for item in videos]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids) or len(ids) > 24:
        raise SourceError('这节课没有可确认的录播画面。')
    files = rows(api(remote, '/rman/v1/entity/download/fileinfo', payload=ids))
    indexed = {str(item.get('contentId')): item for item in files}
    if len(indexed) != len(files) or not set(ids) <= indexed.keys():
        raise SourceError('录播画面与文件信息不一致。')
    result = []
    for video, identifier in zip(videos, ids):
        file = indexed[identifier]
        addresses = [value.get('downloadAddress') for group in rows(file.get('fileGroups')) for value in rows(group.get('files'))]
        extra = file.get('downloadAddress') or []
        addresses.extend(extra if isinstance(extra, list) else [extra])
        address = next((value for value in addresses if isinstance(value, str) and value.strip()), None)
        name = str(next((value for value in [video.get('seat'), file.get('seat'), video.get('name'), video.get('name_'), file.get('entityName')] if value), ''))
        lower = name.lower()
        descriptions = ' '.join(str(value or '') for value in (name, video.get('name'), video.get('name_'), file.get('entityName'))).lower()
        if '学生' in descriptions or 'student' in descriptions or lower in {'stu', 'stupan'}:
            continue
        label = '全景画面' if 'tchpan' in lower or '全景' in name else '屏幕画面' if 'screen' in lower or '屏幕' in name else '教师画面' if lower == 'tch' or 'teacher' in lower or '教师' in name or '近景' in name else name or f'画面 {len(result) + 1}'
        result.append({'label': label, 'address': media_url(address)})
    if not result:
        raise SourceError('这节课暂无可播放的教师或屏幕画面。')
    return result


def bounded_range(value):
    if not value:
        return f'bytes=0-{CHUNK - 1}'
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value)
    if not match or not any(match.groups()) or any(len(part) > 16 for part in match.groups()):
        raise HTTPException(416, '不支持这个视频读取范围。')
    start, end = match.groups()
    if not start:
        if int(end) == 0:
            raise HTTPException(416, '视频读取范围为空。')
        return f'bytes=-{min(int(end), CHUNK)}'
    start = int(start)
    if end and int(end) < start:
        raise HTTPException(416, '视频读取范围无效。')
    return f'bytes={start}-{min(int(end), start + CHUNK - 1) if end else start + CHUNK - 1}'


class Playback:
    def __init__(self, context, source, snapshot):
        self.context, self.source, self.snapshot = context, source, snapshot
        self.sessions = {}
        self.lock = threading.RLock()
        self.router = APIRouter()
        self.router.add_api_route('/playback', self.open, methods=['GET'])
        self.router.add_api_route('/playback/{token}/sources', self.select, methods=['GET'])
        self.router.add_api_route('/playback/{token}/media/{source_id}', self.media, methods=['GET'])
        self.router.add_api_route('/playback/{token}/media/{source_id}', self.media, methods=['HEAD'], include_in_schema=False)

    def close(self):
        with self.lock:
            self.sessions.clear()

    def check(self, owner):
        if self.source.cancelled.is_set():
            raise HTTPException(409, '教学社区模块正在停止。')
        if self.source.owner() != owner:
            raise HTTPException(409, '账号已切换，请重新打开录播。')

    def session(self, token):
        with self.lock:
            now = time.monotonic()
            self.sessions = {key: value for key, value in self.sessions.items() if now - value['used'] < IDLE_SECONDS}
            value = self.sessions.get(token)
            if value is None:
                raise HTTPException(404, '播放会话已结束，请重新打开录播。')
            self.check(value['owner'])
            value['used'] = now
            return value

    def read(self, owner, operation, referer=None):
        self.check(owner)
        with self.context.auth.authenticated_client('ids', target='elrc', cancelled=self.source.cancelled) as client:
            self.check(owner)
            if referer:
                client.headers['Referer'] = referer
            result = operation(Remote(client, self.source.cancelled, self.source.hosts))
            self.check(owner)
        self.check(owner)
        return result

    def open(self, lesson_id: str = Query(min_length=1, max_length=500)):
        owner = self.source.owner()
        item = next((item for item in self.snapshot()['data']['lessons'] if item['id'] == lesson_id), None)
        if item is None:
            raise HTTPException(404, '录播不在当前账号目录中，请先同步。')
        referer = media_url(item.get('url'))
        parsed = urlsplit(referer)
        match = re.fullmatch(r'/learn/videoreview/([A-Za-z0-9_-]{1,120})', parsed.path)
        recording_id = parse_qs(parsed.query).get('id', [''])[0]
        if not match or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', recording_id):
            raise SourceError('这条录播缺少课次入口，请在原站查看。')
        course_id = match[1]
        value = self.read(owner, lambda remote: lessons(api(remote, '/learn/v1/course/recording/video/info', {'courseId': course_id, 'id': recording_id}), course_id), referer)
        preferred = set(item.get('stream_ids', [])) if item['id'].startswith('elrc:lesson:') else set()
        selected = next((lesson['id'] for lesson in value if preferred.intersection(lesson['stream_ids'])), value[0]['id'])
        token = secrets.token_hex(16)
        with self.lock:
            self.check(owner)
            self.sessions = {key: session for key, session in self.sessions.items() if session['owner'] == owner and time.monotonic() - session['used'] < IDLE_SECONDS}
            while len(self.sessions) >= 8:
                del self.sessions[min(self.sessions, key=lambda key: self.sessions[key]['used'])]
            self.sessions[token] = {'owner': owner, 'used': time.monotonic(), 'referer': referer, 'lessons': value, 'sources': {}}
        return {'token': token, 'title': item['title'], 'selected': selected, 'lessons': [{key: lesson[key] for key in ('id', 'title')} for lesson in value]}

    def select(self, token: str, lesson: str = Query(min_length=1, max_length=8)):
        session = self.session(token)
        selected = next((item for item in session['lessons'] if item['id'] == lesson), None)
        if selected is None:
            raise HTTPException(404, '课次不在当前播放目录中。')
        value = self.read(session['owner'], lambda remote: sources(remote, selected['query']), session['referer'])
        result = []
        with self.lock:
            self.session(token)
            # Retain recent selections for a late browser range request while switching.
            while len(session['sources']) + len(value) > 48:
                session['sources'].pop(next(iter(session['sources'])))
            for item in value:
                source_id = secrets.token_hex(12)
                session['sources'][source_id] = item
                result.append({'id': source_id, 'label': item['label'], 'url': f'/api/v1/modules/elrc/playback/{token}/media/{source_id}'})
        return {'sources': result}

    def media(self, token: str, source_id: str, request: Request):
        session = self.session(token)
        with self.lock:
            selected = session['sources'].get(source_id)
        if selected is None:
            raise HTTPException(404, '画面已过期，请重新选择课次。')
        requested = bounded_range(request.headers.get('range', ''))

        def load(remote):
            url = selected['address']
            for _ in range(4):
                remote.check()
                url = media_url(url)
                with remote.client.stream('GET', url, headers={'Range': requested, 'Referer': session['referer'], 'Accept-Encoding': 'identity'}, timeout=20, follow_redirects=False) as upstream:
                    if upstream.is_redirect:
                        location = upstream.headers.get('location')
                        if not location:
                            raise SourceError('录播跳转缺少目标地址。')
                        url = urljoin(url, location)
                        continue
                    if upstream.status_code == 401:
                        raise LoginRequired('录播登录已失效，请重新连接教学社区。')
                    if upstream.status_code == 403:
                        raise HTTPException(403, '学校未授权播放这条录播，或播放地址已过期。')
                    if upstream.status_code == 416:
                        headers = {}
                        if re.fullmatch(r'bytes \*/\d{1,16}', upstream.headers.get('content-range', '')):
                            headers['Content-Range'] = upstream.headers['content-range']
                        return Response(status_code=416, headers=headers)
                    if upstream.status_code not in {200, 206}:
                        raise SourceError('录播暂时无法读取，请重新加载或打开原站。')
                    mime = upstream.headers.get('content-type', '').split(';')[0].lower()
                    if not (mime.startswith('video/') or mime == 'application/octet-stream'):
                        raise SourceError('学校没有返回视频内容，请检查登录后重试。')
                    size = upstream.headers.get('content-length', '')
                    if size and (not size.isdigit() or int(size) > CHUNK):
                        raise SourceError('来源不支持分段播放，请在原站观看。')
                    headers = {'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store'}
                    segment = None
                    if upstream.status_code == 206:
                        segment = re.fullmatch(r'bytes (\d{1,16})-(\d{1,16})/(\d{1,16})', upstream.headers.get('content-range', ''))
                        if not segment or not 0 <= int(segment[1]) <= int(segment[2]) < int(segment[3]) or int(segment[2]) - int(segment[1]) + 1 > CHUNK:
                            raise SourceError('录播分段信息不正确。')
                        headers['Content-Range'] = segment[0]
                    body = bytearray()
                    deadline = time.monotonic() + 30
                    for chunk in upstream.iter_bytes(64 * 1024):
                        remote.check()
                        self.check(session['owner'])
                        if time.monotonic() > deadline:
                            raise SourceError('视频读取过慢，请检查网络后重试。')
                        body.extend(chunk)
                        if len(body) > CHUNK:
                            raise SourceError('来源不支持分段播放，请在原站观看。')
                    if not body or segment and len(body) != int(segment[2]) - int(segment[1]) + 1:
                        raise SourceError('录播分段未完整读取，请重试。')
                    headers['Content-Length'] = str(len(body))
                    return Response(b'' if request.method == 'HEAD' else bytes(body), status_code=upstream.status_code, media_type=mime if mime.startswith('video/') else 'video/mp4', headers=headers)
            raise SourceError('录播跳转次数过多。')

        return self.read(session['owner'], load)
