import ast
import json
import re
from datetime import date, datetime, time
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, course, identity
from backend.services.campus.data import digest
from .semesters import select_semester

BASE = "https://eams.shanghaitech.edu.cn"


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
    if soup.select_one('#loginForm, input[type="password"]'):
        raise LoginRequired("教务会话已失效，请在设置重新连接 IDS。")
    script = "\n".join(node.get_text() for node in soup.select("script"))
    table = re.search(r"new\s+CourseTable\s*\(\s*(\d{4})\s*,\s*(\d+)", script)
    span = re.search(r"\.marshalTable\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", script)
    if not table or not span:
        raise SourceError("教务没有返回课表结构，请确认学期或稍后重试。")
    year, count = map(int, table.groups())
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
    periods = []
    rows = [row for row in soup.select('tr') if any(str(cell.get('id', '')).startswith('TD')
            for cell in row.find_all('td', recursive=False))]
    for number, row in enumerate(rows, 1):
        # Count every lesson row, including a row whose time is missing.
        labels = []
        for cell in row.find_all(['th', 'td'], recursive=False):
            if str(cell.get('id', '')).startswith('TD'):
                break
            labels.append(cell.get_text(' ', strip=True))
        times = re.findall(r'\b(\d{1,2}:\d{2})\b', ' '.join(labels).replace('：', ':'))
        if len(times) == 2:
            try:
                start_time, end_time = (time.fromisoformat(value.zfill(5)) for value in times)
            except ValueError:
                continue
            if start_time < end_time:
                periods.append({'period': number, 'start': start_time.strftime('%H:%M'), 'end': end_time.strftime('%H:%M')})
    result['metadata']['periods'] = periods
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


def fetch(remote, previous, *, term_starts=None):
    page = remote.request("GET", BASE + "/eams/courseTableForStd.action").text
    student = re.search(r"addInput\(\s*form\s*,\s*['\"]ids['\"]\s*,\s*['\"](\d+)['\"]", page)
    term = re.search(r"semesterCalendar\s*\(\s*\{[^}]*\bvalue\s*:\s*['\"]?(\d+)", page)
    if not student or not term:
        if "loginForm" in page or "authserver" in page:
            raise LoginRequired("教务需要重新登录 IDS。")
        raise SourceError("教务未返回当前学生或学期。")
    calendar = remote.request("POST", BASE + "/eams/dataQuery.action", data={"tagId": "semester", "dataType": "semesterCalendar", "value": term[1], "empty": "false"}).text
    term_id, term_name = select_semester(calendar, datetime.now(ZoneInfo('Asia/Shanghai')).date(), term_starts)
    html = remote.request("POST", BASE + "/eams/courseTableForStd!courseTable.action", data={"ignoreHead": "1", "setting.kind": "std", "startWeek": "", "semester.id": term_id, "ids": student[1], "tutorRedirectstudentId": student[1]}).text
    result = parse(html, term_name)
    result["metadata"]["semester_id"] = term_id
    return result
