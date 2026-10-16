"""Discover, cache and browse ELRC lessons without manual course-ID mappings."""

import asyncio
import json
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .catalog import BASE, ELRC, ELRCError, SourceSnippet, query_tokens, safe_component

DETAIL = "/learn/v1/teaching/course/get/course/details"
CHAPTERS = "/learn/v1/homepage/chapter/info"
REVIEWS = "/learn/v1/course/video/review/1"
RECORDINGS = "/learn/v1/course/recording/video/info"
VOICE = "/rman/v1/smart/voice/select"
SUMMARY = "/rman/v1/intelligent/select/knowledge/summary"
TICKS_PER_SECOND = (
    10_000_000  # School player uses 100 ns ticks for ASR and AI chapters.
)


def now() -> str:
    """Use an unambiguous timestamp for cache freshness and progress."""
    return datetime.now(UTC).isoformat()


def seconds(value: object) -> float:
    """Convert the school's documented player units, rejecting invalid numbers."""
    try:
        result = float(str(value or 0)) / TICKS_PER_SECOND
    except ValueError as exc:
        raise ELRCError("Invalid ELRC timestamp") from exc
    if not math.isfinite(result) or result < 0:
        raise ELRCError("Invalid ELRC timestamp")
    return result


def voice_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Select the ASR metadata type explicitly; omit deleted and blank text."""
    data = payload.get("data")
    rows = data.get("data") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or not isinstance(rows, list)
        or data.get("isSuccess") is False
    ):
        raise ELRCError("Invalid ELRC transcript response")
    metadata: list[Any] = []
    for row in rows:
        if isinstance(row, dict) and row.get("type") == "model_sobey_smart_voice_":
            if not isinstance(row.get("metadata"), list):
                raise ELRCError("Invalid ELRC transcript metadata")
            metadata.extend(row["metadata"])
    result = []
    for item in metadata:
        if not isinstance(item, dict):
            raise ELRCError("Invalid ELRC transcript segment")
        if item.get("delete") in (1, "1", True):
            continue
        language = item.get("textLanguage")
        language = language if isinstance(language, dict) else {}
        text = str(
            language.get("text_source")
            or language.get("text")
            or item.get("text")
            or ""
        ).strip()
        if text:
            result.append(
                {
                    "text": text,
                    "start_seconds": seconds(item.get("_in")),
                    "end_seconds": seconds(item.get("_out")),
                }
            )
    return sorted(result, key=lambda item: item["start_seconds"])


def summary_chapters(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep the school's generated summaries separate from verbatim ASR evidence."""
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ELRCError("Invalid ELRC summary response")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ELRCError("Invalid ELRC summary chapter")
        title, text = str(row.get("chapterTitle") or ""), str(
            row.get("chapterContent") or ""
        )
        points = row.get("knowledgePoints") or []
        if not isinstance(points, list):
            raise ELRCError("Invalid ELRC knowledge points")
        if title or text:
            result.append(
                {
                    "title": title,
                    "text": text,
                    "start_seconds": seconds(row.get("inPoint")),
                    "end_seconds": seconds(row.get("outPoint")),
                    "points": [
                        str(point.get("title") or "")
                        for point in points
                        if isinstance(point, dict) and point.get("title")
                    ],
                }
            )
    return result


class ContentLibrary:
    """Keep each official course and each recording lesson in its own cache."""

    def __init__(self, elrc: ELRC) -> None:
        self.elrc = elrc

    def path(self, course_id: str, name: str = "manifest") -> Path:
        """Constrain all content paths to a course directory owned by QJQ."""
        return (
            self.elrc.cache_root
            / "library"
            / safe_component(course_id)
            / f"{safe_component(name)}.json"
        )

    def read(self, course_id: str, name: str = "manifest") -> dict[str, Any]:
        """Read an atomic cache file; an absent cache is an ordinary empty state."""
        path = self.path(course_id, name)
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(value, dict):
            raise ELRCError("Invalid ELRC content cache")
        return value

    def write(
        self, course_id: str, value: dict[str, Any], name: str = "manifest"
    ) -> None:
        """Reuse the adapter's atomic writer and never modify imported caches."""
        relative = self.path(course_id, name).relative_to(self.elrc.cache_root)
        self.path(course_id).parent.mkdir(parents=True, exist_ok=True)
        self.elrc._save_json(relative.as_posix(), value)

    def course(self, course_id: str) -> dict[str, Any]:
        """Only expose courses present in the user's discovered catalog."""
        for item in self.elrc.catalog("all")["courses"]:
            if item["id"] == course_id:
                return dict(item)
        raise ValueError("Unknown course")

    def overview(self, course_id: str) -> dict[str, Any]:
        """Describe local availability without making a school request."""
        course = self.course(course_id)
        value = self.read(course_id)
        return {
            "course": course,
            "status": value.get("status", "not_synced"),
            "updated_at": value.get("updated_at"),
            "error": value.get("error", ""),
            "lessons": value.get("lessons", []),
            "materials": value.get("materials", []),
            "source_url": self.course_url(course_id),
        }

    @staticmethod
    def course_url(course_id: str) -> str:
        """Use the school's existing course-page route, never a supplied URL."""
        return (
            BASE + "/learn/course/detail/spoc/courseWare/" + safe_component(course_id)
        )

    def lesson(
        self,
        course_id: str,
        lesson_id: str,
        *,
        offset: int = 0,
        limit: int = 100,
        query: str = "",
        at: float | None = None,
    ) -> dict[str, Any]:
        """Read a bounded transcript page with all summary chapters and source context."""
        overview = self.overview(course_id)
        lesson = next(
            (item for item in overview["lessons"] if item["id"] == lesson_id), None
        )
        if lesson is None:
            raise ValueError("Unknown lesson")
        cached = self.read(course_id, lesson_id)
        segments = [
            {**item, "index": i} for i, item in enumerate(cached.get("transcript", []))
        ]
        if query.strip():
            segments = [
                item
                for item in segments
                if query.strip().casefold() in item["text"].casefold()
            ]
        if at is not None:
            offset = next(
                (i for i, item in enumerate(segments) if item["end_seconds"] >= at),
                max(0, len(segments) - limit),
            )
        return {
            "course": overview["course"],
            "lesson": lesson,
            "transcript": segments[offset : offset + limit],
            "total": len(segments),
            "offset": offset,
            "limit": limit,
            "summary": cached.get("summary", []),
            "updated_at": cached.get("updated_at"),
            "voice_state": cached.get("voice_state", "not_synced"),
            "summary_state": cached.get("summary_state", "not_synced"),
        }

    async def review_catalog(self) -> list[dict[str, Any]]:
        """Read only the school's 'my participated recordings' listing, with paging."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, 101):
            payload = await self.elrc.fetch(
                REVIEWS,
                params={
                    "type": "1",
                    "page": str(page),
                    "size": "50",
                    "courseTime": "1",
                    "playType": "0",
                },
            )
            data = payload.get("data")
            rows = data.get("results") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise ELRCError("Invalid ELRC recording catalog")
            added = 0
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not row.get("courseId")
                    or row.get("id") is None
                ):
                    raise ELRCError("Invalid ELRC recording course")
                key = str(row["id"])
                if key not in seen:
                    seen.add(key)
                    result.append(row)
                    added += 1
            if len(rows) < 50:
                return result
            if not added:
                raise ELRCError("ELRC recording pagination did not advance")
        raise ELRCError("ELRC recording catalog exceeded the page limit")

    @staticmethod
    def materials(tree: object) -> list[dict[str, str]]:
        """Read published chapter resources without generating download credentials."""
        if not isinstance(tree, list):
            raise ELRCError("Invalid ELRC course chapter tree")
        result: list[dict[str, str]] = []

        def walk(rows: list[Any], parents: list[str], depth: int = 0) -> None:
            if depth > 30:
                raise ELRCError("ELRC chapter nesting exceeded the limit")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("info"), dict):
                    raise ELRCError("Invalid ELRC course chapter")
                info = row["info"]
                title = str(info.get("chapter_name") or "未命名资料")
                resource = info.get("chapter_describe")
                kind = info.get("resourse_type")
                if resource and kind and info.get("publish_status", 1) in (1, "1"):
                    result.append(
                        {
                            "id": str(
                                info.get("guid_") or info.get("identification") or ""
                            ),
                            "title": title,
                            "kind": str(kind),
                            "chapter": " / ".join(parents),
                        }
                    )
                children = row.get("childInfo") or []
                if not isinstance(children, list):
                    raise ELRCError("Invalid ELRC course chapter children")
                walk(children, [*parents, title], depth + 1)

        walk(tree, [])
        return result

    @staticmethod
    def recording_lessons(
        payload: dict[str, Any], review: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Use schedule IDs and actual video IDs, keeping repeated weeks distinct."""
        data = payload.get("data")
        weeks = data.get("recordingVideoInfoShows") if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(weeks, list)
            or data.get("courseId") != review["courseId"]
        ):
            raise ELRCError("Invalid ELRC recording schedule")
        lessons: dict[str, dict[str, Any]] = {}
        for week in weeks:
            if not isinstance(week, dict) or not isinstance(
                week.get("recordInfoDetailList"), list
            ):
                raise ELRCError("Invalid ELRC recording week")
            for detail in week["recordInfoDetailList"]:
                if not isinstance(detail, dict) or not isinstance(
                    detail.get("videoInfoList"), list
                ):
                    raise ELRCError("Invalid ELRC recording detail")
                for video in detail["videoInfoList"]:
                    if not isinstance(video, dict) or not video.get("videoId"):
                        raise ELRCError("Invalid ELRC recording video")
                    title = str(video.get("videoName") or "")
                    if "学生" in title:
                        continue
                    vid = safe_component(str(video["videoId"]))
                    identifier = safe_component(
                        f"{review['id']}-{video.get('scheduleId') or vid}"
                    )
                    day = str(detail.get("weekDate") or "")
                    if not day and video.get("startTime"):
                        day = (
                            datetime.fromisoformat(video["startTime"])
                            .astimezone(timezone(timedelta(hours=8)))
                            .date()
                            .isoformat()
                        )
                    if identifier not in lessons:
                        lessons[identifier] = {
                            "id": identifier,
                            "semester_id": str(review.get("showSemester") or ""),
                            "week": str(week.get("week") or ""),
                            "date": day,
                            "label": f"第 {week.get('week', '')} 周 · {day or '日期待确认'} {detail.get('weekDay') or ''} · 第 {detail.get('section', '')} 节",
                            "source_url": BASE
                            + "/learn/videoreview/"
                            + safe_component(str(review["courseId"]))
                            + "?"
                            + urlencode({"id": str(review["id"])}),
                            "streams": [],
                        }
                    streams = lessons[identifier]["streams"]
                    if not any(item["id"] == vid for item in streams):
                        streams.append({"id": vid, "name": title})
        for lesson in lessons.values():
            lesson["streams"].sort(
                key=lambda item: (
                    "教师全景" not in item["name"],
                    "屏幕" not in item["name"],
                )
            )
        return list(lessons.values())

    async def sync_lesson(
        self, course_id: str, lesson: dict[str, Any], force: bool = False
    ) -> dict[str, Any]:
        """Resume successful lesson caches; a failed refresh preserves useful content."""
        old = await asyncio.to_thread(self.read, course_id, lesson["id"])
        age = (
            (
                datetime.now(UTC) - datetime.fromisoformat(old["updated_at"])
            ).total_seconds()
            if old.get("updated_at")
            else float("inf")
        )
        if (
            not force
            and old.get("status") == "ready"
            and old.get("transcript")
            and old.get("summary")
            and age < 24 * 3600
        ):
            return self.lesson_stats(lesson, old)
        result: dict[str, Any] = {"transcript": [], "summary": [], "updated_at": now()}
        for kind, endpoint in [("voice", VOICE), ("summary", SUMMARY)]:
            key = "transcript" if kind == "voice" else "summary"
            had_error = False
            for stream in lesson["streams"]:
                try:
                    payload = await self.elrc.fetch(
                        endpoint,
                        body=(
                            {
                                "contentid": stream["id"],
                                "metadataType": "model_sobey_smart_voice_",
                            }
                            if kind == "voice"
                            else None
                        ),
                        params=(
                            {"contentId": stream["id"]} if kind == "summary" else None
                        ),
                    )
                    rows = (
                        voice_segments(payload)
                        if kind == "voice"
                        else summary_chapters(payload)
                    )
                    if rows:
                        result[key] = rows
                        result[kind + "_content_id"] = stream["id"]
                        break
                except ELRCError:
                    had_error = True
            result[kind + "_state"] = (
                "ready" if result[key] else "error" if had_error else "empty"
            )
            if not result[key] and old.get(key) and had_error:
                result[key] = old[key]
                result[kind + "_content_id"] = old.get(kind + "_content_id", "")
                result[kind + "_state"] = "stale"
        result["status"] = (
            "partial"
            if any(
                result[kind + "_state"] in {"error", "stale"}
                for kind in ("voice", "summary")
            )
            else "ready"
        )
        await asyncio.to_thread(self.write, course_id, result, lesson["id"])
        return self.lesson_stats(lesson, result)

    @staticmethod
    def lesson_stats(lesson: dict[str, Any], cached: dict[str, Any]) -> dict[str, Any]:
        """Expose counts and status in manifests while keeping large text separate."""
        return {
            **lesson,
            "status": cached.get("status", "not_synced"),
            "voice_state": cached.get("voice_state", "not_synced"),
            "summary_state": cached.get("summary_state", "not_synced"),
            "segments": len(cached.get("transcript", [])),
            "chapters": len(cached.get("summary", [])),
            "updated_at": cached.get("updated_at"),
        }

    async def sync_course(
        self,
        course: dict[str, Any],
        reviews: list[dict[str, Any]],
        progress: Callable[[str], None],
        force: bool = False,
    ) -> None:
        """Bind recording courses only through the authoritative detail.courseId."""
        cid = str(course["id"])
        payload = await self.elrc.fetch(DETAIL, params={"contentId": cid})
        detail = payload.get("data")
        if (
            not isinstance(detail, dict)
            or detail.get("contentId") != cid
            or not isinstance(detail.get("entityData"), dict)
        ):
            raise ELRCError("ELRC course identity could not be verified")
        entity = detail["entityData"]
        chapter_data = await self.elrc.fetch(
            CHAPTERS,
            params={
                "courseId": cid,
                "semester": str(entity.get("course_semester_id") or 1),
                "metadataType": "chapter_contents",
                "type": "released",
            },
        )
        material_rows = self.materials(chapter_data.get("data"))
        matching = [
            row
            for row in reviews
            if detail.get("courseId")
            and row["courseId"] == detail["courseId"]
            and row.get("showSemester") in course.get("semester_ids", [])
        ]
        lessons: list[dict[str, Any]] = []
        for review in matching:
            payload = await self.elrc.fetch(
                RECORDINGS,
                params={"courseId": review["courseId"], "id": str(review["id"])},
            )
            lessons.extend(self.recording_lessons(payload, review))
        lessons.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
        manifest: dict[str, Any] = {
            "status": "syncing",
            "lessons": [
                self.lesson_stats(item, self.read(cid, item["id"])) for item in lessons
            ],
            "materials": material_rows,
            "updated_at": now(),
            "error": "",
        }
        await asyncio.to_thread(self.write, cid, manifest)
        for index, lesson in enumerate(lessons):
            progress(lesson["label"])
            manifest["lessons"][index] = await self.sync_lesson(cid, lesson, force)
            await asyncio.to_thread(self.write, cid, manifest)
        manifest["status"] = (
            "partial"
            if any(item["status"] == "partial" for item in manifest["lessons"])
            else "ready" if lessons or material_rows else "empty"
        )
        manifest["updated_at"] = now()
        await asyncio.to_thread(self.write, cid, manifest)

    def search(
        self,
        query: str,
        identities: dict[str, dict[str, Any]],
        course_code: str | None = None,
        course_id: str | None = None,
    ) -> list[tuple[int, SourceSnippet]]:
        """Return searchable transcript and summary evidence with durable lesson IDs."""
        tokens = query_tokens(query)
        ranked = []
        for cid, course in identities.items():
            if (course_id and cid != course_id) or (
                course_code and course.get("code") != course_code
            ):
                continue
            for lesson in self.read(cid).get("lessons", []):
                cache = self.read(cid, lesson["id"])
                for kind, rows in [
                    ("transcript", cache.get("transcript", [])),
                    ("summary", cache.get("summary", [])),
                ]:
                    for index, row in enumerate(rows):
                        text = (
                            row["text"]
                            if kind == "transcript"
                            else f"{row['title']}\n{row['text']}"
                        )
                        score = 10 * int(query.casefold() in text.casefold()) + sum(
                            token in text.casefold() for token in tokens
                        )
                        if not score:
                            continue
                        snippet = SourceSnippet(
                            source_id=f"elrc:{cid}:{lesson['id']}:{kind}:{index}",
                            course=course.get("code", ""),
                            course_id=cid,
                            course_name=course.get("name", ""),
                            semester=course.get("semester", ""),
                            semester_id=course.get("semester_id", ""),
                            week=lesson["week"],
                            text=text,
                            start_seconds=row["start_seconds"],
                            end_seconds=row["end_seconds"],
                            cache_updated_at=cache["updated_at"],
                            lesson_id=lesson["id"],
                            lesson_label=lesson["label"],
                            source_kind=kind,
                            source_url=lesson["source_url"],
                        )
                        ranked.append((score, snippet))
        return ranked
