"""Grounded education requests through the shared AI service."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .answers import EducationAnswer

PROMPT = Path(__file__).with_name("education-system-v1.md").read_text(encoding="utf-8")
MODES = {"answer": "答疑", "hint": "分步提示", "quiz": "知识自测", "plan": "学习计划", "notice": "通知核对"}


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_id: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=4000)
    course_name: str = Field(default="", max_length=300)
    semester: str = Field(default="", max_length=100)
    lesson_label: str = Field(default="", max_length=300)
    source_kind: str = Field(default="manual", max_length=40)
    start_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    end_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)


class EducationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=8000)
    mode: Literal["answer", "hint", "quiz", "plan", "notice"] = "answer"
    sources: list[Source] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def unique_sources(self):
        if not self.question.strip():
            raise ValueError("问题不能为空。")
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("来源 ID 必须唯一。")
        return self


def build_request(body):
    return [
        {"role": "system", "content": PROMPT + "\n\n输出 JSON Schema：\n" +
         json.dumps(EducationAnswer.model_json_schema(), ensure_ascii=False)},
        {"role": "user", "content": json.dumps(body.model_dump(), ensure_ascii=False)},
    ]


def validate_answer(content, body):
    answer = EducationAnswer.model_validate(content)
    if answer.mode != body.mode:
        raise ValueError("回答模式不匹配。")
    sources = {source.source_id: source.text for source in body.sources}
    for citation in answer.citations:
        if citation.source_id not in sources or not citation.quote.strip() or citation.quote not in sources[citation.source_id]:
            raise ValueError("引用未通过原文校验。")
    return answer


def create_router(context):
    router = APIRouter()

    @router.get("/modes")
    def modes():
        return {"modes": MODES, "max_sources": 12, "max_source_chars": 4000}

    @router.post("/preview")
    def preview(body: EducationRequest):
        return {"messages": build_request(body), "source_count": len(body.sources), "calls_ai": False}

    @router.post("/answer")
    def answer(body: EducationRequest):
        result = context.ai.chat(messages=build_request(body), format="json")
        try:
            checked = validate_answer(result["content"], body)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, "AI 回答格式或引用未通过校验，请调整问题后重试。") from None
        return {"answer": checked.model_dump(), "model": result.get("model"), "usage": result.get("usage", {})}

    return router
