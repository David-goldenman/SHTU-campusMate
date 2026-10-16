import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError

reader = load("timetable").fetch.__globals__
weeks, parse = reader["weeks"], reader["parse"]
catalogue, current, index = reader["catalogue"], reader["current"], reader["index"]
assert weeks("0" * 49 + "1100", 2026, 50, 1, 10) == [1, 2]
assert weeks("01" + "0" * 51, 2026, 50, 1, 10) == [5]
mask = "011" + "0" * 50
html = f'''<tr><td>CS100</td><td><a class="cs-detail-link" data-course-id="7">合成课程</a></td></tr><script>
var table = new CourseTable(2026,91); var unitCount=13;
var teachers=[{{name:"合成教师"}}];
activity = new TaskActivity(t.join(','), names.join(','), "7(CS100)", "合成课程,实验", "1", "测试教室", "{mask}", null);
index=1*unitCount+4; index=1*unitCount+5; index=1*unitCount+8;
table.marshalTable(2,1,18);</script>'''
result = parse(html, "2026-2027学年秋季")
assert len(result["timetable"]) == 2
item = result["timetable"][0]
assert (item["weekday"], item["period_start"], item["period_end"], item["weeks"], item["teacher"]) == (2, 5, 6, [1, 2], "合成教师")
for invalid in [html.replace(mask, "010"), "<html>maintenance</html>"]:
    try:
        parse(invalid, "2026 Fall")
        raise AssertionError("Malformed timetable must preserve the previous snapshot")
    except SourceError:
        pass
calendar = 'semesters:{y0:[{id:262,schoolYear:"2025-2026",name:"1"},{id:263,schoolYear:"2025-2026",name:"2"},{id:264,schoolYear:"2025-2026",name:"3"}],y1:[{id:282,schoolYear:"2026-2027",name:"1"}]}'
terms = catalogue(calendar)
assert [(item["id"], item["name"], item["season"]) for item in terms] == [("262", "2025-2026学年秋季", "秋季"), ("263", "2025-2026学年春季", "春季"), ("264", "2025-2026学年夏季", "夏季"), ("282", "2026-2027学年秋季", "秋季")]
assert current(terms, date(2026, 10, 16))["id"] == "282"
assert current(terms, date(2026, 2, 20))["id"] == "263"
assert current(terms, date(2026, 7, 20))["id"] == "264"
assert current(terms, date(2027, 1, 5))["id"] == "282"
assert current(terms[:1], date(2026, 10, 16)) is None
assert index('<script>addInput(form,"ids","15098");semesterCalendar({value:"264",option:"学期"});</script>') == {"student": "15098", "semester_id": "264"}
blank = parse('<html><script>var App = {contextPath:"/eams"};</script><body>该学期没有课表</body></html>', "2026-2027学年夏季")
assert blank["timetable"] == [] and blank["issues"] == ["该学期还没有发布课表。"] and blank["metadata"]["week_count"] is None
print("timetable: calendar rollover, JS arguments, disjoint periods, week masks, semester catalogue and page changes passed")
