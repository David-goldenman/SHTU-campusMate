"""Evidence and time validation adapted from QJQ's group summary/notice parsing."""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from .models import Extraction
from .text import public_text

ZONE = ZoneInfo('Asia/Shanghai')
PROMPT = Path(__file__).with_name('instruction.md').read_text(encoding='utf-8')
ABSOLUTE = re.compile(r'(?<!\d)(?:(20\d{2})[-/年.])?(\d{1,2})[-/月.](\d{1,2})日?')
RELATIVE = re.compile(r'今天|今日|今晚|今早|明天|明日|明晚|后天')
CLOCK = re.compile(r'(?<!\d)(\d{1,2})(?:[:：](\d{2})|点(?:(半)|(\d{1,2})分?)?)(?!\d)')


def time_supported(value, quote, sent_at, *, clock=True):
    """Require the proposed date and clock in the same cited fragment; keep unknowns for review."""
    target = datetime.fromisoformat(value).astimezone(ZONE) if clock else date.fromisoformat(value)
    day = target.date() if clock else target
    anchor = datetime.fromisoformat(sent_at).astimezone(ZONE) if sent_at else None
    days = set()
    for match in ABSOLUTE.finditer(quote):
        year, month, number = match.groups()
        if not year and not anchor:
            continue
        try:
            found = date(int(year or anchor.year), int(month), int(number))
            if year or found >= anchor.date() - timedelta(days=1):
                days.add(found)
        except ValueError:
            continue
    if anchor:
        for match in RELATIVE.finditer(quote):
            days.add(anchor.date() + timedelta(days={'明天': 1, '明日': 1, '明晚': 1, '后天': 2}.get(match.group(), 0)))
        for match in re.finditer(r'(本|这|下)(?:周|星期)([一二三四五六日天])', quote):
            weekday = '一二三四五六日天'.index(match[2]) % 7
            if match[2] == '天':
                weekday = 6
            days.add(anchor.date() - timedelta(days=anchor.weekday()) + timedelta(days=weekday + (7 if match[1] == '下' else 0)))
    if day not in days:
        return False
    if not clock:
        return True
    for match in CLOCK.finditer(quote):
        hour, minute, half, point = match.groups()
        h, m = int(hour), int(minute or point or ('30' if half else '0'))
        prefix = quote[max(0, match.start()-8):match.start()]
        if re.search(r'下午|晚上|晚间|明晚|今晚', prefix) and 1 <= h < 12:
            h += 12
        if (h, m) == (target.hour, target.minute):
            return True
    return False


def prepare(batch, group, existing):
    speakers = {value: '成员' + str(index + 1) for index, value in enumerate(dict.fromkeys(row['sender_id'] for row in batch['messages']))}
    remote = {row['remote_id']: row['id'] for row in batch['messages']}
    remote.update({row['remote_id'].rsplit(':server:', 1)[-1]: row['id'] for row in batch['messages'] if ':server:' in row['remote_id']})
    messages = [{'id': row['id'], 'sent_at': row['sent_at'], 'speaker': speakers[row['sender_id']], 'kind': row['kind'],
                 'reply_to': remote.get(row.get('reply_to')),
                 'text': public_text(row['text']), 'truncated': bool(row.get('truncated')), 'new': row['id'] in batch['new_ids']}
                for row in batch['messages']]
    return {'course': group.get('course', {}), 'timezone': 'Asia/Shanghai', 'new_message_ids': batch['new_ids'], 'messages': messages,
            'existing_items': [{**{key: item.get(key) for key in ('id', 'object_key', 'kind', 'title', 'date', 'due_at', 'starts_at', 'action', 'status')}, 'summary': item['summary'][:300]} for item in existing[-40:]],
            'schema': Extraction.model_json_schema()}


def validate(payload, prepared, batch, existing):
    if isinstance(payload, str):
        payload = re.sub(r'^```(?:json)?\s*|\s*```$', '', payload.strip())
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise HTTPException(502, 'AI 未返回可核对的事项，请重试。') from error
    try:
        result = Extraction.model_validate(payload)
    except ValueError as error:
        raise HTTPException(502, 'AI 事项格式不完整，已保留旧结果。') from error
    known = {row['id']: row for row in prepared['messages']}
    original = {row['id']: row for row in batch['messages']}
    targets = {item['id']: item for item in existing}
    output = []
    for finding in result.items:
        value = finding.model_dump(mode='json')
        if finding.target_id and finding.target_id not in targets:
            raise HTTPException(502, 'AI 指向了本次范围以外的事项，未保存。')
        if finding.target_id and targets[finding.target_id]['kind'] != finding.kind:
            raise HTTPException(502, '事项类型与原记录不一致，未保存。')
        if not any(ref.message_id in batch['new_ids'] for ref in finding.citations):
            raise HTTPException(502, '每项变化必须引用本轮新增或修订消息。')
        refs = []
        for ref in finding.citations:
            row = known.get(ref.message_id)
            if row is None or not ref.quote.strip() or ref.quote not in row['text']:
                raise HTTPException(502, 'AI 引用不在本次原文中，未保存。')
            refs.append({**ref.model_dump(), 'sent_at': row['sent_at'], 'sender_id': original[row['id']]['sender_id'],
                         'sender_name': original[row['id']]['sender_name'], 'message_revision': original[row['id']]['revision']})
        fields = [key for key in ('due_at', 'starts_at', 'ends_at') if value[key]]
        verified = all(any(time_supported(value[key], ref['quote'], ref['sent_at']) for ref in refs) for key in fields)
        if value['date']:
            verified = verified and any(time_supported(value['date'], ref['quote'], ref['sent_at'], clock=False) for ref in refs)
        if value['starts_at'] and any(re.search(r'报名|申请|问卷|截止|deadline|registration', ref['quote'], re.I) for ref in refs):
            verified = False
        value.update(citations=refs, time_verified=verified, has_time=bool(fields or value['date']))
        output.append(value)
    return output


def run(context, batch, group, existing, cancel):
    prepared = prepare(batch, group, existing)
    while len(json.dumps(prepared, ensure_ascii=False)) > 115000:
        previous = next((row for row in prepared['messages'] if not row['new']), None)
        if previous is None:
            raise HTTPException(409, '本批正文过长，请缩小读取范围后重试。')
        prepared['messages'].remove(previous)
    reply = context.ai.run(prompt=PROMPT, context=json.dumps(prepared, ensure_ascii=False), plugins=[context.id], cancel_event=cancel)
    if not any(tool.get('name') == 'group_submit' and not tool.get('is_error') for tool in reply.get('tools', [])):
        raise HTTPException(502, 'AI 尚未提交完整的群消息整理结果，请重试。')
    return validate(reply['content'], prepared, batch, existing)
