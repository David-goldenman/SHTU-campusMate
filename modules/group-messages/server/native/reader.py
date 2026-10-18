"""Read existing Hermes SQLite snapshots without modifying or re-decrypting them."""

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree.ElementTree import ParseError

import zstandard
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .models import Attachment, Message

CST = timezone(timedelta(hours=8))
TABLE = re.compile(r"Msg_[0-9a-f]{32}\Z")
PREFIX = re.compile(r"^([A-Za-z0-9_@\-]{3,128}):\n")


def read_only(path: Path) -> sqlite3.Connection:
    """Open an existing snapshot; never create a missing source database."""
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    return db


def decode(raw: str | bytes | None, compressed: str | bytes | None, flag: int) -> str:
    """Decode WCDB text, using the compressed payload when it is present."""
    if flag == 4:
        payload = compressed if isinstance(compressed, bytes) and compressed else raw
        if not isinstance(payload, bytes):
            raise ValueError("Compressed message has no binary payload")
        decompressed = zstandard.ZstdDecompressor().decompress(
            payload, max_output_size=16 * 1024 * 1024
        )
        return bytes(decompressed).decode("utf-8", "replace")
    value = raw if raw is not None else compressed
    return (
        value.decode("utf-8", "replace")
        if isinstance(value, bytes)
        else str(value or "")
    )


def read_messages(
    snapshot: Path, since: datetime, conversations: list[str]
) -> Iterator[Message]:
    """Read all message shards with stable server IDs and full, untruncated text."""
    if not conversations:
        return
    shards = sorted((snapshot / "message").glob("message_*.db"))
    shards = [p for p in shards if re.fullmatch(r"message_\d+\.db", p.name)]
    if not shards:
        raise FileNotFoundError("No decrypted message shards found")
    if since.tzinfo is None:
        raise ValueError("since must include a timezone")
    for path in shards:
        with closing(read_only(path)) as db:
            names = dict(db.execute("SELECT rowid,user_name FROM Name2Id"))
            # MD5 is WeChat's actual table addressing scheme, not a file fingerprint.
            conversation_map = {
                hashlib.md5(name.encode()).hexdigest(): name for name in names.values()
            }
            tables = [
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if TABLE.fullmatch(r[0])
            ]
            for table in tables:
                conv = conversation_map.get(table[4:], table)
                if conv not in conversations:
                    continue
                columns = {
                    row[1] for row in db.execute(f'PRAGMA table_info("{table}")')
                }
                time_source = (
                    "qjq_time_source" if "qjq_time_source" in columns else "'source'"
                )
                sql = f'SELECT local_id,server_id,local_type,real_sender_id,create_time,WCDB_CT_message_content,message_content,compress_content,{time_source} FROM "{table}" WHERE create_time>=? ORDER BY create_time,local_id'
                for (
                    lid,
                    sid,
                    typ,
                    sender,
                    ts,
                    flag,
                    raw,
                    compressed,
                    origin,
                ) in db.execute(sql, (int(since.timestamp()),)):
                    body = decode(raw, compressed, flag)
                    prefix = PREFIX.match(body) if origin == "source" else None
                    sender_id = prefix.group(1) if prefix else names.get(sender, "")
                    body = body[prefix.end() :] if prefix else body
                    identity = (
                        f"server:{sid}" if sid else f"local:{path.name}:{table}:{lid}"
                    )
                    yield Message(
                        key=f"wechat:{conv}:{identity}",
                        conversation_id=conv,
                        sender_id=sender_id,
                        sent_at=datetime.fromtimestamp(ts, CST),
                        text=body,
                        type_code=typ & 0xFFFFFFFF,
                        source_db=path.name,
                        server_id=str(sid or 0),
                        time_source=(
                            origin
                            if origin in {"source", "manual", "imported"}
                            else "imported"
                        ),
                    )


def attachment_from(message: Message) -> Attachment | None:
    """Parse only document attachments; links and image XML are not documents."""
    if message.type_code != 49 or len(message.text) > 2 * 1024 * 1024:
        return None
    try:
        root = fromstring(message.text)
    except (ParseError, DefusedXmlException):
        return None
    app = root if root.tag == "appmsg" else root.find(".//appmsg")
    if app is None or app.findtext("type") != "6":
        return None
    name = app.findtext("title", "").strip()
    if not name:
        return None
    size_text = app.findtext("appattach/totallen", "")
    md5 = app.findtext("appattach/filemd5", "") or app.findtext("md5", "")
    return Attachment(
        name=name,
        md5=md5.lower() if re.fullmatch(r"[0-9a-fA-F]{32}", md5) else "",
        size=int(size_text) if size_text.isdigit() else None,
    )
