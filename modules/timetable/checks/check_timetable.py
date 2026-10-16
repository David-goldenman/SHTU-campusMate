import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load
from backend.services.campus import SourceError

reader = load("timetable").fetch.__globals__
weeks, parse = reader["weeks"], reader["parse"]
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
print("timetable: calendar rollover, JS arguments, disjoint periods, week masks and page changes passed")
