"""Read the school inbox over IMAP without touching Coremail web sessions."""
import imaplib
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, identity

from .reader import BASE, presentation

FETCH_HEADERS = "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
UID_PATTERN = re.compile(r"\d+")


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
    try:
        status, data = mailbox.uid("SEARCH", None, "ALL")
        if status != "OK":
            raise imaplib.IMAP4.error("search failed")
        found = [value.decode("ascii", "ignore") for value in (data[0] or b"").split() if value.isdigit()]
        found = [value for value in found if UID_PATTERN.fullmatch(value)][-100:][::-1]
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
        raise LoginRequired("IMAP 连接已断开，请到设置检查邮箱连接。") from None
    messages, issues = [], []
    old = {item["id"]: item for item in previous.get("messages", [])}
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
        })
    return {
        "messages": messages,
        "issues": list(dict.fromkeys(issues)),
        "metadata": {"folder": "收件箱", "limit": 100, "total": len(found), "transport": "imap"},
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
        raise LoginRequired("IMAP 连接已断开，请到设置检查邮箱连接。") from None
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
