import json
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from fastapi import HTTPException

from backend.services.campus import SourceError, course, identity, plain, timestamp
from backend.services.campus.data import digest

BASE = "https://www.gradescope.com"
HOSTS = ["www.gradescope.com", "production-gradescope-uploads.s3-us-west-2.amazonaws.com"]


def courses(html):
    tree = BeautifulSoup(html, "html.parser")
    wrapper = tree.select_one("#account-show")
    if wrapper is None:
        raise SourceError("Gradescope 课程页面结构已变化。")
    if not wrapper.select("a.courseBox[href]") and wrapper.select('a[href*="/courses/"]'):
        raise SourceError("Gradescope 课程卡片结构已变化。")
    result = []
    for card in wrapper.select("a.courseBox[href]"):
        match = re.fullmatch(r"/courses/(\d+)/?", urlsplit(card["href"]).path)
        if not match:
            continue
        term = card.find_previous(class_="courseList--term")
        name, code = card.select_one(".courseBox--name"), card.select_one(".courseBox--shortname")
        result.append(course("gradescope", match[1], name.get_text(" ", strip=True) if name else card.get_text(" ", strip=True), code.get_text(strip=True) if code else "", term.get_text(" ", strip=True) if term else "", BASE + "/courses/" + match[1], status="active"))
    return result


def assignments(html, course_id, issues):
    table = BeautifulSoup(html, "html.parser").select_one("#assignments-student-table")
    if table is None:
        raise SourceError("Gradescope 作业列表未返回，请稍后重试。")
    result = []
    for row in table.select("tbody tr"):
        primary = row.select_one(".table--primaryLink")
        if primary is None or not primary.get_text(strip=True):
            issues.append("一条作业缺少标题，未加入列表。")
            continue
        title = primary.get_text(" ", strip=True)
        anchor, button = primary.select_one("a[href]"), primary.select_one("button[data-assignment-id]")
        match = re.search(r"/assignments/(\d+)", anchor["href"]) if anchor else None
        value = str(button["data-assignment-id"]) if button else match[1] if match else None
        if value is not None and not value.isdigit():
            issues.append("一条作业的标识格式无法识别。")
            continue
        status_tag, score_tag = row.select_one(".submissionStatus"), row.select_one(".submissionStatus--score")
        status_text = status_tag.get_text(" ", strip=True) if status_tag else ""
        score = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", score_tag.get_text() if score_tag else "")
        submitted = True if score_tag or status_text.casefold() in {"submitted", "已提交"} else False if status_text.casefold() in {"no submission", "not submitted", "未提交"} else None
        dates = row.select("time.submissionTimeChart--dueDate[datetime]")
        release = row.select_one("time.submissionTimeChart--releaseDate[datetime]")
        released_at = timestamp(release["datetime"]) if release else None
        active = button is not None and not button.has_attr("disabled") and button.get("aria-disabled") != "true"
        reachable = anchor is not None or button is not None
        scheduled = not active and released_at is not None and datetime.fromisoformat(released_at) > datetime.now(timezone.utc)
        availability = "open" if active else "scheduled" if scheduled else "closed" if button is not None and not active else "unknown"
        raw_url = urljoin(BASE, anchor["href"]) if anchor else f"{BASE}/courses/{course_id}/assignments/{value}/submissions/new" if button else f"{BASE}/courses/{course_id}"
        if urlsplit(raw_url).netloc != "www.gradescope.com":
            raise SourceError("Gradescope 作业链接不属于当前平台。")
        result.append({"id": identity("gradescope", f"{course_id}:{value or digest(title + str(released_at))}"), "source": "gradescope", "source_id": value, "source_course_id": str(course_id), "course_id": identity("gradescope", course_id), "title": title, "url": raw_url, "submitted": submitted, "status": "graded" if score_tag else "submitted" if submitted is True else "not_submitted" if submitted is False else "unknown", "due_at": timestamp(dates[-1]["datetime"]) if dates else None, "release_at": released_at, "score": float(score[1]) if score else None, "max_score": float(score[2]) if score else None, "availability": availability, "actionable": True if active else False if not reachable or scheduled or button is not None else None, "has_statement": None})
    return result


def props(html):
    node = BeautifulSoup(html, "html.parser").select_one('[data-react-class="AssignmentSubmissionViewer"]')
    if node is None:
        return None
    try:
        data = json.loads(node.get("data-react-props", ""))
    except ValueError:
        raise SourceError("Gradescope 作业详情 JSON 无法读取。") from None
    if not isinstance(data, dict) or not isinstance(data.get("assignment"), dict):
        raise SourceError("Gradescope 作业详情缺少结构信息。")
    return data


def enrich(item, html):
    data = props(html)
    if data is None:
        return {**item, "materials": [], "detail_available": False}
    assignment = data["assignment"]
    if assignment.get("template_url") is not None and not isinstance(assignment["template_url"], str):
        raise SourceError("Gradescope 题目文件地址格式不正确。")
    allowed = assignment.get("submission_allowed")
    allowed = allowed if type(allowed) is bool else None
    if data.get("inactive") is True:
        allowed = False
    result = {**item, "detail_available": True, "has_statement": bool(assignment.get("template_url") or data.get("questions")), "submission_format": assignment.get("submission_format"), "materials": []}
    if allowed is not None:
        result.update(actionable=allowed, availability="open" if allowed else "closed")
    questions = data.get("questions")
    if isinstance(questions, list):
        result["body_text"] = "\n".join(plain(question.get("content") or question.get("text") or question.get("question")) for question in questions if isinstance(question, dict))
    if assignment.get("template_url"):
        filename = unquote(urlsplit(assignment["template_url"]).path.rsplit("/", 1)[-1]) or "statement.pdf"
        result["materials"].append({"id": item["id"] + ":statement", "source": "gradescope", "course_id": item["course_id"], "assignment_id": item["id"], "title": filename, "type": "file", "path": [item["title"], filename], "url": item["url"], "download_url": "/api/v1/modules/gradescope/file?" + urlencode({"course_id": item["source_course_id"], "assignment_id": item["source_id"]})})
    return result


def detail(remote, course_id, assignment_id, item=None):
    if item is None:
        item = next((value for value in assignments(remote.html(f"{BASE}/courses/{course_id}"), course_id, []) if value["source_id"] == str(assignment_id)), None)
    if item is None:
        raise HTTPException(404, "该作业当前没有可访问入口。")
    path = urlsplit(item["url"]).path
    if not path.startswith(f"/courses/{course_id}/assignments/{assignment_id}/"):
        raise HTTPException(404, "该作业当前没有可访问入口。")
    html = remote.html(item["url"])
    return enrich(item, html), props(html)


def fetch(remote, previous):
    result = {"courses": courses(remote.html(BASE + "/account")), "assignments": [], "materials": [], "issues": [], "metadata": {"scope": "all_visible_courses", "availability": "submission_controls"}}
    for item in result["courses"]:
        try:
            values = assignments(remote.html(item["url"]), item["source_id"], result["issues"])
        except HTTPException:
            result["issues"].append(item["title"] + " 的作业列表暂时不可读，保留上次数据。")
            for kind in ("assignments", "materials"):
                result[kind].extend({**old, "stale": True} for old in previous.get(kind, []) if old.get("course_id") == item["id"])
            continue
        for value in values:
            if value["source_id"]:
                try:
                    value, _ = detail(remote, item["source_id"], value["source_id"], value)
                except HTTPException:
                    result["issues"].append(value["title"] + " 的详情暂时不可读，保留列表状态。")
            result["materials"].extend(value.pop("materials", []))
            result["assignments"].append(value)
    return result
