import re

from backend.services.campus import SourceError
from .reader import BASE, number, read, soup_of

COURSE_INDEX = BASE + '/eams/courseSearchOther.action'
COURSE_SEARCH = BASE + '/eams/courseSearchOther!search.action'


def courses(page):
    tree = soup_of(page)
    table = tree.select_one('table.gridtable')
    if table is None:
        raise SourceError('教务课程查询没有返回课程列表，请稍后重试。')
    heads = [cell.get_text(' ', strip=True) for cell in table.find('tr').find_all(['th', 'td'], recursive=False)]
    if not {'代码', '名称', '学分'} <= set(heads):
        raise SourceError('教务课程目录表头已变化，请检查接口。')
    items = []
    for row in table.select('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) != len(heads):
            continue
        values = {head: ' '.join(cell.get_text(' ', strip=True).split()) for head, cell in zip(heads, cells)}
        if not values['代码'] or not values['名称']:
            continue
        link = row.select_one('a[href*="courseSearchOther!info.action"]')
        match = re.search(r'syllabusIds=(\d+)', link['href']) if link else None
        items.append({'id': 'eams:catalog:' + values['代码'], 'code': values['代码'], 'title': values['名称'],
                      'english_title': values.get('英文名', ''), 'credits': number(values['学分']), 'hours': number(values.get('总课时', '')),
                      'weeks': number(values.get('周数', '')), 'weekly_hours': number(values.get('周课时', '')),
                      'education': values.get('学历层次', ''), 'department': values.get('建议开课院系', ''), 'coordinator': values.get('负责人', ''),
                      'teachers': values.get('授课教师', ''), 'syllabus_id': int(match[1]) if match else None,
                      'url': BASE + '/eams/courseSearchOther!info.action?syllabusIds=' + match[1] if match else COURSE_INDEX})
    paging = re.search(r'\.pageInfo\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', page)
    if not paging:
        raise SourceError('教务课程目录缺少分页信息。')
    page_no, size, total = map(int, paging.groups())
    return {'items': items, 'page': page_no, 'page_size': size, 'total': total, 'scope': 'course_catalog',
            'notice': '课程目录及教学大纲；学期实际开课与选课要求以学校公布为准。'}


def search(remote, query, page):
    entry = soup_of(read(remote, 'GET', COURSE_INDEX))
    form = entry.select_one('form[action*="courseSearchOther!search.action"]')
    if form is None:
        raise SourceError('教务没有返回课程查询表单。')
    values = {node['name']: node.get('value', '') for node in entry.select('input[type=hidden][name]')}
    code = bool(re.fullmatch(r'[A-Za-z]{2,}\d+[A-Za-z]?(?:\.\d+)?', query))
    values.update({'course.code': query if code else '', 'course.name': '' if code else query, 'pageNo': str(page), 'pageSize': '20'})
    return courses(read(remote, 'POST', COURSE_SEARCH, data=values, headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': COURSE_INDEX}))


def syllabus(remote, syllabus_id):
    read(remote, 'GET', COURSE_INDEX)
    url = BASE + '/eams/courseSearchOther!info.action?syllabusIds=' + str(syllabus_id)
    tree = soup_of(read(remote, 'GET', url, headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': COURSE_INDEX}))
    for node in tree.select('script, style, nav'):
        node.decompose()
    body = tree.select_one('body') or tree
    text = body.get_text('\n', strip=True)
    if not text or not any(marker in text for marker in ('课程代码', '课程简介', '课程大纲', '课程名称')):
        raise SourceError('教务没有返回该课程的教学大纲。')
    return {'id': 'eams:syllabus:' + str(syllabus_id), 'title': '课程教学大纲 ' + str(syllabus_id), 'text': text[:24000], 'url': url,
            'scope': 'course_syllabus', 'truncated': len(text) > 24000}
