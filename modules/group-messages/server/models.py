"""UI settings and evidence-backed extraction; no platform credentials in these records."""
from typing import Literal
from datetime import date as Date
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WechatConnection(Strict):
    database_dir: str = Field(min_length=1, max_length=2000)
    pid: int = Field(gt=0)
    acknowledge_local_read: Literal[True]


class QQConnection(Strict):
    base_url: str = Field(default='http://127.0.0.1:3000', max_length=300)
    access_token: str = Field(min_length=1, max_length=4096)
    acknowledge_local_read: Literal[True]


class GroupPreference(Strict):
    id: str = Field(min_length=1, max_length=200)
    course_id: str = Field(default='', max_length=200)
    trusted_senders: list[str] = Field(default_factory=list, max_length=50)
    auto_extract: bool = False
    auto_apply: bool = False

    @model_validator(mode='after')
    def automatic(self):
        if self.auto_apply and (not self.auto_extract or not self.trusted_senders):
            raise ValueError('自动应用需要自动整理，并指定可信的老师或助教。')
        if any(not value.strip() or len(value) > 200 for value in self.trusted_senders):
            raise ValueError('请选择有效的发送者。')
        return self


class Selection(Strict):
    expected_revision: str = Field(min_length=1, max_length=100)
    groups: list[GroupPreference] = Field(default_factory=list, max_length=40)
    enabled: bool = True
    interval_seconds: Literal[20, 60, 300, 900, 1800] = 300
    history_days: Literal[7, 30] = 7
    allow_ai: bool = False
    confirm_compatible: bool = False

    @model_validator(mode='after')
    def selected(self):
        if self.enabled and not self.groups:
            raise ValueError('请先选择需要同步的群。')
        return self


class Evidence(Strict):
    message_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=1500)


class Finding(Strict):
    target_id: str = Field(default='', max_length=100)
    object_key: str = Field(min_length=1, max_length=150)
    kind: Literal['assignment', 'quiz', 'exam', 'class_change', 'activity', 'material', 'notice']
    action: Literal['announce', 'change', 'cancel', 'question', 'uncertain'] = 'announce'
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=3000)
    date: str = Field(default='', pattern=r'^(|\d{4}-\d{2}-\d{2})$')
    due_at: AwareDatetime | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    location: str = Field(default='', max_length=200)
    citations: list[Evidence] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def interval(self):
        if self.date:
            Date.fromisoformat(self.date)
        if self.ends_at and (not self.starts_at or self.ends_at <= self.starts_at):
            raise ValueError('结束时刻应晚于开始时刻。')
        if self.due_at and self.starts_at:
            raise ValueError('截止时间和活动开始时间应拆为不同事项。')
        return self


class Extraction(Strict):
    items: list[Finding] = Field(default_factory=list, max_length=30)


class Decision(Strict):
    expected_revision: str = Field(min_length=1, max_length=100)
    action: Literal['accept', 'dismiss', 'undo', 'apply']


class ExtractRequest(Strict):
    source: Literal['wechat', 'qq']
    group_id: str = Field(min_length=1, max_length=200)
    allow_ai: Literal[True]

