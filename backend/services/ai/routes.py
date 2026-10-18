from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, SecretStr, model_validator


class AISettings(BaseModel):
    enabled: bool | None = None
    provider: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{0,63}$')
    model: str | None = Field(default=None, min_length=1, max_length=200, pattern=r'^\S+$')
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    custom: bool | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    protocol: Literal['openai-completions', 'openai-responses', 'anthropic-messages'] | None = None
    api_key: SecretStr | None = None
    delete_key: bool = False


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    context: str | None = Field(default=None, max_length=120000)
    format: Literal["text", "json"] = "text"


class VisionSettings(BaseModel):
    enabled: bool = False
    base_url: str = Field(default='https://api.openai.com/v1', max_length=2048)
    protocol: Literal['openai-completions', 'openai-responses', 'anthropic-messages'] = 'openai-completions'
    model: str = Field(default='', max_length=200)
    supports_images: bool = False
    quality_confirmed: bool = False
    api_key: SecretStr | None = None
    delete_key: bool = False


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    context: str | None = Field(default=None, max_length=120000)
    plugins: list[str] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def check_plugins(self):
        if len(set(self.plugins)) != len(self.plugins):
            raise ValueError("每个插件只需选择一次。")
        return self


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

    @router.get('/catalog', summary='读取官方 Harness 的内置提供商和模型目录')
    def catalog():
        return service.catalog()

    @router.get('/vision/settings', summary='读取独立图片模型配置，密钥不回显')
    def vision_settings():
        return service.vision_settings()

    @router.put('/vision/settings', summary='配置图片模型及用户确认的识图能力')
    def save_vision_settings(body: VisionSettings):
        return service.save_vision_settings(body)

    @router.put("/settings", summary="设置 AI 提供商、模型与加密密钥")
    def save_settings(body: AISettings):
        return service.save_settings(body)

    @router.delete('/providers/{provider_id}', summary='删除本机保存的提供商配置和密钥')
    def delete_provider(provider_id: str):
        return service.delete_provider(provider_id)

    @router.post("/generate", summary="根据调用方提供的资料生成内容")
    def generate(body: GenerateRequest):
        return service.generate(**body.model_dump())

    @router.post("/chat", summary="处理调用方提供的对话消息")
    def chat(body: ChatRequest):
        return service.chat(**body.model_dump())

    @router.get("/plugins", summary="列出模块提供的原生 Harness 插件")
    def plugins():
        return service.harness.plugins()

    @router.post("/run", summary="通过官方 Harness 执行所选插件任务")
    def run(body: RunRequest):
        return service.run(**body.model_dump())

    return router
