from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class Message(BaseModel):
    key: str
    conversation_id: str
    sender_id: str = ''
    sent_at: datetime
    text: str
    type_code: int = 1
    source_db: str = ''
    server_id: str = '0'
    time_source: Literal['source', 'manual', 'imported'] = 'source'


class Attachment(BaseModel):
    name: str
    md5: str = ''
    size: int | None = None
