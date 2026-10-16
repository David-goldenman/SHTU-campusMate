import json
import math

from fastapi import HTTPException

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, course, identity, plain, rows, semester
from backend.services.campus.data import digest

BASE = "https://elrc.shanghaitech.edu.cn"


def api(remote, path, params=None, payload=None):
    result = remote.json("POST", BASE + path, json=payload) if payload is not None else remote.json("GET", BASE + path, params=params)
    if not isinstance(result, dict):
        raise SourceError("教学社区返回格式不正确。")
    if result.get("status") in (401, "401") or result.get("message") == "unLogin":
        raise LoginRequired("教学社区会话已到期，请重新连接 IDS。")
    if result.get("status") not in (None, 0, "0", 200, "200") or "data" not in result:
        raise SourceError("教学社区没有返回预期的数据。")
    return result["data"]


def pages(remote, path, parameters, page_name, size_name):
    seen = set()
    for page in range(1, 101):
        data = api(remote, path, {**parameters, page_name: page, size_name: 50})
        values = rows(data, "results")
        signature = digest(json.dumps(values, sort_keys=True, ensure_ascii=False))
        if values and signature in seen:
            raise SourceError("教学社区返回了重复分页，已保留缓存。")
        seen.add(signature)
        yield from values
        if len(values) < 50:
            return
        total = data.get("total") or data.get("totalCount")
        if isinstance(total, (int, float)) and page * 50 >= total:
            return
    raise SourceError("教学社区分页超过单次 100 页的读取范围。")


def chapters(values, cid, url, issues):
    result, seen = [], set()
    stack = [(node, [], 0) for node in reversed(rows(values))]
    while stack:
        node, parents, depth = stack.pop()
        if depth > 32 or len(result) >= 10000:
            raise SourceError("教学社区资料层级或数量超过读取范围。")
        info = node.get("info")
        if not isinstance(info, dict):
            issues.append("一条课程资料没有返回信息对象。")
            continue
        value = info.get("guid_") or info.get("identification")
        if value and str(value) in seen:
            issues.append("课程资料包含重复节点，已跳过。")
            continue
        if value:
            seen.add(str(value))
        title = plain(info.get("chapter_name")) or "课程资料"
        path = parents + [title]
        if value:
            result.append({"id": identity("elrc", str(cid) + ":" + str(value)), "source": "elrc", "course_id": identity("elrc", cid), "title": title, "path": path, "body_text": plain(info.get("chapter_describe")), "type": str(info.get("resourse_type") or "content"), "url": url})
        stack.extend((child, path, depth + 1) for child in reversed(rows(node.get("childInfo"))))
    return result


def fetch(remote, previous):
    result = {"courses": [], "materials": [], "lessons": [], "issues": [], "metadata": {"page_size": 50}}
    term = api(remote, "/learn/v1/dropdownbox/semester/manage/current")
    result["metadata"]["semester"] = term.get("currentSemester", {}) if isinstance(term, dict) else {}
    recording_map = {}
    for entry in pages(remote, "/learn/v1/learningsituation/teaching/course/get/participated/courses/list", {"courseType": -1}, "pageIndex", "pageSize"):
        data = entry.get("entityData")
        if not isinstance(data, dict) or not data.get("contentId_"):
            result["issues"].append("一条课程记录缺少课程标识。")
            continue
        cid = str(data["contentId_"])
        url = BASE + "/learn/course/detail/spoc/courseWare/" + cid
        item = course("elrc", cid, data.get("name_") or data.get("name") or data.get("course_name") or cid, data.get("courseNumber"), data.get("semester_show_name") or str(data.get("semester_list") or ""), url, status="active")
        result["courses"].append(item)
        try:
            details = api(remote, "/learn/v1/teaching/course/get/course/details", {"contentId": cid})
            if not isinstance(details, dict):
                raise SourceError("课程详情格式不正确。")
            if details.get("courseId"):
                recording_map[(str(details["courseId"]), item["semester"])] = item["id"]
            if data.get("course_semester_id"):
                tree = api(remote, "/learn/v1/homepage/chapter/info", {"courseId": cid, "semester": data["course_semester_id"], "metadataType": "chapter_contents", "type": "released"})
                result["materials"].extend(chapters(tree, cid, url, result["issues"]))
        except HTTPException:
            result["issues"].append(item["title"] + " 的课程资料暂时不可读，保留缓存。")
            result["materials"].extend(old for old in previous.get("materials", []) if old.get("course_id") == item["id"])
    old_lessons = {item["id"]: item for item in previous.get("lessons", [])}
    try:
        for value in pages(remote, "/learn/v1/course/video/review/1", {"type": 1, "courseTime": 1, "playType": 0}, "page", "size"):
            if not value.get("id"):
                result["issues"].append("一条录播缺少标识。")
                continue
            vid, cid = str(value["id"]), str(value.get("courseId") or "")
            canonical = identity("elrc", "recording:" + cid + ":" + vid)
            result["lessons"].append({**old_lessons.get(canonical, {}), "id": canonical, "source": "elrc", "source_id": vid, "recording_course_id": cid, "course_id": recording_map.get((cid, semester(value.get("showSemester")))), "title": plain(value.get("courseName") or value.get("name")) or "课程录播", "term": str(value.get("showSemester") or ""), "url": BASE + f"/learn/videoreview/{cid}?id={vid}"})
    except HTTPException:
        result["lessons"] = list(old_lessons.values())
        result["issues"].append("录播目录暂时不可读，保留缓存。")
    return result


def recording(remote, course_id, recording_id):
    data = api(remote, "/learn/v1/course/recording/video/info", {"courseId": course_id, "id": recording_id})
    if not isinstance(data, dict):
        raise SourceError("录播详情格式不正确。")
    lessons = []
    for week in rows(data.get("recordingVideoInfoShows")):
        for day in rows(week.get("recordInfoDetailList")):
            streams = [{"id": str(value["videoId"]), "name": str(value.get("videoName") or "录播")} for value in rows(day.get("videoInfoList")) if value.get("videoId") and "学生" not in str(value.get("videoName") or "")]
            streams.sort(key=lambda value: ("教师全景" not in value["name"], "屏幕" not in value["name"]))
            if streams:
                lessons.append({"title": f"第 {week.get('week', '?')} 周 · {day.get('weekDate', '')} · 第 {day.get('section', '?')} 节", "streams": streams})
    return {"title": plain(data.get("courseName")), "lessons": lessons}


def parse_transcript(voice, summary):
    values = voice.get("data") if isinstance(voice, dict) else voice
    lines, issues = [], []
    for group in rows(values):
        if group.get("type") != "model_sobey_smart_voice_":
            continue
        for line in rows(group.get("metadata")):
            if str(line.get("delete", "0")).lower() in {"1", "true"}:
                continue
            language = line.get("textLanguage") or {}
            if isinstance(language, str):
                try:
                    language = json.loads(language)
                except ValueError:
                    language = {}
            language = language if isinstance(language, dict) else {}
            text = plain(language.get("text_source") or language.get("text") or line.get("text"))
            if not text:
                continue
            try:
                start, end = float(line.get("_in", 0)) / 10000000, float(line.get("_out", 0)) / 10000000
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                start = end = None
                issues.append("部分转写缺少有效时间，已保留文字。")
            lines.append({"text": text, "start": start, "end": end})
    chapters = [{"title": plain(item.get("chapterTitle") or item.get("chapterName") or item.get("title")), "body_text": plain(item.get("chapterContent"))} for item in rows(summary)]
    return {"transcript": lines, "summary": chapters, "issues": list(dict.fromkeys(issues))}


def transcript(remote, stream_id):
    voice = api(remote, "/rman/v1/smart/voice/select", payload={"contentid": stream_id, "metadataType": "model_sobey_smart_voice_"})
    summary = api(remote, "/rman/v1/intelligent/select/knowledge/summary", {"contentId": stream_id})
    return parse_transcript(voice, summary)
