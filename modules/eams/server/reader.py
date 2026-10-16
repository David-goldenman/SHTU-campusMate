import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from fastapi import HTTPException

from backend.services.auth import LoginRequired
from backend.services.campus import KINDS, SourceError, identity
from backend.services.campus.data import digest, plain, semester, timestamp

BASE = "https://eams.shanghaitech.edu.cn"
INDEX_URL = BASE + "/eams/stdExamTable!innerIndex.action"
GRADE_URL = BASE + "/eams/teach/grade/course/person!historyCourseGrade.action?projectType=MAJOR"
PLAN_URL = BASE + "/eams/myPlan.action"
SEASONS = {"1": "秋季", "2": "春季", "3": "夏季"}
PAGE_PAUSE = 1.2
BLOCK_PAUSE = 4.0
BLOCK_MARKERS = ("请不要过快点击", "请不要过快", "过于频繁", "操作太快", "访问受限")
LOGIN = '#loginForm, form[action="/login"], input[type="password"]'


def pause(remote, seconds):
    """等待期间保持可取消，同步停止后不再继续占用连接。"""
    remote.cancelled.wait(seconds)


def soup_of(page):
    value = BeautifulSoup(page, "html.parser")
    if value.select_one(LOGIN):
        raise LoginRequired("教务会话已失效，请在设置重新连接 IDS。")
    return value


def read(remote, method, url, **kwargs):
    """读取页面；教务提示访问过快时等待后重试，不把提示内容当作数据。"""
    for attempt in range(3):
        page = remote.request(method, url, **kwargs).text
        marker = next((value for value in BLOCK_MARKERS if value in page), None)
        if marker is None:
            pause(remote, PAGE_PAUSE)
            return page
        if attempt == 2:
            break
        pause(remote, BLOCK_PAUSE)
    raise SourceError("教务提示访问过快，已保留上次数据，请稍后再同步。")


def attempt(issues, label, work):
    """单个板块失败时保留上次数据，其余板块继续读取。"""
    try:
        return work()
    except LoginRequired:
        raise
    except (SourceError, ValueError):
        pass
    except HTTPException as error:
        if error.status_code not in {403, 404}:
            raise
    issues.append(label + "暂时无法读取，已保留上次数据。")
    return None


def semesters(calendar):
    values = re.findall(r'\{id:(\d+),schoolYear:"([^"]+)",name:"(\d+)"\}', calendar)
    if not values:
        raise SourceError("教务没有返回学期目录，已保留上次数据。")
    return [{"id": value, "name": year + "学年" + SEASONS.get(term, term)} for value, year, term in values]


def index(page):
    """考试页给出学生、当前学期、考试批次和考试片段地址。"""
    value = soup_of(page)
    student = re.search(r"tutorRedirectstudentId=(\d+)", page)
    current = re.search(r"\.semesterCalendar\(\{[^}]*\bvalue:\"(\d+)\"", page)
    target = re.search(r"bg\.Go\('([^']*stdExamTable!examTable\.action[^']*)'", page)
    batches = [{"id": option["value"], "name": plain(option.get_text(" ", strip=True))} for option in value.select("#examBatchId option") if option.get("value")]
    if not student or not current:
        raise SourceError("教务考试页结构已变化，已保留上次数据。")
    default = "/eams/stdExamTable!examTable.action?examBatch.id=" + (batches[0]["id"] if batches else "") + "&tutorRedirectstudentId=" + student[1]
    return {"student": student[1], "semester_id": current[1], "batches": batches, "target": target[1] if target else default}


def moment(day, window):
    start = re.search(r"\d{1,2}:\d{2}", window or "")
    try:
        value = datetime.fromisoformat(day + "T" + (start[0] if start else "00:00"))
    except ValueError:
        return None, start[0] if start else ""
    return value.replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(), start[0] if start else ""


def grade_id(term, section):
    return identity("eams", "grade:" + semester(term) + ":" + section)


def exams(page, term, url):
    value = soup_of(page)
    table = value.select_one("table")
    heads = {cell.get_text(" ", strip=True) for cell in table.select("tr th")} if table else set()
    if not table or not {"课程名称", "考试日期", "考试地点"} <= heads:
        raise SourceError("教务考试表结构已变化，已保留上次数据。")
    items = []
    for row in table.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 8 or not cells[0] or not cells[3]:
            continue
        code, title, kind, day, window, location, status, note = cells[:8]
        due, start = moment(day, window)
        items.append({"id": identity("eams", digest(["exam", term, code, day, window])), "source": "eams", "source_id": code,
                      "kind": "exam", "title": plain(title), "exam_kind": kind, "date": day, "start_time": start, "window": window,
                      "location": location, "status": status, "note": note, "due_at": due, "term": term, "semester": semester(term),
                      "course_id": grade_id(term, code), "url": url})
    return sorted(items, key=lambda item: (item["date"], item["start_time"], item["title"]))



def number(value):
    try:
        return float(str(value or "").replace(",", "").strip())
    except ValueError:
        return None


def caption(value):
    """培养方案课程格带组内序号，去掉序号并统一空格。"""
    return re.sub(r"^\d{1,3}[\s\u00a0]+", "", plain(value)).replace("\u00a0", " ").strip()


def grades(page):
    """成绩页给出学期汇总网格与课程成绩明细网格。"""
    value = soup_of(page)
    tables = value.select("table.gridtable")
    if len(tables) < 2:
        raise SourceError("教务成绩页结构已变化，已保留上次数据。")
    summary = []
    for row in tables[0].select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) == 5 and re.fullmatch(r"20\d{2}-20\d{2}", cells[0]):
            summary.append({"year": cells[0], "term": cells[1], "label": cells[0] + "学年" + SEASONS.get(cells[1], cells[1]),
                            "courses": int(cells[2]) if cells[2].isdigit() else None, "credits": number(cells[3]), "gpa": number(cells[4])})
    courses, total, weight = [], 0.0, 0.0
    for row in tables[1].select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
        if len(cells) < 10 or not re.fullmatch(r"[A-Z]{2,}\d{2,}[A-Z]?", cells[2]):
            continue
        year, season, code, section, title, category, credits, score, point, published = cells[:10]
        grade, size = number(point), number(credits)
        term = year + "-" + season
        courses.append({"id": grade_id(term, section), "source": "eams", "source_id": section, "kind": "grade",
                        "title": plain(title), "code": code, "term": term, "semester": semester(term),
                        "url": GRADE_URL, "credits": size, "score": score, "point": grade, "category": category,
                        "published_at": timestamp(published)})
        if grade is not None and size:
            total, weight = total + grade * size, weight + size
    if not courses:
        raise SourceError("教务成绩页没有课程记录，已保留上次数据。")
    return {"overall": round(total / weight, 3) if weight else None, "weighted_credits": round(weight, 2),
            "earned_credits": round(sum(item["credits"] for item in summary if item["credits"] is not None), 2) if summary else None,
            "semesters": summary}, courses


def plan(page):
    """培养方案页的 #PrintA 标签页给出专业培养计划课程表。"""
    value = soup_of(page)
    node = value.select_one("#PrintA") or value
    table = node.select_one("table.planTable")
    if not table:
        raise SourceError("教务培养方案页没有返回课程表，已保留上次数据。")
    head = node.select_one("p")
    groups, levels, requirements, notes = {}, ["", "", ""], [], []
    for row in table.select("tr"):
        cells = row.select("td")
        text = row.get_text(' ', strip=True)
        if cells and any(label in text for label in ('应修学分', '学分小计', '全程总计')):
            requirements.append({'path': [part for part in levels if part], 'text': text})
        if cells and cells[0].get_text(strip=True) == '备注':
            notes.append(text)
        position = next((index for index, cell in enumerate(cells) if "course" in (cell.get("class") or [])), None)
        if not position:
            continue
        code = re.sub(r"\s+", "", cells[position - 1].get_text(" ", strip=True))
        if not re.fullmatch(r"[A-Z]{2,}\d{2,}[A-Z]?(?:\.\d+)?", code):
            continue
        started = [cell.get_text(" ", strip=True) for cell in row.select("td.group")]
        if started:
            levels = (started + ["", "", ""])[:3]
        tail = [cell.get_text(" ", strip=True) for cell in cells[position + 13:]]
        groups.setdefault(tuple(part for part in levels if part), []).append({
            "code": code, "title": caption(cells[position].get_text(" ", strip=True)), "credits": number(cells[position + 1].get_text(" ", strip=True)),
            "terms": [index for index, cell in enumerate(cells[position + 2:position + 13], start=1) if cell.get_text(strip=True) == "√"],
            "required": bool(tail) and tail[0] == "是", "department": tail[1] if len(tail) > 1 else "",
            "note": " ".join(part for part in tail[2:] if part)})
    if not groups:
        raise SourceError("教务培养方案没有课程记录，已保留上次数据。")
    return {"title": plain(head.get_text(" ", strip=True)) if head else "", "groups": [{"path": list(path), "courses": courses} for path, courses in groups.items()], "requirements": requirements, "notes": notes}


def fetch(remote, previous):
    metadata = previous.get("metadata", {}) if isinstance(previous, dict) else {}
    issues = []
    value = index(read(remote, "GET", INDEX_URL))
    catalogue = attempt(issues, "学期目录", lambda: semesters(read(remote, "POST", BASE + "/eams/dataQuery.action", data={"tagId": "semester", "dataType": "semesterCalendar", "value": value["semester_id"], "empty": "false"}))) or metadata.get("semesters", [])
    term = next((item["name"] for item in catalogue if item["id"] == value["semester_id"]), metadata.get("semester", ""))
    batch = re.search(r"examBatch\.id=(\d+)", value["target"])
    exams_value = attempt(issues, "考试安排", lambda: exams(read(remote, "GET", urljoin(BASE, value["target"])), term, INDEX_URL))
    gpa_value = attempt(issues, "学期成绩", lambda: grades(read(remote, "GET", GRADE_URL)))
    plan_value = attempt(issues, "培养方案", lambda: plan(read(remote, "GET", PLAN_URL)))
    result = {kind: [] for kind in KINDS}
    result["courses"] = gpa_value[1] if gpa_value else previous.get("courses", [])
    result["assignments"] = exams_value if exams_value is not None else previous.get("assignments", [])
    result["metadata"] = {"semester": term, "semester_id": value["semester_id"], "student_id": value["student"], "semesters": catalogue,
                          "exams": {"batch": next((item["name"] for item in value["batches"] if item["id"] == batch[1]), "") if batch else "",
                                    "batch_id": batch[1] if batch else "", "batches": value["batches"]},
                          "gpa": gpa_value[0] if gpa_value else metadata.get("gpa", {}),
                          "study_plan": plan_value if plan_value else metadata.get("study_plan", {})}
    result["issues"] = issues
    return result
