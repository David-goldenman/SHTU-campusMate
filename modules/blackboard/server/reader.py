import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from fastapi import HTTPException

from backend.services.campus import SourceError, course, identity, plain, timestamp
from backend.services.campus.data import digest
from .submission import activity, decide, score_number, submission_history

BASE = "https://elearning.shanghaitech.edu.cn:8443"
KINDS = {"resource/x-bb-folder": "folder", "resource/x-bb-file": "file", "resource/x-bb-assignment": "assignment", "resource/x-bb-asmt-test-link": "test", "resource/x-bb-externallink": "link"}
TERM = re.compile(r"20\d{2}(?:[-–]20\d{2}学年|\s*[-–]\s*20\d{2})?(?:\s*学年|\s*年)?\s*(?:[春夏暑秋]季?(?:学期)?|(?:fall|autumn|spring|summer))", re.I)


def checked(value):
    if not isinstance(value, str) or not re.fullmatch(r"_[1-9]\d*_1", value):
        raise SourceError("Blackboard 返回了无法识别的资源标识。")
    return value


def grade_values(column, grade):
    display = grade.get('displayGrade') if isinstance(grade.get('displayGrade'), dict) else {}
    possible = column.get('score') if isinstance(column.get('score'), dict) else {}
    grading = column.get('grading') if isinstance(column.get('grading'), dict) else {}
    return {'score': score_number(display.get('score')), 'max_score': score_number(possible.get('possible')),
            'due_at': timestamp(grading.get('due'))}


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


def term_labels(remote):
    result = {}
    for value in remote.pages(BASE + "/learn/api/public/v1/terms?limit=100"):
        if isinstance(value.get("id"), str) and isinstance(value.get("name"), str) and value["name"].strip():
            result[value["id"]] = value["name"].strip()
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


def announcements(html, course):
    """Parse one course's announcement page.

    Return None when the page is unreadable or its container is gone, so the
    caller can silently keep the previous announcements. Rows that miss the
    title or id elements are skipped instead of being invented.
    """
    tree = BeautifulSoup(html, "html.parser")
    if tree.select_one("#announcementList, #announcementForm") is None:
        return None
    result = []
    for row in tree.select("#announcementList > li[id]"):
        try:
            title = row.select_one("h3.item")
            text = title.get_text(" ", strip=True) if title else ""
            if not text:
                continue
            body = row.select_one(".details .vtbegenerated")
            result.append({"id": identity("blackboard", course["source_id"] + ":" + row["id"]), "source": "blackboard", "course_id": course["id"], "title": text, "body_text": body.get_text(" ", strip=True) if body else "", "url": course["url"]})
        except Exception:
            # 单条公告结构异常时默认忽略，不影响同一课程的其他公告。
            continue
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
    previous_assignments = {item['id']: item for item in previous.get('assignments', [])}
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        states = portal(remote.html(BASE + "/webapps/portal/execute/tabs/tabAction?tab_tab_group_id=_1_1"))
    except HTTPException:
        states = {item["source_id"]: item for item in previous.get("courses", [])}
        result["issues"].append("课程门户暂时不可读，保留已知课程学期。")
    memberships = list(remote.pages(BASE + "/learn/api/public/v1/users/me/courses"))
    try:
        labels = term_labels(remote)
    except HTTPException:
        labels = {}
        result["issues"].append("Blackboard 学期列表暂时不可读，学期按课程名称推断。")
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
            # termId comes from the course REST record; the term name is the only
            # reliable semester source because the portal label often omits it.
            term = TERM.search(labels.get(detail.get("termId"), "")) or TERM.search(detail["name"]) or TERM.search(info.get("term") or "")
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
            except HTTPException:
                result["issues"].append(item["title"] + " 的成绩暂时不可读。")
            try:
                columns = list(remote.pages(BASE + f"/learn/api/public/v2/courses/{cid}/gradebook/columns"))
            except HTTPException:
                columns = []
                result["issues"].append(item["title"] + " 的成绩列暂时不可读。")
            try:
                submitted = activity(remote.html(BASE + f"/webapps/bb-mygrades-BBLEARN/myGrades?course_id={cid}&stream_name=mygrades"))
            except HTTPException:
                result["issues"].append(item["title"] + " 的提交活动页面暂时不可读。")
            by_content = {column.get("contentId"): column for column in columns}
            item['grades'] = []
            for column in columns:
                numbers = grade_values(column, grades.get(column.get('id'), {}))
                item['grades'].append({'title': column.get('name'), 'score': numbers['score'], 'max_score': numbers['max_score']})
            for node in nodes:
                if node["kind"] not in {"assignment", "test"}:
                    continue
                column = by_content.get(node["id"], {})
                grade = grades.get(column.get("id"), {})
                canonical = identity("blackboard", cid + ":" + node["id"])
                history_url = BASE + "/webapps/assignment/uploadAssignment?" + urlencode({"course_id": cid, "content_id": node["id"], "mode": "view"})
                load_history = (lambda: remote.html(history_url)) if node['kind'] == 'assignment' else None
                judgement = decide(grade, submitted.get(column.get('id')), load_history, previous_assignments.get(canonical, {}), checked_at)
                if judgement['submission_status'] == 'unknown' or judgement['submission_stale']:
                    result['issues'].append(node['title'] + ' 的提交情况本次未能核实，请查看记录说明。')
                numbers = grade_values(column, grade)
                column_due = numbers['due_at']
                state, open_now = availability(node.get("availability"))
                result["assignments"].append({"id": canonical, "source": "blackboard", "course_id": item["id"], "source_id": node["id"], "title": node["title"], "body_text": node["body_text"], "url": history_url if load_history else item["url"],
                    **judgement, "score": numbers['score'] if numbers['score'] is not None else judgement.get('score'),
                    "max_score": numbers['max_score'] if numbers['max_score'] is not None else judgement.get('max_score'),
                    "due_at": column_due or judgement.get('due_at'), 'due_at_evidence': 'gradebook' if column_due else judgement.get('due_at_evidence'),
                    "release_at": timestamp(node.get("created")), "availability": state, "actionable": open_now, "submission_available": None})
            previous_announcements = [old for old in previous.get("announcements", []) if old.get("course_id") == item["id"]]
            try:
                fresh = announcements(remote.html(BASE + "/webapps/blackboard/execute/announcement?" + urlencode({"method": "search", "context": "course", "course_id": cid})), item)
            except Exception:
                # 公告是附加信息：页面不可读、请求失败或结构变化时默认忽略，保留上次公告。
                fresh = None
            result["announcements"].extend(previous_announcements if fresh is None else fresh)
        except HTTPException:
            result["issues"].append("一门 Blackboard 课程暂时不可读，保留上次数据。")
            for kind in ("courses", "assignments", "materials", "announcements"):
                existing = {item["id"] for item in result[kind]}
                result[kind].extend({**old, "stale": True} for old in previous.get(kind, []) if (old.get("course_id") == identity("blackboard", cid) or old["id"] == identity("blackboard", cid)) and old["id"] not in existing)
    return result
