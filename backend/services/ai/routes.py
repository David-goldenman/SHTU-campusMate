from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, SecretStr, model_validator


class AISettings(BaseModel):
    enabled: bool = False
    model: Literal["deepseek-flash", "deepseek-v4-pro"] = "deepseek-flash"
    api_key: SecretStr | None = None
    delete_key: bool = False


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    context: str | None = Field(default=None, max_length=120000)
    format: Literal["text", "json"] = "text"


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=120000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)
    format: Literal["text", "json"] = "text"

    @model_validator(mode="after")
    def check_total_length(self):
        if sum(len(message.content) for message in self.messages) > 120000:
            raise ValueError("对话内容总长度不能超过 120000 字符。")
        return self


def create_router(service):
    router = APIRouter(prefix="/ai", tags=["共享 AI"])

    @router.get("/settings", summary="读取 AI 配置与密钥保存状态")
    def settings():
        return service.settings()

    @router.put("/settings", summary="设置 DeepSeek 与加密密钥")
    def save_settings(body: AISettings):
        return service.save_settings(body)

    @router.post("/generate", summary="根据调用方提供的资料生成内容")
    def generate(body: GenerateRequest):
        return service.generate(**body.model_dump())

    @router.post("/chat", summary="处理调用方提供的对话消息")
    def chat(body: ChatRequest):
        return service.chat(**body.model_dump())

    return router
