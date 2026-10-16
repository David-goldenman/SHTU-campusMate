from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    major: str = Field(default="", max_length=120)
    cohort_year: int | None = Field(default=None, ge=2000, le=2100)
    direction: str = Field(default="", max_length=1200)
    weekly_hours: float | None = Field(default=None, ge=0, le=168, allow_inf_nan=False)
    notes: str = Field(default="", max_length=4000)


class Remember(BaseModel):
    profile: Profile
    quote: str = Field(min_length=1, max_length=2000)


class Query(BaseModel):
    area: Literal["courses", "assignments", "timetable", "grades", "degree_plan", "notifications", "mail", "profile"]
    q: str = Field(default="", max_length=300)
    course_id: str = Field(default="", max_length=300)
    pending: bool = False
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=60)


class Search(BaseModel):
    collection: Literal["materials", "lessons", "posts"] = "materials"
    q: str = Field(default="", max_length=300)
    course_id: str = Field(default="", max_length=300)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=12, ge=1, le=30)


class Document(BaseModel):
    record_id: str = Field(min_length=1, max_length=400)
    q: str = Field(default="", max_length=300)
    page: int = Field(default=1, ge=1, le=1000)
    limit: int = Field(default=6, ge=1, le=12)


class CourseSearch(BaseModel):
    q: str = Field(default="", max_length=160)
    page: int = Field(default=1, ge=1, le=100)
    syllabus_id: int | None = Field(default=None, gt=0)


class Navigate(BaseModel):
    category: Literal["dashboard", "mail", "timetable", "courses", "assignments", "eams", "notifications", "assistant", "settings"]


class Citation(BaseModel):
    source_id: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=1, max_length=800)


class Answer(BaseModel):
    text: str = Field(min_length=1, max_length=24000)
    citations: list[Citation] = Field(default_factory=list, max_length=24)
    insufficient_context: bool = False
