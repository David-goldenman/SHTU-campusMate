"""ELRC catalog extraction from QJQ, using the host's authenticated client."""
import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.services.auth import LoginRequired

BASE = "https://elrc.shanghaitech.edu.cn"
COURSE_LIST = "/learn/v1/learningsituation/teaching/course/get/participated/courses/list"
SEMESTERS = "/learn/v1/dropdownbox/semester/manage/current"

class ELRCError(RuntimeError):
    """A user-actionable source error, without cookies or response bodies."""


class SourceSnippet(BaseModel):
    """A citable transcript excerpt with its original timeline."""

    source_id: str
    course: str
    course_id: str = ""
    course_name: str = ""
    semester: str = ""
    semester_id: str = ""
    week: str
    text: str
    start_seconds: float
    end_seconds: float
    cache_updated_at: str
    lesson_id: str = ""
    lesson_label: str = ""
    source_kind: str = "transcript"
    source_url: str = ""


def safe_component(value: str) -> str:
    """Restrict course/week tokens before using them in cache filenames."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Invalid course/week identifier")
    return value


def query_tokens(query: str) -> set[str]:
    """Use lexical Chinese bigrams so ordinary questions can find short ASR phrases."""
    tokens = set(re.findall(r"[a-z0-9_]{2,}", query.casefold()))
    stop = {
        "什么",
        "怎么",
        "如何",
        "解释",
        "说明",
        "请问",
        "一下",
        "老师",
        "课程",
        "这个",
        "那个",
        "为什么",
        "么用",
        "有什",
        "是什",
        "的作",
        "作用",
    }
    for run in re.findall(r"[\u4e00-\u9fff]+", query):
        tokens.update(
            run[i : i + 2] for i in range(len(run) - 1) if run[i : i + 2] not in stop
        )
    return tokens


class ELRC:
    def __init__(self, cache_root: Path, client=None):
        self.cache_root = cache_root
        self.client = client

    async def fetch(self, path, params=None, body=None):
        allowed = {
            COURSE_LIST, SEMESTERS,
            "/learn/v1/teaching/course/get/course/details",
            "/learn/v1/homepage/chapter/info",
            "/learn/v1/course/video/review/1",
            "/learn/v1/course/recording/video/info",
            "/rman/v1/intelligent/select/knowledge/summary",
            "/rman/v1/smart/voice/select",
        }
        if path not in allowed:
            raise ValueError("Unsupported ELRC endpoint")
        if self.client is None:
            raise ELRCError("请在设置中登录学校账号，并检查虚拟教学社区的连接状态。")
        token = next((cookie.value for cookie in self.client.cookies.jar
                      if cookie.name == "CsrfToken" and
                      "elrc.shanghaitech.edu.cn".endswith(cookie.domain.lstrip("."))), "")
        # Called within a synchronous FastAPI request worker, not the host event loop.
        response = self.client.request(
            "POST" if body is not None else "GET", BASE + path,
            params=params, json=body, headers={"CsrfToken": token} if token else {},
            follow_redirects=False, timeout=30,
        )
        if response.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise LoginRequired("ELRC 登录或课程权限失效，请在设置中重新连接。")
        response.raise_for_status()
        try:
            value = response.json()
        except ValueError:
            raise ELRCError("ELRC 未返回课程数据，请检查登录状态。") from None
        if not isinstance(value, dict):
            raise ELRCError("ELRC 返回格式已变化。")
        code = str(value.get("code", value.get("status", "200")))
        if code in {"401", "403"}:
            raise LoginRequired("ELRC 登录失效，请在设置中重新连接。")
        if value.get("success") is False or value.get("errorCode", "success") != "success" or code not in {"0", "200", "0000"}:
            raise ELRCError("ELRC 拒绝读取，请检查课程访问权限。")
        return value

    def _save_json(self, name: str, value: object) -> None:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        path = self.cache_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp-" + uuid.uuid4().hex)
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    async def discover_courses(self, semester: str = "current") -> list[dict[str, Any]]:
        """Refresh the catalog and default to the school's authoritative current term."""
        academic = await self.fetch(SEMESTERS)
        data = academic.get("data")
        current = data.get("currentSemester") if isinstance(data, dict) else None
        rows = data.get("semesterDataList") if isinstance(data, dict) else None
        if not isinstance(current, dict) or not isinstance(rows, list):
            raise ELRCError("Academic semester information unavailable")
        terms = [
            {
                "id": str(item.get("showSemester") or ""),
                "name": str(item.get("name") or ""),
            }
            for item in rows
            if isinstance(item, dict) and item.get("showSemester") and item.get("name")
        ]
        current_term = next(
            (term for term in terms if term["id"] == str(current.get("showSemester"))),
            None,
        )
        if current_term is None:
            raise ELRCError("Current academic semester is not identifiable")
        terms_by_name = {term["name"]: term for term in terms}
        terms_by_id = {term["id"]: term for term in terms}
        courses: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(1, 101):
            payload = await self.fetch(
                COURSE_LIST,
                params={"pageIndex": str(page), "pageSize": "50", "courseType": "-1"},
            )
            data = payload.get("data")
            records = data.get("results") if isinstance(data, dict) else None
            if not isinstance(records, list):
                raise ELRCError("Unexpected course discovery response")
            added = 0
            for item in records:
                record = item.get("entityData") if isinstance(item, dict) else None
                if not isinstance(record, dict):
                    raise ELRCError("Unexpected course record structure")
                identifier = str(record.get("contentId_") or "")
                if not identifier or identifier in seen:
                    continue
                safe_component(identifier)
                seen.add(identifier)
                term_ids: list[str] = []
                labels = record.get("semester_list")
                labels = labels if isinstance(labels, list) else []
                for label in [
                    record.get("semester_show_name"),
                    record.get("semester_teaching_courses"),
                    *labels,
                ]:
                    term = terms_by_id.get(str(label)) or terms_by_name.get(str(label))
                    if term and term["id"] not in term_ids:
                        term_ids.append(term["id"])
                courses.append(
                    {
                        "id": identifier,
                        "code": str(record.get("courseNumber") or ""),
                        "name": str(record.get("name_") or record.get("name") or ""),
                        "semester": "、".join(
                            terms_by_id[key]["name"] for key in term_ids
                        ),
                        "semester_id": term_ids[0] if term_ids else "",
                        "semester_ids": term_ids,
                    }
                )
                added += 1
            if len(records) < 50:
                break
            if not added:
                raise ELRCError("ELRC 课程分页未前进，保留已有目录。")
        else:
            raise ELRCError("ELRC 课程目录超过分页上限，保留已有目录。")
        await asyncio.to_thread(self._save_json, "discovered-courses.json", courses)
        await asyncio.to_thread(
            self._save_json,
            "semesters.json",
            {
                "current": current_term,
                "items": terms,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        selected_courses: list[dict[str, Any]] = self.catalog(semester)["courses"]
        return selected_courses

    def catalog(self, semester="current"):
        def read(name, default):
            path = self.cache_root / name
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

        terms = read("semesters.json", {"current": None, "items": []})
        current = terms.get("current")
        selected = current["id"] if semester == "current" and current else semester
        if semester not in {"current", "all"} and not any(item["id"] == semester for item in terms["items"]):
            raise ValueError("Unknown academic semester")
        records = read("discovered-courses.json", [])
        courses = []
        for course in records:
            if selected != "all" and selected not in course.get("semester_ids", []):
                continue
            path = self.cache_root / "library" / safe_component(course["id"]) / "manifest.json"
            content = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            lessons = content.get("lessons", [])
            courses.append({**course, "content_status": content.get("status", "not_synced"),
                            "lesson_count": len(lessons),
                            "transcript_count": sum(bool(item.get("segments")) for item in lessons),
                            "summary_count": sum(bool(item.get("chapters")) for item in lessons),
                            "material_count": len(content.get("materials", [])),
                            "content_updated_at": content.get("updated_at")})
        courses.sort(key=lambda item: (item.get("code", ""), item.get("name", ""), item["id"]))
        return {"current_semester": current, "semesters": terms["items"],
                "selected_semester": selected, "courses": courses,
                "total_count": len(records), "updated_at": terms.get("updated_at")}
