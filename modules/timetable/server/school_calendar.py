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
from zoneinfo import ZoneInfo

import httpx
import pypdfium2 as pdfium
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
ZONE = ZoneInfo('Asia/Shanghai')
PDF_SCALE = 2.2
BOUNDARY_DAYS = 3


def term_key(metadata):
    match = re.search(r'(20\d{2})-(20\d{2}).*?([秋春夏暑])', metadata.get('semester', ''))
    return match[1] + '-' + SEASONS[match[3]] if match else None


def parse(text):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    matches = list(re.finditer(r'([秋春暑夏])学期[（(](20\d{2})[.年/](\d{1,2})[.月/](\d{1,2})', text))
    terms = {}
    for match in matches:
        try:
            start = date(int(match[2]), int(match[3]), int(match[4]))
        except ValueError:
            continue
        if start.weekday() != 0:
            # OCR noise can turn 21 into 2 and make the weekday invalid.  Other
            # terms in the same calendar remain usable; do not discard them all.
            continue
        year = start.year if match[1] == '秋' else start.year - 1
        key = str(year) + '-' + SEASONS[match[1]]
        terms[key] = {'week_one': start.isoformat(), 'closures': []}
    for match in re.finditer(r'(\d{1,2})月(\d{1,2})日校运(?:动)?会[,，]?全校停课', text):
        heading = next((value for value in reversed(matches) if value.start() < match.start()), None)
        if heading is not None:
            year = int(heading[2])
            key = str(year if heading[1] == '秋' else year - 1) + '-' + SEASONS[heading[1]]
            if key not in terms:
                continue
            try:
                day = date(year, int(match[1]), int(match[2]))
            except ValueError:
                continue
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
        if saved.get('error') or not checked:
            return True
        try:
            checked_at = datetime.fromisoformat(checked)
        except ValueError:
            return True
        if datetime.now(timezone.utc) - checked_at > timedelta(days=7):
            return True
        # Refresh once more around the first and last teaching week so a
        # calendar published just before the semester boundary is picked up.
        key = term_key(metadata)
        term = saved.get('terms', {}).get(key) if key else None
        if not term or not term.get('week_one'):
            return False
        try:
            start = date.fromisoformat(term['week_one'])
            weeks = int(metadata.get('week_count') or 18)
            end = start + timedelta(weeks=weeks) - timedelta(days=1)
            last = checked_at.astimezone(ZONE).date()
        except (TypeError, ValueError):
            return True
        today = datetime.now(ZONE).date()
        return any(abs((today - boundary).days) <= BOUNDARY_DAYS and last < boundary
                   for boundary in (start, end))

    def directory(self, key):
        return self.context.data_dir / 'calendar' / key

    def images(self, key):
        folder = self.directory(key)
        if not folder.is_dir():
            return []
        return sorted((path for path in folder.glob('page-*.png') if path.is_file()),
                      key=lambda path: int(path.stem.split('-')[-1]))

    def render(self, content, key):
        """Cache the original PDF and rasterize every page for the web panel."""
        folder = self.directory(key)
        folder.mkdir(parents=True, exist_ok=True)
        pdf_path = folder / 'calendar.pdf'
        pdf_path.write_bytes(content)
        for path in folder.glob('page-*.png'):
            path.unlink()
        document = pdfium.PdfDocument(str(pdf_path))
        try:
            for index in range(len(document)):
                page = document[index]
                try:
                    bitmap = page.render(scale=PDF_SCALE)
                    try:
                        image = bitmap.to_pil()
                        try:
                            image.save(folder / f'page-{index + 1}.png', format='PNG', optimize=True)
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        finally:
            document.close()
        return self.images(key)

    def image(self, metadata, number=1):
        key = term_key(metadata)
        if key is None:
            raise HTTPException(409, '请先同步教务课表，再读取本学年校历。')
        folder = self.directory(key)
        path = folder / f'page-{int(number)}.png'
        with self.lock:
            if not path.is_file():
                pdf_path = folder / 'calendar.pdf'
                if not pdf_path.is_file():
                    raise HTTPException(404, '校历图片尚未缓存，请点击更新。')
                self.render(pdf_path.read_bytes(), key)
            if not path.is_file():
                raise HTTPException(404, '校历中没有这一页。')
        return path

    def view(self, metadata):
        key = term_key(metadata)
        saved = self.saved(metadata) if key else {}
        images = self.images(key) if key else []
        return {'available': bool(images), 'pages': len(images),
                'url': saved.get('url'), 'pdf_url': saved.get('pdf_url'),
                'checked_at': saved.get('checked_at'), 'error': saved.get('error'),
                'version': saved.get('fingerprint') or saved.get('checked_at'),
                'due': bool(key) and self.due(metadata)}

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
                    candidates = [item for item in listing.select('a[href]')
                                  if '校历' in item.get_text() and year in item.get_text()]
                    if not candidates:
                        # The list is newest first.  Use its first dated calendar
                        # entry even when the title format omits the academic year.
                        candidates = [item for item in listing.select('a[href]')
                                      if '校历' in item.get_text() and re.search(r'20\d{2}', item.get_text())]
                    anchor = candidates[0] if candidates else None
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
                reader = PdfReader(io.BytesIO(content))
                if reader.is_encrypted or len(reader.pages) > 4:
                    raise ValueError('请使用至多 4 页且未加密的校历 PDF。')
                if fingerprint == previous.get('fingerprint') and len(self.images(key)) == len(reader.pages):
                    saved = {**previous, 'checked_at': checked, 'error': None}
                else:
                    self.render(content, key)
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
