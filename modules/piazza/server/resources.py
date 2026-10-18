"""Read Piazza's course resource catalog without executing page scripts."""
import json
import re
from urllib.parse import quote, urlencode, urlsplit

from bs4 import BeautifulSoup

from backend.services.campus import SourceError, identity, plain, timestamp
from backend.services.campus.remote import Remote

BASE = 'https://piazza.com'
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,100}')


def resource_page(network: dict) -> str:
    """Build the resource page from the enrolled course's own routing fields."""
    values = [network.get('school_ext'), network.get('term_key') or str(network.get('term') or '').lower().replace(' ', ''), network.get('short_number')]
    if any(not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,200}', value) or value in {'.', '..'} for value in values):
        raise SourceError('Piazza 未提供完整的课程资源入口，已保留已有资料。')
    return BASE + '/' + '/'.join(quote(value, safe='') for value in values) + '/resources'


def parse_resources(html: str, network: dict) -> list[dict]:
    """Normalize file/link entries from the current Resources page bootstrap."""
    course_id = str(network.get('id') or network.get('nid') or '')
    if not IDENTIFIER.fullmatch(course_id):
        raise SourceError('Piazza 课程标识不正确。')
    resources = None
    for script in BeautifulSoup(html, 'html.parser').find_all('script'):
        text = script.string or script.get_text()
        match = re.search(r'\b(?:var|let|const)\s+RESOURCES\s*=\s*', text)
        if match:
            try:
                resources, _ = json.JSONDecoder().raw_decode(text[match.end():])
            except ValueError:
                raise SourceError('Piazza 课件目录格式已变化，已保留已有资料。') from None
            break
    if not isinstance(resources, list) or len(resources) > 1000:
        raise SourceError('Piazza 未返回可读取的课件目录，已保留已有资料。')
    sections = {row['name']: plain(row.get('title')) for row in (network.get('config') or {}).get('resource_sections', []) if isinstance(row, dict) and isinstance(row.get('name'), str)}
    result, seen = [], set()
    for row in resources:
        if not isinstance(row, dict) or not IDENTIFIER.fullmatch(str(row.get('id') or '')) or not isinstance(row.get('config'), dict):
            raise SourceError('Piazza 课件记录缺少合法标识，已保留已有资料。')
        resource_id, config = str(row['id']), row['config']
        if resource_id in seen:
            continue
        seen.add(resource_id)
        kind = config.get('resource_type')
        if kind not in {'file', 'link'}:
            continue
        key = identity('piazza', 'resource:' + course_id + ':' + resource_id)
        section = str(config.get('section') or 'general')
        item = {'id': key, 'source': 'piazza', 'source_id': resource_id, 'source_course_id': course_id,
                'course_id': identity('piazza', course_id), 'title': plain(row.get('subject') or row.get('content')) or '课程资料',
                'path': [sections.get(section) or section], 'resource_type': kind, 'body_text': '',
                'created_at': timestamp(row.get('created')), 'updated_at': timestamp(row.get('updated') or row.get('created'))}
        if kind == 'file':
            item['url'] = BASE + '/class_profile/get_resource/' + course_id + '/' + resource_id
            item['download_url'] = '/api/v1/modules/piazza/file?' + urlencode({'material_id': key})
            item['preview_url'] = item['download_url'] + '&inline=true'
        else:
            url = str(row.get('content') or '')
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            if not valid:
                continue
            item['url'] = url
        result.append(item)
    return result


def fetch_resources(remote: Remote, network: dict) -> list[dict]:
    return parse_resources(remote.html(resource_page(network)), network)
