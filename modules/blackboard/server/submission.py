"""Submission evidence is independent of availability, deadlines and local progress."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from fastapi import HTTPException

from backend.services.campus import SourceError, timestamp

POSITIVE = {'submitted', 'needs_grading', 'graded'}
REASONS = {
    'submitted': '已找到正式提交记录。',
    'needs_grading': '已正式提交，等待教师评分。',
    'graded': '来源已评分；0 分同样表示已有评分记录。',
    'draft': '已开始或保存草稿，尚未正式提交。',
    'not_submitted': '来源明确显示尚未提交。',
    'exempt': '来源已标记豁免，不列入需要提交的待办。',
    'unknown': '尚未取得可确认的提交记录，请重新同步或查看原站。',
}


def score_number(value):
    if value is None or isinstance(value, bool) or not str(value).strip():
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def state(status, evidence, **extra):
    return {'submitted': True if status in POSITIVE else False if status in {'draft', 'not_submitted'} else None,
            'submission_status': status, 'submission_evidence': evidence, 'submission_reason': REASONS[status],
            'exempt': status == 'exempt', 'submission_stale': False, **extra}


def activity(html):
    tree = BeautifulSoup(html, 'html.parser')
    if tree.select_one('#grades_wrapper') is None:
        raise SourceError('Blackboard 成绩页面结构已变化。')
    result = {}
    for row in tree.select('#grades_wrapper .sortable_item_row[id]'):
        if not row['id'].isdigit():
            continue
        classes = row.get('class', [])
        # Assignment titles may themselves contain words such as "not submitted".
        status_nodes = row.select('.activity, .gradeStatus, .activityType')
        text = ' '.join(node.get_text(' ', strip=True) for node in status_nodes).casefold()
        text += ' ' + ' '.join(node.get('alt', '') for node in row.select('.gradeStatus img')).casefold()
        if any(word in text for word in ('exempt', '豁免', '免除')):
            status = 'exempt'
        elif any(word in text for word in ('needs grading', '需要评分', '待评分')):
            status = 'needs_grading'
        elif 'graded_item_row' in classes:
            status = 'graded'
        elif 'submitted_item_row' in classes:
            status = 'submitted'
        elif any(word in text for word in ('draft', 'in progress', '草稿', '进行中')):
            status = 'draft'
        elif any(word in text for word in ('no submission', 'not submitted', '未提交', '未尝试')):
            status = 'not_submitted'
        else:
            status = 'unknown'
        value = state(status, 'activity')
        if status == 'exempt' and any(name in classes for name in ('submitted_item_row', 'graded_item_row')):
            value['submitted'] = True
        result['_' + row['id'] + '_1'] = value
    return result


def history_time(text):
    if ':' not in text:
        return None
    value = timestamp(text)
    if value:
        return value
    match = re.fullmatch(r'\s*(\d{2}|\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?\s*(上午|下午|AM|PM)?\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*', text, re.I)
    if not match:
        return None
    year, month, day, marker, hour, minute, second = match.groups()
    year, hour = int(year), int(hour)
    if marker:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if marker.upper() in {'下午', 'PM'} else 0)
    try:
        return datetime(year + 2000 if year < 100 else year, int(month), int(day), hour,
                        int(minute), int(second or 0), tzinfo=ZoneInfo('Asia/Shanghai')).isoformat()
    except ValueError:
        return None


def submission_history(html):
    tree = BeautifulSoup(html, 'html.parser')
    title, attempt = tree.select_one('#pageTitleText'), tree.select_one('#currentAttempt')
    extra = {}
    for label in tree.select('#assignmentInfo h3'):
        if label.get_text(' ', strip=True).casefold().rstrip(':：') in {'截止日期', 'due date'}:
            value = label.find_next_sibling('p')
            due = history_time(value.get_text(' ', strip=True)) if value else None
            if due:
                extra.update(due_at=due, due_at_evidence='submission_history')
    possible = tree.select_one('#currentAttempt_pointsPossible')
    maximum = score_number(possible.get_text(strip=True).lstrip('/')) if possible else None
    if maximum is not None:
        extra['max_score'] = maximum
    if title and attempt and title.get_text(' ', strip=True).casefold().startswith(('复查提交历史记录', 'review submission history')):
        header = attempt.select_one('.attemptHeader')
        if header and any(word in header.get_text(' ', strip=True).casefold() for word in ('草稿', 'draft', '进行中', 'in progress')):
            return state('draft', 'submission_history', **extra)
        date, submission = attempt.select_one('.dateStamp'), attempt.select_one('#currentAttempt_submission')
        if date and re.search(r'\d', date.get_text(strip=True)) and submission:
            for label in submission.select('h4'):
                label.decompose()
            if submission.get_text(' ', strip=True):
                score_tag = attempt.select_one('#currentAttempt_grade')
                score = score_number(score_tag.get('value')) if score_tag else None
                return state('graded' if score is not None else 'submitted', 'submission_history',
                             submitted_at=history_time(date.get_text(' ', strip=True)),
                             **({'score': score} if score is not None else {}), **extra)
    if title and title.get_text(' ', strip=True).casefold().startswith(('上载作业', '上传作业', 'upload assignment')) and tree.select_one('form#uploadAssignmentFormId'):
        return state('not_submitted', 'submission_history', **extra)
    raise SourceError('Blackboard 作业提交历史无法确认。')


def decide(grade, activity_value, load_history, previous, checked_at):
    display = grade.get('displayGrade') if isinstance(grade.get('displayGrade'), dict) else {}
    score = score_number(display.get('score'))
    activity_value = activity_value or state('unknown', 'unavailable')
    status = grade.get('status') if isinstance(grade.get('status'), str) else None
    negative = status in {'NotAttempted', 'NotSubmitted'} or activity_value['submission_status'] == 'not_submitted'
    if grade.get('exempt') is True or activity_value['submission_status'] == 'exempt':
        result = state('exempt', 'gradebook' if grade.get('exempt') is True else 'activity')
        if score is not None or status in {'Graded', 'NeedsGrading'} or activity_value['submitted'] is True:
            result['submitted'] = True
    elif status == 'NeedsGrading':
        result = state('needs_grading', 'gradebook')
    elif (score is not None and not negative) or status == 'Graded':
        result = state('graded', 'gradebook')
    elif activity_value['submission_status'] in POSITIVE:
        result = activity_value
    else:
        result = (state('unknown', 'unavailable', submission_reason='成绩与提交记录不一致，需要核对提交历史。') if score is not None and negative else
                  state('draft', 'gradebook') if status == 'InProgress' else
                  state('not_submitted', 'gradebook') if status in {'NotAttempted', 'NotSubmitted'} else activity_value)
        if load_history is not None and result['submission_status'] != 'not_submitted':
            try:
                history = submission_history(load_history())
                # An empty upload form cannot disprove a separately observed saved draft.
                if result['submission_status'] != 'draft' or history['submission_status'] != 'not_submitted':
                    result = history
            except HTTPException:
                if result['submission_status'] == 'unknown':
                    result = state('unknown', 'unavailable')
    if result['submission_status'] == 'unknown' and (type(previous.get('submitted')) is bool or previous.get('exempt') is True):
        preserved = {key: value for key, value in previous.items()
                     if key.startswith('submission_') or key in {'submitted', 'submitted_at', 'checked_at', 'exempt', 'due_at', 'due_at_evidence', 'score', 'max_score'}}
        fallback = previous.get('submission_status') or ('exempt' if previous.get('exempt') else 'submitted' if previous.get('submitted') else 'not_submitted')
        return {**state(fallback, 'cached'), **preserved, 'submission_evidence': 'cached',
                'submission_stale': True, 'submission_reason': '本次无法核实提交情况，保留上次记录；请重新同步或查看原站。'}
    return {**result, 'checked_at': checked_at}
