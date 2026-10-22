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

        def submitted(record):
            return fresh(record) and record.get('submitted') is True and record.get('submission_status') in {'submitted', 'needs_grading', 'graded'}

        waived = any(record.get('reminder_suppressed') for record in records)
        complete = all(record.get('reminder_suppressed') or submitted(record) for record in records)
        reason = 'assignment_not_required' if waived else 'assignment_submitted'
        reopened = any(not record.get('reminder_suppressed') and (
            fresh(record) and record.get('submitted') is False and record.get('submission_status') in {'not_submitted', 'draft'}
            or item.get('auto_read', {}).get('reason') == 'assignment_not_required' and record.get('pending')) for record in records)
        if complete and not item['read']:
            item.update(read=True, auto_read={'reason': reason, 'at': now, 'assignment_ids': sorted(set(identities))})
            changed = True
        elif complete and item.get('auto_read') and item['auto_read']['reason'] != reason:
            item['auto_read']['reason'] = reason
            changed = True
        elif reopened and item.get('auto_read', {}).get('reason') in {'assignment_submitted', 'assignment_not_required'}:
            item['read'] = False
            item.pop('auto_read', None)
            changed = True
    return changed
