"""Read the State Council holiday arrangement when a semester starts.

Classes never meet on an announced public holiday, so the timetable drops the
lessons that fall on those days instead of leaving them for the user to cancel.
The arrangement comes from the official notice on `www.gov.cn`, is stored per
calendar year, and is reused offline until the next semester starts.  Make-up
workdays are kept for reference only: the school timetable, not the holiday
notice, decides when a course meets, so no class is invented on a workday.
"""
import re
import threading
import unicodedata
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

SEARCH = 'https://sousuo.www.gov.cn/search-gov/data'
TITLE = '国务院办公厅关于{year}年部分节假日安排的通知'
LIMIT = 512_000
ZONE = ZoneInfo('Asia/Shanghai')
PARENS = re.compile(r'[（(][^）)]*[）)]')
DAYS = re.compile(r'(?:(\d{1,2})月)?(\d{1,2})日')
HEADING = re.compile(r'[一二三四五六七八九十]{1,3}、([^：:]{2,16})[：:]')


def calendar_years(term):
    """Calendar years a term can touch; a fall term also covers the next New Year."""
    if not term:
        return []
    year = int(term[:4])
    return [year] if term.endswith(('spring', 'summer')) else [year, year + 1]


def days(sentence, year):
    """Expand ``1月1日至3日`` into single dates, keeping the carried month."""
    text = PARENS.sub('', sentence)
    tokens, month = [], None
    for match in DAYS.finditer(text):
        month = int(match[1]) if match[1] else month
        if month:
            tokens.append((month, int(match[2]), match.start(), match.end()))
    found, used = set(), set()
    for index, (month, day, _, end) in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if index not in used and re.search(r'[至到—–]', text[end:following[2]]):
            used.update({index, index + 1})
            try:
                first, last = date(year, month, day), date(year, following[0], following[1])
            except ValueError:
                continue
            # A span longer than a fortnight is a misread, not a holiday.
            if first <= last and (last - first).days <= 14:
                found.update(first + timedelta(days=offset) for offset in range((last - first).days + 1))
    for index, (month, day, _, _) in enumerate(tokens):
        if index in used:
            continue
        try:
            found.add(date(year, month, day))
        except ValueError:
            continue
    return found


def parse(text, year):
    """Return holiday and make-up workday dates from a notice page."""
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    headings = list(HEADING.finditer(text))
    holidays, workdays = {}, {}
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        for sentence in text[heading.end():end].split('。'):
            if '上班' in sentence or '补班' in sentence:
                target = workdays
            elif '放假' in sentence:
                target = holidays
            else:
                continue
            for day in days(sentence, year):
                target.setdefault(day.isoformat(), heading[1])
    if not holidays:
        raise ValueError('节假日安排通知中没有可识别的放假日期。')
    return holidays, workdays


def notice_url(payload, year):
    """Pick this year's notice out of a policy search response."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            title = re.sub(r'<[^>]+>', '', str(node.get('title') or '')).strip()
            url = node.get('url') or node.get('link')
            if title == TITLE.format(year=year) and str(url).startswith('https://www.gov.cn/'):
                found.append(str(url))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)
    if not found:
        raise ValueError(f'国务院尚未公布 {year} 年部分节假日安排。')
    return found[0]


class Holidays:
    def __init__(self, context, source):
        self.context, self.source, self.lock = context, source, threading.Lock()

    def saved(self, year):
        return self.context.store.read('holidays:' + str(year), {})

    def due(self, term):
        """True until this term has tried to read every year it touches."""
        return any(self.saved(year).get('attempted_term') != term for year in calendar_years(term))

    def view(self, term):
        saved = {year: self.saved(year) for year in calendar_years(term)}
        holidays = [item for value in saved.values() for item in value.get('holidays') or []]
        workdays = [item for value in saved.values() for item in value.get('workdays') or []]
        checked = sorted(value['checked_at'] for value in saved.values() if value.get('checked_at'))
        # A notice for a future year is published late, so only report years
        # whose arrangement should already be known.
        today = datetime.now(ZONE).year
        errors = [str(year) + ' 年：' + value['error'] for year, value in saved.items()
                  if value.get('error') and year <= today]
        return {'years': list(saved), 'items': sorted(holidays, key=lambda item: item['date']),
                'workdays': sorted(workdays, key=lambda item: item['date']),
                'checked_at': checked[-1] if checked else None,
                'due': self.due(term), 'error': '；'.join(errors) or None}

    def closures(self, term, start, end):
        """Holiday dates inside an inclusive ISO range, ordered by date."""
        found = {}
        for year in calendar_years(term):
            for item in self.saved(year).get('holidays') or []:
                if start <= item['date'] <= end:
                    found[item['date']] = item
        return [found[key] for key in sorted(found)]

    def read(self, year):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            response = client.get(SEARCH, params={'t': 'zhengcelibrary', 'q': TITLE.format(year=year),
                                                  'p': 1, 'n': 10, 'sort': 'pubtime', 'sortType': 1})
            response.raise_for_status()
            if len(response.content) > LIMIT:
                raise ValueError('节假日检索结果超过大小限制。')
            url = notice_url(response.json(), year)
            page = client.get(url)
            page.raise_for_status()
            if len(page.content) > LIMIT:
                raise ValueError('节假日通知超过大小限制。')
        article = BeautifulSoup(page.content, 'html.parser')
        node = article.select_one('.pages_content') or article.select_one('#UCAP-CONTENT') or article
        return url, parse(node.get_text('\n'), year)

    def refresh(self, term, *, force=False):
        """Read the arrangement once per semester; network errors keep classes."""
        years = calendar_years(term)
        if not years:
            return self.view(term)
        with self.lock:
            for year in years:
                previous = self.saved(year)
                if not force and previous.get('attempted_term') == term:
                    continue
                if self.source.cancelled.is_set():
                    break
                checked = datetime.now(ZONE).isoformat()
                try:
                    url, (holidays, workdays) = self.read(year)
                    saved = {'holidays': [{'date': key, 'title': value} for key, value in sorted(holidays.items())],
                             'workdays': [{'date': key, 'title': value} for key, value in sorted(workdays.items())],
                             'url': url, 'checked_at': checked, 'error': None, 'attempted_term': term}
                except ValueError as error:
                    saved = {**previous, 'checked_at': checked, 'attempted_term': term, 'error': str(error)}
                except (httpx.HTTPError, OSError, RuntimeError):
                    saved = {**previous, 'checked_at': checked, 'attempted_term': term,
                             'error': '国家节假日安排暂时无法读取，课程按已保存的日期显示；下次进入学期或更新校历后重试。'}
                self.context.store.write('holidays:' + str(year), saved)
        return self.view(term)
