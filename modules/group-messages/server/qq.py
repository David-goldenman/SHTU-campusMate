"""Team message-hub QQ reader with account isolation and honest history coverage."""
import math
import re
from datetime import datetime, timezone
from .qq_client import APIError, QQClient


def connect(body, cancel):
    client = QQClient(body.base_url, body.access_token, stop=cancel)
    account = str((client.login_info() or {}).get('user_id') or '')
    if not account:
        raise APIError('qq', 'account', '未获取到 QQ 登录账号。请先在 NapCat 管理页面完成本人 QQ 登录，再回来连接。')
    rows = client.groups()
    if not isinstance(rows, list) or len(rows) > 3000:
        raise APIError('qq', 'schema', 'QQ 群列表格式不匹配。')
    groups = [{'id': str(row['group_id']), 'name': str(row.get('group_name') or row['group_id'])[:300], 'message_count': None}
              for row in rows if isinstance(row, dict) and row.get('group_id') is not None]
    return {'account': account, 'base_url': client.base_url, 'groups': groups}, {'access_token': body.access_token}


def decode_cq(raw):
    segments, position = [], 0
    for match in re.finditer(r'\[CQ:([^,\]]+)((?:,[^\]]*)?)\]', raw):
        if match.start() > position:
            segments.append({'type': 'text', 'data': {'text': raw[position:match.start()]}})
        data = {}
        for field in match.group(2).lstrip(',').split(','):
            if '=' in field:
                key, value = field.split('=', 1)
                data[key] = value.replace('&#44;', ',').replace('&#91;', '[').replace('&#93;', ']').replace('&amp;', '&')
        segments.append({'type': match.group(1), 'data': data})
        position = match.end()
    if position < len(raw):
        segments.append({'type': 'text', 'data': {'text': raw[position:]}})
    return segments


def normalize(row, account, group):
    if not isinstance(row, dict) or row.get('self_id') is not None and str(row['self_id']) != account or row.get('group_id') is not None and str(row['group_id']) != group:
        raise APIError('qq', 'account', 'QQ 返回了其他账号或群的消息，已停止接入。')
    mid = row.get('message_id') if row.get('message_id') is not None else row.get('message_seq')
    if mid is None:
        raise APIError('qq', 'schema', 'QQ 消息缺少稳定标识。')
    sender = row.get('sender') or {}
    sender_id = row.get('user_id') if row.get('user_id') is not None else sender.get('user_id')
    sent_at = None
    try:
        timestamp = float(row['time'])
        if math.isfinite(timestamp) and timestamp > 0:
            sent_at = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (KeyError, TypeError, ValueError, OSError, OverflowError):
        pass
    segments = row.get('message', [])
    if isinstance(segments, str):
        segments = decode_cq(segments)
    if not isinstance(segments, list):
        raise APIError('qq', 'schema', 'QQ 消息正文格式不匹配。')
    text, reply_to, kinds = [], '', set()
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get('data', {}), dict):
            continue
        kind, data = segment.get('type'), segment.get('data', {})
        if kind == 'text':
            text.append(str(data.get('text', ''))); kinds.add('text')
        elif kind == 'at':
            text.append('[提及成员]')
        elif kind == 'reply':
            reply_to = str(data.get('id', '')); kinds.add('reply')
        elif kind == 'file':
            text.append('[文件标题，正文未读取] ' + str(data.get('name') or '附件')); kinds.add('file_title')
        else:
            text.append('[图片、语音或其他非文字内容未读取]'); kinds.add('unread_media')
    body = '\n'.join(text)
    return {'remote_id': str(mid), 'sender_id': str(sender_id) if sender_id is not None else '',
            'sender_name': str(sender.get('card') or sender.get('nickname') or sender_id or '未知发送者')[:300],
            'sent_at': sent_at, 'text': body[:64000], 'reply_to': reply_to,
            'kind': 'reply' if reply_to else 'text' if 'text' in kinds else 'unread_media', 'truncated': len(body) > 64000}


def synchronize(config, secret, cancel):
    client = QQClient(config['base_url'], secret.get('access_token', ''), stop=cancel)
    if str((client.login_info() or {}).get('user_id') or '') != config['account']:
        raise APIError('qq', 'account', 'QQ 登录账号已变化，请重新连接并选择群。')
    messages, coverage, failures = {}, dict(config.get('coverage', {})), []
    for group in config.get('selected', []):
        if cancel.is_set():
            raise APIError('qq', 'stopped', '采集已停止。')
        gid = group['id']
        old = coverage.get(gid, {})
        try:
            rows = client.group_history(gid)
            values = [normalize(row, config['account'], gid) for row in rows]
            ids = {value['remote_id'] for value in values}
            gap = len(values) >= 100 and (not old.get('last_id') or old['last_id'] not in ids)
            ordered = sorted(values, key=lambda value: value['sent_at'] or '')
            coverage[gid] = {**old, 'last_success': datetime.now(timezone.utc).isoformat(), 'last_id': ordered[-1]['remote_id'] if ordered else old.get('last_id'),
                'possible_gap': bool(old.get('possible_gap') or gap), 'window_limit': 100,
                'observed_start': min((value['sent_at'] for value in values if value['sent_at']), default=None),
                'observed_end': max((value['sent_at'] for value in values if value['sent_at']), default=None), 'error': None}
            messages[gid] = values
        except APIError as error:
            if error.category in {'auth', 'account', 'stopped'}:
                raise
            coverage[gid] = {**old, 'error': str(error)}
            failures.append(gid)
    if cancel.is_set():
        raise APIError('qq', 'stopped', '采集已停止。')
    return {'messages': messages, 'coverage': coverage, 'failed_groups': failures}
