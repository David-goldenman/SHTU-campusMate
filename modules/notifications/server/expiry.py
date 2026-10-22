"""Expire activity reminders, preserving history and user read-state choices."""
from datetime import datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def proposal_window(proposal):
    event = proposal.get('event', {})
    start, end = instant(event.get('starts_at')), instant(event.get('ends_at'))
    if not start or event.get('ends_at') and (not end or end <= start):
        return None
    expiry = end or datetime.combine(start.astimezone(ZONE).date() + timedelta(days=1), time.min, ZONE)
    return {'starts_at': start.isoformat(), 'expires_at': expiry.isoformat(), 'basis': 'event_end' if end else 'event_day_end'}


def reconcile(items, now):
    changed = False
    for item in items:
        expiry = item.get('expiry') or {}
        at = instant(expiry.get('at'))
        if at and at <= now:
            if not item.get('read') and item.get('read_source') != 'manual':
                item.update(read=True, auto_read={'reason': 'event_expired', 'at': now.isoformat(), 'expires_at': at.isoformat()})
                changed = True
        elif item.get('auto_read', {}).get('reason') == 'event_expired':
            # A corrected future date or invalidated source reopens only auto-read notices.
            if item.get('read_source') != 'manual':
                item['read'] = False
                item.pop('auto_read', None)
                changed = True
    return changed


def update_windows(items, mail, proposals, mail_available, proposals_available):
    changed = False
    for item in items:
        if re.search(r'作业|待提交|未提交|补交|补签|待完成|成绩|评分|批改|反馈|问卷|调查|申请|缴费|付款|\b(?:assignment|homework|feedback|survey|grades?|grading)\b', item.get('title', '') + '\n' + item.get('summary', ''), re.I):
            if item.get('expiry'):
                item['expiry'] = None
                changed = True
            continue
        sources = item.get('citations', [])
        ids = [row.get('id', '').removeprefix('messages:') for row in sources]
        candidate, authoritative = None, False
        if ids and all(row.get('source') == 'mail' or identity.startswith('mail:') for row, identity in zip(sources, ids)):
            authoritative = mail_available and all(identity in mail for identity in ids)
            if authoritative:
                windows = [mail[identity].get('event_window') for identity in ids]
                if all(window and instant(window.get('expires_at')) for window in windows):
                    window = max(windows, key=lambda row: instant(row['expires_at']))
                    candidate = {'at': window['expires_at'], 'basis': window['basis'], 'source_ids': ids}
                    if len(ids) == 1 and item.get('event_at') != window.get('starts_at'):
                        item['event_at'] = window.get('starts_at')
                        changed = True
                    suffix = ' 活动时间需要核对。'
                    if len(ids) == 1 and item.get('why', '').endswith(suffix):
                        item['why'] = item['why'][:-len(suffix)] + (' 参加要求仍需核对。' if mail[ids[0]].get('needs_check') else '')
                        changed = True
        elif item.get('proposal_id'):
            authoritative = proposals_available and item['proposal_id'] in proposals
            proposal = proposals.get(item['proposal_id'], {})
            # Never resolve a notice combining an activity and other actionable sources.
            if authoritative and len(ids) == 1 and ids[0] == proposal.get('source_id'):
                window = proposal_window(proposal)
                if window:
                    candidate = {'at': window['expires_at'], 'basis': window['basis'], 'source_ids': ids}
        if authoritative and item.get('expiry') != candidate:
            item['expiry'] = candidate
            changed = True
    return changed
