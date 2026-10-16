import ast
import json
import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, course, identity
from backend.services.campus.data import digest

BASE = "https://eams.shanghaitech.edu.cn"
INDEX_URL = BASE + "/eams/courseTableForStd.action"
TABLE_URL = BASE + "/eams/courseTableForStd!courseTable.action"
CALENDAR_URL = BASE + "/eams/dataQuery.action"
SEASONS = {"1": "秋季", "2": "春季", "3": "夏季"}
LOGIN = '#loginForm, form[action="/login"], input[type="password"]'
CHROME = re.compile(r"contextPath\s*:\s*['\"]/eams")
TABLE_MARKERS = ("CourseTable", "marshalTable", "unitCount", "TaskActivity")
BLOCK_MARKERS = ("请不要过快", "过于频繁", "操作太快", "访问受限")
DEFAULT_WEEKS, DEFAULT_UNITS = 18, 13


def read(remote, method, url, **kwargs):
    """读取页面；教务提示访问过快时等待后重试，不把提示内容当作数据。"""
    for attempt in range(3):
        page = remote.request(method, url, **kwargs).text
        if not any(marker in page for marker in BLOCK_MARKERS):
            return page
        if attempt == 2:
            break
        remote.cancelled.wait(2.0)
    raise SourceError("教务提示访问过快，已保留上次数据，请稍后再同步。")


def catalogue(page):
    """学期目录给出编号、学年与季节，供页面按学年和学期切换。"""
    values = re.findall(r'\{id:(\d+),schoolYear:"([^"]+)",name:"(\d+)"\}', page)
    if not values:
        raise SourceError("教务没有返回学期目录，已保留上次数据。")
    return [{"id": value, "school_year": year, "season": SEASONS.get(season, season), "name": year + "学年" + SEASONS.get(season, season)} for value, year, season in values]


def current(terms, today=None):
    """按当天日期定位当前学期：九月到一月是秋季，二月到六月是春季，七八月是夏季。"""
    now = today or date.today()
    if now.month == 1:
        year, season = now.year - 1, "秋季"
    elif now.month >= 9:
        year, season = now.year, "秋季"
    elif now.month <= 6:
        year, season = now.year - 1, "春季"
    else:
        year, season = now.year - 1, "夏季"
    return next((item for item in terms if item["school_year"] == str(year) + "-" + str(year + 1) and item["season"] == season), None)


def index(page):
    """课表首页给出学生编号和教务默认学期。"""
    soup = BeautifulSoup(page, "html.parser")
    if soup.select_one(LOGIN):
        raise LoginRequired("教务会话已失效，请在设置重新连接 IDS。")
    student = re.search(r"addInput\(\s*form\s*,\s*['\"]ids['\"]\s*,\s*['\"](\d+)['\"]", page) or re.search(r"tutorRedirectstudentId=(\d+)", page)
    term = re.search(r"semesterCalendar\s*\(\s*\{[^}]*\bvalue\s*:\s*['\"]?(\d+)", page)
    if not student or not term:
        raise SourceError("教务未返回当前学生或学期。")
    return {"student": student[1], "semester_id": term[1]}


def table(remote, student, semester_id):
    """按学期读取课表页面；没有发布课表的学期会返回不含课表脚本的页面。"""
    return read(remote, "POST", TABLE_URL, data={"ignoreHead": "1", "setting.kind": "std", "startWeek": "", "semester.id": semester_id, "ids": student, "tutorRedirectstudentId": student})


def weeks(mask, year, first, start, end):
    if not re.fullmatch("[01]{53}", mask) or not 1 <= first <= 53 or not 1 <= start <= end <= 53:
        raise SourceError("教务周次参数格式已变化。")
    cut = first + start - 2
    # EAMS shifts activities that belong entirely to the next calendar year.
    if date(year, 12, 31).weekday() != 5 and "1" in mask[:cut] and "1" not in mask[cut:]:
        mask = mask[1:] + "0"
    return [week for week in range(start, end + 1) if mask[(first + week - 2) % 53] == "1"]


def js_arguments(script, position):
    values, start, depth, quote, escaped = [], position, 0, None, False
    for index in range(position, len(script)):
        char = script[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([{" :
            depth += 1
        elif char == ")" and depth == 0:
            values.append(script[start:index].strip())
            return values, index + 1
        elif char in ")]}" :
            depth -= 1
        elif char == "," and depth == 0:
            values.append(script[start:index].strip())
            start = index + 1
    raise SourceError("教务活动参数未完整返回。")


def literal(value):
    try:
        parsed = json.loads(value) if value.startswith('"') else ast.literal_eval(value)
    except (ValueError, SyntaxError):
        raise SourceError("教务活动文字格式已变化。") from None
    if not isinstance(parsed, str):
        raise SourceError("教务活动文字格式已变化。")
    return parsed


def parse(html, term):
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(LOGIN):
        raise LoginRequired("教务会话已失效，请在设置重新连接 IDS。")
    script = "\n".join(node.get_text() for node in soup.select("script"))
    header = re.search(r"new\s+CourseTable\s*\(\s*(\d{4})\s*,\s*(\d+)", script)
    span = re.search(r"\.marshalTable\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", script)
    if not header or not span:
        # 学期还没发布课表时教务返回应用页面但没有课表脚本；其他形态仍按结构变化处理。
        if CHROME.search(html) and not any(marker in script for marker in TABLE_MARKERS):
            return {"courses": [], "timetable": [], "metadata": {"semester": term, "week_count": None, "units": None}, "issues": ["该学期还没有发布课表。"]}
        raise SourceError("教务没有返回课表结构，请确认学期或稍后重试。")
    year, count = map(int, header.groups())
    first, start, end = map(int, span.groups())
    units_match = re.search(r"\bunitCount\s*=\s*(\d+)", script)
    units = int(units_match[1]) if units_match else count // 7
    if not 1 <= units <= 30:
        raise SourceError("教务每天节数不符合预期。")
    courses = {}
    for anchor in soup.select("a.cs-detail-link[data-course-id]"):
        row = anchor.find_parent("tr")
        code = re.search(r"\b[A-Z]{2,}\s*\d{2,}[A-Z]?\b", row.get_text(" ", strip=True) if row else "")
        value = str(anchor["data-course-id"])
        link = row.select_one('a[href*="taskTable.action"]') if row else None
        courses[value] = course("timetable", value, anchor.get_text(" ", strip=True), code[0] if code else "", term, urljoin(BASE, link["href"]) if link else BASE + "/eams/courseTableForStd.action", status="active")
    activities = list(re.finditer(r"\bactivity\s*=\s*new\s+TaskActivity\s*\(", script))
    result = {"courses": list(courses.values()), "timetable": [], "metadata": {"semester": term, "week_count": end, "units": units}}
    for number, match in enumerate(activities):
        fields, position = js_arguments(script, match.end())
        if len(fields) < 7:
            raise SourceError("教务活动缺少课程、地点或周次。")
        value, location, mask = literal(fields[2]).split("(", 1)[0], literal(fields[5]), literal(fields[6])
        if value not in courses:
            raise SourceError("课表活动无法对应到课程清单。")
        active_weeks = weeks(mask, year, first, start, end)
        teachers = list(re.finditer(r"\bteachers\s*=\s*\[([\s\S]*?)\]\s*;", script[:match.start()]))
        teacher = "、".join(literal(token) for token in re.findall(r"\bname\s*:\s*(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')", teachers[-1][1])) if teachers else ""
        section = script[position:activities[number + 1].start() if number + 1 < len(activities) else len(script)]
        positions = [(int(day), int(period)) for day, period in re.findall(r"\bindex\s*=\s*(\d+)\s*\*\s*unitCount\s*\+\s*(\d+)", section)]
        if not positions:
            positions = [divmod(int(index), units) for index in re.findall(r"\bindex\s*=\s*(\d+)\s*;", section)]
        if not positions or any(not 0 <= day < 7 or not 0 <= period < units for day, period in positions):
            raise SourceError("课表星期或节次格式已变化。")
        by_day = {}
        for day, period in positions:
            by_day.setdefault(day, set()).add(period + 1)
        for day, periods in by_day.items():
            runs = []
            for period in sorted(periods):
                if runs and period == runs[-1][-1] + 1:
                    runs[-1].append(period)
                else:
                    runs.append([period])
            for run in runs:
                result["timetable"].append({"id": identity("timetable", digest([value, day, run, active_weeks, teacher, location])), "source": "timetable", "course_id": courses[value]["id"], "title": courses[value]["title"], "weekday": day + 1, "period_start": run[0], "period_end": run[-1], "weeks": active_weeks, "teacher": teacher, "location": location, "url": courses[value]["url"]})
    return result


def fetch(remote, previous):
    metadata = previous.get("metadata", {}) if isinstance(previous, dict) else {}
    value = index(read(remote, "GET", INDEX_URL))
    terms = catalogue(read(remote, "POST", CALENDAR_URL, data={"tagId": "semester", "dataType": "semesterCalendar", "value": value["semester_id"], "empty": "false"}))
    # 教务保存的学期可能停留在上一学期，以日期定位的当前学期为准，找不到时沿用教务默认。
    chosen = current(terms) or next((item for item in terms if item["id"] == value["semester_id"]), None) or {"id": value["semester_id"], "name": metadata.get("semester", "")}
    result = parse(table(remote, value["student"], chosen["id"]), chosen["name"])
    result["metadata"].update({"semester_id": chosen["id"], "student_id": value["student"], "semesters": terms})
    fallback = metadata if metadata.get("semester_id") == chosen["id"] else {}
    if not result["metadata"].get("week_count"):
        result["metadata"]["week_count"] = fallback.get("week_count") or DEFAULT_WEEKS
    if not result["metadata"].get("units"):
        result["metadata"]["units"] = fallback.get("units") or DEFAULT_UNITS
    return result
