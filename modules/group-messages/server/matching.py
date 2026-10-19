"""Local course/group-name suggestions; no chat body or model call is needed."""
import re
import unicodedata

from backend.services.campus import semester


TERM = re.compile(r'20\d{2}(?:\s*[-–/]\s*20\d{2})?\s*(?:学年)?\s*(?:秋|春|夏|fall|autumn|spring|summer)(?:季)?(?:学期)?', re.I)
NUMERIC_TERM = re.compile(r'20\d{2}-20\d{2}-[123](?!\d)')


def group_term(name):
    text = unicodedata.normalize('NFKC', name)
    found = NUMERIC_TERM.search(text) or TERM.search(text)
    return semester(re.sub(r'\s+', '', found[0])) if found else ''


def normalized_name(name):
    text = unicodedata.normalize('NFKC', name).casefold()
    text = NUMERIC_TERM.sub('', TERM.sub('', text))
    text = re.sub(r'(?<![a-z0-9])20\d{2}(?!\d)', '', text)
    text = re.sub(r'(?:微信|qq群|wechat|qq)', '', text, flags=re.I)
    text = re.sub(r'[^\w\u3400-\u9fff]|_', '', text)
    return re.sub(r'(?:课程)?(?:交流|讨论|通知|学习)?群(?:聊)?$', '', text)


def score(name, course):
    code = str(course.get('code') or '').upper()
    text = unicodedata.normalize('NFKC', name)
    if re.fullmatch(r'[A-Z]{2,}\d{2,}[A-Z]?', code):
        letters, digits = re.match(r'([A-Z]+)(.*)', code).groups()
        if re.search(r'(?<![A-Z0-9])' + letters + r'[\s_-]*' + digits + r'(?![A-Z0-9])', text, re.I):
            return 100, '课程代码一致'
    group = normalized_name(text)
    aliases = [normalized_name(value) for value in [course['title'], *course.get('aliases', [])]]
    if group and group in aliases:
        return 95, '课程名称或平台别名一致'
    if any(len(alias) >= 3 and alias in group for alias in aliases):
        return 60, '群名包含课程名称，请核对'
    return 0, ''


def suggest(group, courses, current, saved=None):
    known = {row['id']: row for row in courses}
    if saved is not None:
        if saved.get('course_id') in known:
            return {'status': 'saved', 'course_id': saved['course_id'], 'reason': '沿用已保存的关联，可自行修改', 'candidates': []}
        return {'status': 'inactive', 'course_id': '', 'reason': '已保存的关联不属于本学期，请重新选择课程', 'candidates': []}
    term = group_term(group['name'])
    years = re.findall(r'(?<![A-Za-z0-9])20\d{2}(?!\d)', group['name'])
    if term and term != current or not term and years and current[:4] not in years:
        return {'status': 'other_term', 'course_id': '', 'reason': '群名标记了其他学期', 'candidates': []}
    candidates = []
    for course in courses:
        points, reason = score(group['name'], course)
        if points:
            candidates.append({'course_id': course['id'], 'title': course['title'], 'score': points, 'reason': reason})
    candidates.sort(key=lambda row: (-row['score'], row['title'], row['course_id']))
    automatic = bool(candidates and candidates[0]['score'] >= 95 and (len(candidates) == 1 or candidates[0]['score'] > candidates[1]['score']))
    return {'status': 'automatic' if automatic else 'ambiguous' if candidates else 'unmatched',
            'course_id': candidates[0]['course_id'] if automatic else '',
            'reason': candidates[0]['reason'] if automatic else '存在可能的课程，请自行选择' if candidates else '暂未匹配，可手动关联本学期课程',
            'candidates': candidates[:5]}
