"""Conservative, local text screening. Matches are leads, never routing decisions."""
import re
from datetime import date, timedelta
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

NOTICE_LIST = 'https://www.shanghaitech.edu.cn/1004/list.htm'
RELEVANT = re.compile(r'施工|封路|围挡|封闭|封锁|暂停.{0,6}(?:开放|通行)|恢复.{0,6}(?:开放|通行)|重新开放|临时.{0,6}管制|道路.{0,6}(?:维修|养护)|绕行|改道|road\s*closure|construction|reopen|detour', re.I)
REOPEN = re.compile(r'恢复.{0,6}(?:开放|通行)|重新开放|解除.{0,6}(?:封闭|管制)|reopen', re.I)
UNCERTAIN = re.compile(r'预计|计划|拟于|将于|即将|有望|尚未|暂未|未恢复|没有.{0,4}恢复|不.{0,4}恢复|待.{0,8}验收|尚不|不代表|expected|planned|not\s+reopen', re.I)
VEHICLE = re.compile(r'机动车|车辆|汽车|停车|vehicle|parking', re.I)
WALK = re.compile(r'行人|步行|人行|pedestrian|on foot', re.I)
WALK_BLOCK = re.compile(r'(?:行人|步行|人行).{0,12}(?:封闭|禁止|无法|暂停|绕行|不可)|(?:封闭|禁止|暂停).{0,10}(?:行人|步行|人行)', re.I)
WALK_OPEN = re.compile(r'(?:行人|步行|人行).{0,8}(?:不受影响|正常|可通行|无需绕行|需核实)', re.I)


def public_notice_url(url):
    value = urlsplit(url)
    return value.scheme == 'https' and value.hostname == 'www.shanghaitech.edu.cn' and value.port in {None, 443} and not value.username and not value.password


def notice_links(html, today):
    tree, result = BeautifulSoup(html, 'html.parser'), {}
    for anchor in tree.select('a[href]'):
        url = urljoin(NOTICE_LIST, anchor['href']).split('#')[0]
        match = re.fullmatch(r'/(20\d{2})/(\d{2})(\d{2})/c1004a\d+/page.htm', urlsplit(url).path)
        if not match or not public_notice_url(url):
            continue
        try:
            published = date(*map(int, match.groups()))
        except ValueError:
            continue
        if today - timedelta(days=90) <= published <= today:
            result[url] = {'source_id': url, 'url': url, 'source_date': published.isoformat(),
                           'title': (anchor.get('title') or anchor.get_text(' ', strip=True))[:160]}
    return list(result.values())[:20]


def notice_text(html):
    tree = BeautifulSoup(html, 'html.parser')
    body = tree.select_one('.wp_articlecontent')
    if body is None:
        raise ValueError('公告正文结构已变化，未解析为通行信息。')
    for node in body.select('script,style,iframe,form'):
        node.decompose()
    title = tree.select_one('h1')
    return (title.get_text(' ', strip=True)[:160] if title else ''), body.get_text('\n', strip=True)[:40000]


def screen(source, places, today):
    text = source['title'] + '\n' + source.get('text', '')
    hits = list(RELEVANT.finditer(text))
    if not hits:
        return None
    # Keep a continuous source excerpt so its wording remains auditable.
    start = max(0, hits[0].start() - 100)
    evidence = text[start:start + 700].strip()
    reopen = REOPEN.search(evidence)
    action = 'reopening' if reopen and not UNCERTAIN.search(evidence) else 'restriction'
    flags = ['自动筛选仅供核实；请确认实际位置、日期及对行人的影响。']
    if UNCERTAIN.search(evidence):
        flags.append('原文含计划、预计或否定语气，不能据此认定已恢复。')
    if VEHICLE.search(evidence) and (not WALK_BLOCK.search(evidence) or WALK_OPEN.search(evidence)):
        action = 'caution'
        flags.append('原文可能只限制机动车，尚不能认定步行封闭。')
    if action == 'restriction' and not re.search(r'封路|封闭|禁止.{0,6}通行|暂停.{0,6}(?:开放|通行)|绕行|改道|closure|detour', evidence, re.I):
        action = 'caution'
        flags.append('提及施工但未明确步行封闭，需核对实际影响。')
    locations = []
    for place in places['buildings']:
        aliases = sorted(set([place['name'], place.get('short_name', ''), *place.get('aliases', [])]), key=len, reverse=True)
        if any(len(alias) >= 2 and re.search(re.escape(alias) + (r'(?!\d)' if alias[-1:].isdigit() else ''), evidence, re.I) for alias in aliases):
            locations.append(place['id'])
    # Overlapping aliases are suggestions; the reviewer chooses the actual geometry.
    if len(locations) != 1:
        flags.append('位置不唯一或未识别，请在地图指定地点、路段或区域。')
    if not locations and not re.search(r'道路|校门|入口|出口|校园|校内|围挡|通道|路段|人行|步行|road|gate|path|pedestrian', evidence, re.I):
        return None
    found_dates = list(dict.fromkeys(re.findall(r'20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?|\d{1,2}月\d{1,2}日', evidence)))
    if not found_dates:
        flags.append('未提取到明确生效日期，请核对；发布日期不等于生效日期。')
    return {'title': source['title'][:80], 'action': action, 'evidence': evidence,
            'place_ids': locations[:15], 'date_text': found_dates[:8], 'flags': flags,
            'source': source['source'], 'source_id': source['source_id'], 'source_url': source['url'],
            'source_title': source['title'][:160], 'source_date': source.get('source_date') or today.isoformat(),
            'date_unknown': not bool(source.get('source_date'))}
