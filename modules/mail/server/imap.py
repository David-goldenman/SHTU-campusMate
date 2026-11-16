"""Read the school inbox over IMAP without touching Coremail web sessions."""
import imaplib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from backend.services.auth import ImapUnavailable
from backend.services.campus import SourceError, identity

from .reader import BASE, presentation

FETCH_HEADERS = "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
UID_PATTERN = re.compile(r"\d+")


def uid_validity(mailbox):
    """Read the epoch returned by EXAMINE; do not assume UIDNEXT is supported."""
    _, values = mailbox.response("UIDVALIDITY")
    value = next((item.decode('ascii') for item in values or [] if isinstance(item, bytes) and item.isdigit()), None)
    if value is None:
        raise ImapUnavailable("邮箱未返回有效的邮件标识版本，已保留缓存，将稍后重试。")
    return value


def scan(mailbox):
    """Read only identifiers and flags, never headers/bodies or Seen mutations."""
    try:
        status, _ = mailbox.select('INBOX', readonly=True)
        if status != 'OK':
            raise ImapUnavailable()
        epoch = uid_validity(mailbox)
        status, data = mailbox.uid('SEARCH', None, 'ALL')
        if status != 'OK' or not isinstance(data, list) or not data:
            raise ImapUnavailable()
        all_uids = sorted({int(value) for value in (data[0] or b'').split() if value.isdigit()})
        uids = [str(value) for value in all_uids[-100:][::-1]]
        flags = {}
        if uids:
            status, data = mailbox.uid('FETCH', ','.join(uids), '(UID FLAGS)')
            if status != 'OK':
                raise ImapUnavailable()
            for item in data:
                raw = item[0] if isinstance(item, tuple) else item
                if not isinstance(raw, bytes):
                    continue
                uid, values = re.search(rb'\bUID\s+(\d+)', raw), re.search(rb'\bFLAGS\s+\(([^)]*)\)', raw, re.I)
                if uid and values:
                    # Recent is session-local and can change merely by reconnecting.
                    flags[uid[1].decode('ascii')] = sorted(flag for flag in values[1].decode('ascii', 'replace').split() if flag.casefold() != '\\recent')
        return {'uid_validity': epoch, 'total': len(all_uids), 'uids': uids,
                'flags': [[uid, flags.get(uid)] for uid in uids]}
    except (OSError, imaplib.IMAP4.error):
        raise ImapUnavailable() from None


def _uid(value):
    value = str(value or "")
    if not UID_PATTERN.fullmatch(value):
        raise SourceError("IMAP 邮件标识格式不正确。")
    return value


def _fetch(data, label):
    raw = next((item[1] for item in data if isinstance(item, tuple) and isinstance(item[1], bytes)), None)
    if raw is None:
        raise SourceError(label)
    return raw


def _header(message, name):
    value = message.get(name)
    if value is None:
        return ""
    return " ".join(str(value).split())


def _received(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))).isoformat()


def inbox(mailbox, previous):
    """Return the newest 100 INBOX messages with stable UIDs as identifiers."""
    observed = scan(mailbox)
    try:
        found = observed['uids']
        fetched = {}
        if found:
            status, data = mailbox.uid("FETCH", ",".join(found), FETCH_HEADERS)
            if status != "OK":
                raise imaplib.IMAP4.error("fetch failed")
            for item in data:
                if not isinstance(item, tuple):
                    continue
                prefix, raw = item
                uid = re.search(rb"\bUID\s+(\d+)", prefix)
                if not uid:
                    continue
                flags = re.search(rb"\bFLAGS\s+\(([^)]*)\)", prefix, re.IGNORECASE)
                fetched[uid[1].decode("ascii")] = (raw, flags[1] if flags else None)
    except (OSError, imaplib.IMAP4.error):
        raise ImapUnavailable() from None
    messages, issues = [], []
    old_epoch = previous.get('metadata', {}).get('uid_validity')
    reset = observed['uid_validity'] if old_epoch and old_epoch != observed['uid_validity'] else previous.get('metadata', {}).get('uid_reset')
    old = {item["id"]: item for item in previous.get("messages", [])} if old_epoch in (None, observed['uid_validity']) else {}
    for uid in found:
        raw, flags = fetched.get(uid, (None, None))
        if raw is None:
            issues.append("一封 IMAP 邮件无法读取，已跳过。")
            continue
        message = BytesParser(policy=policy.default).parsebytes(raw)
        received = _received(_header(message, "Date"))
        if _header(message, "Date") and received is None:
            issues.append("一封邮件的收件时间无法识别，已保留原邮件入口。")
        canonical = identity("mail", uid)
        messages.append({
            "id": canonical, "source": "mail", "source_id": uid,
            "title": _header(message, "Subject") or "（无主题）",
            "sender": _header(message, "From"),
            "received_at": received,
            "unread": (b"\\Seen" not in flags) if flags is not None else None,
            "url": BASE,
            "body_text": old.get(canonical, {}).get("body_text", ""),
            **({'uid_reset': reset} if reset else {}),
        })
    return {
        "messages": messages,
        "issues": list(dict.fromkeys(issues)),
        "metadata": {"folder": "收件箱", "limit": 100, "total": observed['total'], "transport": "imap",
                     "uid_validity": observed['uid_validity'], "imap_state": observed,
                     **({'uid_reset': reset} if reset else {})},
    }


def _text(part):
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, "replace")
    except LookupError:
        return payload.decode("utf-8", "replace")


def read_message(mailbox, uid):
    """Read one message with BODY.PEEK so IMAP flags stay unchanged."""
    uid = _uid(uid)
    try:
        status, data = mailbox.uid("FETCH", uid, "(BODY.PEEK[])")
    except (OSError, imaplib.IMAP4.error):
        raise ImapUnavailable() from None
    if status != "OK":
        raise SourceError("IMAP 未返回邮件正文。")
    message = BytesParser(policy=policy.default).parsebytes(_fetch(data, "IMAP 未返回邮件正文。"))
    parts = [part for part in message.walk() if not part.is_multipart()]
    html = next((part for part in parts if part.get_content_type() == "text/html"), None)
    plain = next((part for part in parts if part.get_content_type() == "text/plain"), None)
    content = _text(html) if html is not None else ""
    if not content.strip():
        content = _text(plain) if plain is not None else ""
    if not content.strip():
        content = "<p>（邮件没有可显示的正文）</p>"
    attachments = []
    for part in parts:
        filename = part.get_filename()
        if filename:
            payload = part.get_payload(decode=True)
            attachments.append({
                "name": filename, "size": len(payload) if isinstance(payload, bytes) else 0,
                "content_type": part.get_content_type(),
            })
    return {**presentation(content), "attachments": attachments}
