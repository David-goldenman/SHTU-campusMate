from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = "0.1.0"
CATEGORIES = [
    {"id": "dashboard", "label": "总览"},
    {"id": "mail", "label": "邮箱"},
    {"id": "timetable", "label": "课程表"},
    {"id": "courses", "label": "课程中心"},
    {"id": "assignments", "label": "作业管理"},
    {"id": "notifications", "label": "通知"},
    {"id": "assistant", "label": "AI助手"},
    {"id": "settings", "label": "设置"},
]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: int = Field(default=16666, ge=1024, le=65535)

    @field_validator("port")
    @classmethod
    def browser_port(cls, value):
        if value in {1719, 1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669, 6697, 10080}:
            raise ValueError("该端口被浏览器限制，请选择其他端口，例如 16666。")
        return value
