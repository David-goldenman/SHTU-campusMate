"""Resolve only notices whose citations identify confirmed assignment records."""
import re


def assignment_reminder(item):
    # Submission closes a due reminder, not a newly published grade or feedback.
    title = item.get('title', '')
    if re.search(r'评分|成绩|批改|反馈|答案|讲评|grade|feedback', title, re.I):
        return False
    return bool(re.search(r'未提交|待提交|待完成|截止|已发布|布置|提交提醒|deadline|\bdue\b|not submitted',
                          title + '\n' + item.get('summary', ''), re.I))


def reconcile(items, assignments, now):
    changed = False
    for item in items:
        if item.get('read_source') == 'manual' or not assignment_reminder(item):
            continue
        identities = [source.get('id', '').removeprefix('assignments:') for source in item.get('citations', [])]
        if not identities or any(identity not in assignments for identity in identities):
            continue
        records = [assignments[identity] for identity in identities]

        def fresh(record):
            return record.get('source_status') in {'ready', 'partial'} and not any(
                record.get(key) for key in ('needs_review', 'source_stale', 'submission_stale', 'stale'))

        complete = all(fresh(record) and record.get('submitted') is True and record.get('submission_status') in
                       {'submitted', 'needs_grading', 'graded'} for record in records)
        reopened = any(fresh(record) and record.get('submitted') is False and record.get('submission_status') in
                       {'not_submitted', 'draft'} for record in records)
        if complete and not item['read']:
            item.update(read=True, auto_read={'reason': 'assignment_submitted', 'at': now, 'assignment_ids': sorted(set(identities))})
            changed = True
        elif reopened and item.get('auto_read', {}).get('reason') == 'assignment_submitted':
            item['read'] = False
            item.pop('auto_read', None)
            changed = True
    return changed
