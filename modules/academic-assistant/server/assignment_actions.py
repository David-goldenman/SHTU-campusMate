"""Conversation-bound edits through the assignment module's public API."""
import json
import re
from uuid import uuid4

from fastapi import HTTPException


async def change_handling(task, body):
    task.check()
    verbs = '恢复|重新提醒|重新列入' if body.status == 'required' else '标记|设为|设置|忽略|免交|无需.{0,5}提交|不用.{0,5}提交|不必.{0,5}提交|不用.{0,5}提醒|不再提醒'
    task.intent(body.quote, verbs)
    record = task.assignment_records.get(body.record_id)
    if not record:
        raise HTTPException(422, '请先查询作业，使用本次读取的 ID；恢复时不要使用 pending=true 筛选。')
    named = any(str(record.get(key) or '') in task.message for key in ('title', 'url') if record.get(key))
    if not named and not (len(task.assignment_records) == 1 and re.search(r'这(?:个|项|份|次)?(?:作业)?|它|该作业', task.message)):
        raise HTTPException(422, '请明确要修改的作业，避免更改同课程的其他项目。')
    if body.note and body.note not in task.message:
        raise HTTPException(422, '说明请引用用户本次原文，不要补写未经确认的原因。')
    if body.status == 'waived' and body.reason == 'team_submitted':
        evidence = re.search(r'(?:队友|组员|同组|搭档|同学)[^，,。；;\n]{0,24}(?:已(?:经)?[^，,。；;\n]{0,8}(?:提交|上交|交)|提交了|上交了|交了|交过)', task.message)
        if not evidence or re.search(r'没|未|是否|如果|还不', evidence.group()):
            raise HTTPException(422, '用户尚未明确说明队友已经提交，请核对原因。')
    signature = 'handling:' + json.dumps(body.model_dump(exclude={'quote'}), ensure_ascii=False, sort_keys=True)
    if signature in task.calendar_results:
        return task.calendar_results[signature]
    response = await task.context.api('assignments', '/handling', method='PUT', body={
        'assignment_id': body.record_id, 'status': body.status, 'reason': body.reason, 'note': body.note,
        'expected_revision': record.get('handling', {}).get('revision', ''), 'account_revision': task.owner})
    task.check()
    if response.status_code != 200:
        raise HTTPException(response.status_code, response.json().get('detail', '作业选择未保存。'))
    saved = response.json()['handling']
    change = {'applied': True, 'domain': 'assignment_handling', 'action': 'set_handling', 'record_id': body.record_id,
              'before': {'title': record['title'], **record.get('handling', {})},
              'after': {'title': record['title'], **saved}, 'local_only': True, 'affected_count': 1}
    task.assignment_records[body.record_id] = {**record, 'handling': saved}
    task.changes.append(change)
    task.emit({'type': 'change', 'change': change})
    result = {'change': change, 'items': [task.source('handling-change:' + uuid4().hex, '作业提醒选择已保存', json.dumps(change, ensure_ascii=False))]}
    task.calendar_results[signature] = result
    return result
