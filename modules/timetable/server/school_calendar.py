import io
import json
import re
import subprocess
import tempfile
import threading
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from backend.core.paths import PROJECT
from backend.core.vault import windows_path, windows_tool
from backend.services.campus.data import digest

BASE = 'https://www.shanghaitech.edu.cn'
INDEX = BASE + '/1024/list.htm'
SEASONS = {'秋': 'fall', '春': 'spring', '暑': 'summer', '夏': 'summer'}


def term_key(metadata):
    match = re.search(r'(20\d{2})-(20\d{2}).*?([秋春夏暑])', metadata.get('semester', ''))
    return match[1] + '-' + SEASONS[match[3]] if match else None


def monday(year, month, week):
    first = date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (week - 1))


def inferred_week_one(metadata):
    """Infer week one from the semester name when the school calendar is unavailable.

    The convention matches the published calendar: autumn starts on the second Monday of
    September, spring on the second Monday of February and summer on the first Monday of
    July. Callers must label the result as inferred, never as the official calendar.
    """
    key = term_key(metadata)
    if key is None:
        return None
    year, season = int(key[:4]), key[5:]
    if season == 'fall':
        return monday(year, 9, 2).isoformat()
    if season == 'summer':
        return monday(year + 1, 7, 1).isoformat()
    return monday(year + 1, 2, 2).isoformat()


def parse(text):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    matches = list(re.finditer(r'([秋春暑夏])学期[（(](20\d{2})[.年/](\d{1,2})[.月/](\d{1,2})', text))
    terms = {}
    for match in matches:
        start = date(int(match[2]), int(match[3]), int(match[4]))
        if start.weekday() != 0:
            raise ValueError('识别出的开学日期不是周一，请手动核对。')
        year = start.year if match[1] == '秋' else start.year - 1
        key = str(year) + '-' + SEASONS[match[1]]
        terms[key] = {'week_one': start.isoformat(), 'closures': []}
    for match in re.finditer(r'(\d{1,2})月(\d{1,2})日校运(?:动)?会[,，]?全校停课', text):
        heading = next((value for value in reversed(matches) if value.start() < match.start()), None)
        if heading is not None:
            year = int(heading[2])
            key = str(year if heading[1] == '秋' else year - 1) + '-' + SEASONS[heading[1]]
            day = date(year, int(match[1]), int(match[2]))
            terms[key]['closures'].append({'date': day.isoformat(), 'title': '校运动会（全校停课）'})
    if not terms:
        raise ValueError('校历没有可确认的学期起始日期，请手动填写。')
    return terms


class SchoolCalendar:
    def __init__(self, context, source):
        self.context, self.source, self.lock = context, source, threading.Lock()

    def saved(self, metadata):
        key = term_key(metadata)
        return self.context.store.read('school-calendar:' + key[:4], {}) if key else {}

    def due(self, metadata):
        saved = self.saved(metadata)
        checked = saved.get('checked_at')
        return not checked or datetime.now(timezone.utc) - datetime.fromisoformat(checked) > timedelta(days=7)

    def refresh(self, metadata):
        key = term_key(metadata)
        if key is None:
            raise HTTPException(409, '请先同步教务课表，再读取本学年校历。')
        with self.lock:
            previous = self.saved(metadata)
            checked = datetime.now(timezone.utc).isoformat()
            try:
                with httpx.Client(timeout=35, follow_redirects=False) as client:
                    def read(url, limit):
                        target = urlsplit(url)
                        if (target.scheme, target.netloc) != ('https', 'www.shanghaitech.edu.cn'):
                            raise ValueError('校历链接须属于学校官网。')
                        with client.stream('GET', url) as response:
                            response.raise_for_status()
                            chunks, size = [], 0
                            for chunk in response.iter_bytes():
                                if self.source.cancelled.is_set():
                                    raise ValueError('校历更新已取消。')
                                size += len(chunk)
                                if size > limit:
                                    raise ValueError('校历附件超过大小限制。')
                                chunks.append(chunk)
                        return b''.join(chunks)
                    listing = BeautifulSoup(read(INDEX, 512_000), 'html.parser')
                    year = key[:4] + '-' + str(int(key[:4]) + 1)
                    anchor = next((item for item in listing.select('a[href]') if year in item.get_text() and '校历' in item.get_text()), None)
                    if anchor is None:
                        raise ValueError('学校校历栏目尚未公布本学年校历。')
                    url = urljoin(INDEX, anchor['href'])
                    article = BeautifulSoup(read(url, 512_000), 'html.parser')
                    attachment = article.select_one('.wp_articlecontent [pdfsrc], .wp_articlecontent a[href$=".pdf"]')
                    if attachment is None:
                        raise ValueError('校历附件格式已变化，请手动核对。')
                    pdf_url = urljoin(url, attachment.get('pdfsrc') or attachment['href'])
                    content = read(pdf_url, 10 * 1024 * 1024)
                fingerprint = digest(content.hex())
                if fingerprint == previous.get('fingerprint'):
                    saved = {**previous, 'checked_at': checked, 'error': None}
                else:
                    reader = PdfReader(io.BytesIO(content))
                    if reader.is_encrypted or len(reader.pages) > 4:
                        raise ValueError('请使用至多 4 页且未加密的校历 PDF。')
                    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
                    if not text.strip():
                        temporary = self.context.data_dir / 'tmp'
                        temporary.mkdir(parents=True, exist_ok=True)
                        with tempfile.NamedTemporaryFile(suffix='.pdf', dir=temporary, delete=False) as file:
                            file.write(content)
                            path = Path(file.name)
                        try:
                            result = subprocess.run([windows_tool('powershell'), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                                                     windows_path(PROJECT / 'scripts' / 'read-calendar.ps1'), '-Path', windows_path(path)],
                                                    capture_output=True, text=True, encoding='utf-8', timeout=90)
                            if result.returncode:
                                raise ValueError('图片校历识别需要 Windows 中文 OCR，请手动设置日期或安装系统中文识别组件。')
                            text = '\n'.join(json.loads(result.stdout)['pages'])
                        finally:
                            path.unlink()
                    terms = parse(text)
                    if key not in terms:
                        raise ValueError('校历与当前学期不匹配，请手动核对。')
                    saved = {'terms': terms, 'url': url, 'pdf_url': pdf_url, 'fingerprint': fingerprint, 'checked_at': checked, 'error': None}
                self.context.store.write('school-calendar:' + key[:4], saved)
                return saved
            except (httpx.HTTPError, ValueError, OSError, RuntimeError, PyPdfError, subprocess.SubprocessError):
                error = '学校校历暂时无法自动识别，已保留当前日期；可在学期设置中手动填写。'
                self.context.store.write('school-calendar:' + key[:4], {**previous, 'checked_at': checked, 'error': error})
                raise HTTPException(502, error) from None
