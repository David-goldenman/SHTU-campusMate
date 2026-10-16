import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from fastapi import HTTPException

from backend.services.campus import SourceError, course, identity, plain, timestamp
from backend.services.campus.data import digest

BASE = "https://elearning.shanghaitech.edu.cn:8443"
KINDS = {"resource/x-bb-folder": "folder", "resource/x-bb-file": "file", "resource/x-bb-assignment": "assignment", "resource/x-bb-asmt-test-link": "test", "resource/x-bb-externallink": "link"}
TERM = re.compile(r"20\d{2}(?:-20\d{2}学年)?\S*?[春夏暑秋]季?学期")


def checked(value):
    if not isinstance(value, str) or not re.fullmatch(r"_[1-9]\d*_1", value):
        raise SourceError("Blackboard 返回了无法识别的资源标识。")
    return value


def availability(value, now=None):
    if not isinstance(value, dict):
        return "unknown", None
    flag = value.get("available")
    if flag in ("No", False):
        return "closed", False
    window = value.get("adaptiveRelease") or {}
    if not isinstance(window, dict):
        return "unknown", None
    at = now or datetime.now(timezone.utc)
    for key, state, comparison in (("start", "scheduled", lambda date: at < date), ("end", "closed", lambda date: at > date)):
        if window.get(key):
            parsed = timestamp(window[key])
            if parsed is None:
                return "unknown", None
            if comparison(datetime.fromisoformat(parsed)):
                return state, False
    return ("open", True) if flag in ("Yes", True) else ("unknown", None)


def portal(html):
    tree, result = BeautifulSoup(html, "html.parser"), {}
    for module, state in (("module:_185_1", "active"), ("module:_186_1", "completed")):
        area = tree.find(id=module)
        if area is None:
            continue
        for anchor in area.select('a[href*="type=Course"]'):
            values = parse_qs(urlsplit(anchor["href"]).query)
            cid = values.get("id", [None])[0]
            if not cid:
                continue
            label = anchor.get_text(" ", strip=True)
            code = re.search(r"\b[A-Z]{2,}\d+[A-Z]?\b", label)
            term = TERM.search(label)
            result[cid] = {"status": state, "code": code[0] if code else "", "term": term[0] if term else ""}
    return result


def contents(remote, course_id, issues):
    result, seen, stack = [], set(), [(BASE + f"/learn/api/public/v1/courses/{course_id}/contents", [], 0)]
    while stack:
        url, parents, depth = stack.pop()
        if depth > 32 or len(seen) >= 10000:
            raise SourceError("Blackboard 内容层级或数量超过读取上限。")
        for node in remote.pages(url):
            if not isinstance(node.get("id"), str) or not re.fullmatch(r"_[1-9]\d*_1", node["id"]):
                issues.append("一条课程内容缺少合法标识。")
                continue
            if node["id"] in seen:
                issues.append("课程内容树包含重复或循环节点，已跳过重复项。")
                continue
            seen.add(node["id"])
            handler = node.get("contentHandler") if isinstance(node.get("contentHandler"), dict) else {}
            kind = KINDS.get(handler.get("id"), "content")
            title = plain(node.get("title")) or "课程内容"
            path = parents + [title]
            result.append({**node, "kind": kind, "path": path, "body_text": plain(node.get("body")), "title": title})
            if node.get("hasChildren") is True or node.get("hasChildren") == "true":
                stack.append((BASE + f"/learn/api/public/v1/courses/{course_id}/contents/{node['id']}/children", path, depth + 1))
    return result


def activity(html):
    tree = BeautifulSoup(html, "html.parser")
    if tree.select_one("#grades_wrapper") is None:
        raise SourceError("Blackboard 成绩页面结构已变化。")
    result = {}
    for row in tree.select("#grades_wrapper .sortable_item_row[id]"):
        classes = row.get("class", [])
        text = row.get_text(" ", strip=True).casefold()
        result["_" + row["id"] + "_1"] = True if "graded_item_row" in classes or "submitted_item_row" in classes else False if any(value in text for value in ("no submission", "not submitted", "未提交", "未尝试")) else None
    return result


def materials(nodes, course_id):
    result = []
    for node in nodes:
        if node["kind"] == "folder":
            continue
        canonical = identity("blackboard", course_id + ":" + node["id"])
        url = BASE + "/webapps/blackboard/content/listContent.jsp?" + urlencode({"course_id": course_id, "content_id": node.get("parentId") or node["id"], "mode": "reset"})
        base = {"id": canonical, "source": "blackboard", "source_id": node["id"], "source_course_id": course_id, "course_id": identity("blackboard", course_id), "title": node["title"], "type": node["kind"], "path": node["path"], "body_text": node["body_text"], "url": url}
        if node["kind"] == "file":
            base["download_url"] = "/api/v1/modules/blackboard/file?" + urlencode({"material_id": canonical})
        result.append(base)
        for anchor in BeautifulSoup(node.get("body") or "", "html.parser").select("a[href]"):
            target = urlsplit(urljoin(BASE, anchor["href"]))
            if target.netloc != urlsplit(BASE).netloc or not target.path.startswith("/bbcswebdav/"):
                continue
            name = anchor.get_text(" ", strip=True) or target.path.rsplit("/", 1)[-1]
            mid = canonical + ":" + digest(target.geturl())
            result.append({**base, "id": mid, "title": name, "type": "file", "path": node["path"] + [name], "source_path": target.path + ("?" + target.query if target.query else ""), "download_url": "/api/v1/modules/blackboard/file?" + urlencode({"material_id": mid})})
    return result


def fetch(remote, previous):
    result = {"courses": [], "assignments": [], "materials": [], "announcements": [], "issues": [], "metadata": {"scope": "visible_uncompleted_courses"}}
    try:
        states = portal(remote.html(BASE + "/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"))
    except HTTPException:
        states = {item["source_id"]: item for item in previous.get("courses", [])}
        result["issues"].append("课程门户暂时不可读，保留已知课程学期。")
    memberships = list(remote.pages(BASE + "/learn/api/public/v1/users/me/courses"))
    for membership in memberships:
        try:
            cid = checked(membership.get("courseId"))
        except SourceError:
            result["issues"].append("一条课程成员记录缺少合法标识。")
            continue
        if states.get(cid, {}).get("status") == "completed":
            continue
        try:
            detail = remote.json("GET", BASE + f"/learn/api/public/v1/courses/{cid}")
            if not isinstance(detail, dict) or not detail.get("name"):
                raise SourceError("Blackboard 课程缺少名称。")
            info = states.get(cid, {})
            term = TERM.search(info.get('term') or detail['name'])
            item = course("blackboard", cid, detail["name"], info.get("code") or detail.get("courseId"), term[0] if term else '', BASE + "/webapps/blackboard/execute/launcher?" + urlencode({"type": "Course", "id": cid}), status=info.get("status", "unknown"))
            result["courses"].append(item)
            nodes = contents(remote, cid, result["issues"])
            extra = []
            for node in nodes:
                if node["kind"] in {"assignment", "test"} and node.get("parentId"):
                    try:
                        html = remote.html(BASE + "/webapps/blackboard/content/listContent.jsp?" + urlencode({"course_id": cid, "content_id": node["parentId"], "mode": "reset"}))
                        row = BeautifulSoup(html, "html.parser").find(id="contentListItem:" + node["id"])
                        if row:
                            extra.append({**node, "body": str(row)})
                    except HTTPException:
                        result["issues"].append(node["title"] + " 的附件暂时不可读。")
            result["materials"].extend(materials(nodes + extra, cid))
            grades, submitted = {}, {}
            try:
                grades = {value.get("columnId"): value for value in remote.pages(BASE + f"/learn/api/public/v2/courses/{cid}/gradebook/users/me")}
                columns = list(remote.pages(BASE + f"/learn/api/public/v2/courses/{cid}/gradebook/columns"))
            except HTTPException:
                columns = []
                result["issues"].append(item["title"] + " 的成绩暂时不可读，提交状态保留未知。")
            try:
                submitted = activity(remote.html(BASE + f"/webapps/bb-mygrades-BBLEARN/myGrades?course_id={cid}&stream_name=mygrades"))
            except HTTPException:
                result["issues"].append(item["title"] + " 的提交活动页面暂时不可读。")
            by_content = {column.get("contentId"): column for column in columns}
            item["grades"] = [{"title": column.get("name"), "score": (grades.get(column.get("id"), {}).get("displayGrade") or {}).get("score"), "max_score": (column.get("score") or {}).get("possible")} for column in columns]
            for node in nodes:
                if node["kind"] not in {"assignment", "test"}:
                    continue
                column = by_content.get(node["id"], {})
                grade = grades.get(column.get("id"), {})
                display = grade.get("displayGrade") if isinstance(grade.get("displayGrade"), dict) else {}
                is_submitted = submitted.get(column.get("id"))
                if display.get("score") is not None:
                    is_submitted = True
                state, open_now = availability(node.get("availability"))
                result["assignments"].append({"id": identity("blackboard", cid + ":" + node["id"]), "source": "blackboard", "course_id": item["id"], "source_id": node["id"], "title": node["title"], "body_text": node["body_text"], "url": item["url"], "submitted": is_submitted, "score": display.get("score"), "max_score": (column.get("score") or {}).get("possible"), "due_at": timestamp((column.get("grading") or {}).get("due")), "release_at": timestamp(node.get("created")), "availability": state, "actionable": open_now, "submission_available": None})
            try:
                html = remote.html(BASE + "/webapps/blackboard/execute/announcement?" + urlencode({"method": "search", "context": "course", "course_id": cid}))
                tree = BeautifulSoup(html, "html.parser")
                if tree.select_one("#announcementList, #announcementForm") is None:
                    raise SourceError("Blackboard 公告页面结构已变化。")
                for row in tree.select("#announcementList > li[id]"):
                    title, body = row.select_one("h3.item"), row.select_one(".details .vtbegenerated")
                    result["announcements"].append({"id": identity("blackboard", cid + ":" + row["id"]), "source": "blackboard", "course_id": item["id"], "title": title.get_text(" ", strip=True) if title else "课程公告", "body_text": body.get_text(" ", strip=True) if body else "", "url": item["url"]})
            except HTTPException:
                result["issues"].append(item["title"] + " 的公告暂时不可读。")
                result["announcements"].extend(old for old in previous.get("announcements", []) if old.get("course_id") == item["id"])
        except HTTPException:
            result["issues"].append("一门 Blackboard 课程暂时不可读，保留上次数据。")
            for kind in ("courses", "assignments", "materials", "announcements"):
                existing = {item["id"] for item in result[kind]}
                result[kind].extend({**old, "stale": True} for old in previous.get(kind, []) if (old.get("course_id") == identity("blackboard", cid) or old["id"] == identity("blackboard", cid)) and old["id"] not in existing)
    return result
