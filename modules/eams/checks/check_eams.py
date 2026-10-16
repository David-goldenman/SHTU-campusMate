import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from backend.services.auth import LoginRequired
from backend.services.campus import SourceError
from backend.services.campus.data import digest, validate_bundle
from backend.services.campus.remote import Remote
from checks.module_support import load, sandbox

package = load("eams")
reader = package.fetch.__globals__
reader["pause"] = lambda remote, seconds: None

INDEX = """<html><body><form id="stdExamForm" action="/eams/stdExamTable!innerIndex.action" method="post">
<select id="examBatchId" name="examBatch.id"><option value="9">期末考试（考试周）</option><option value="8">期中考试</option></select>
<script>jQuery("#semesterBar1Semester").semesterCalendar({empty:"false",onChange:"",value:"282"},"");</script>
<script>bg.ready(function(){bg.Go('/eams/stdExamTable!examTable.action?examBatch.id=9&tutorRedirectstudentId=15098','contentDiv')});</script>
</body></html>"""

CALENDAR = """{yearDom:"<tr><td>2025-2026</td></tr>",semesters:[{id:262,schoolYear:"2025-2026",name:"1"},{id:282,schoolYear:"2026-2027",name:"1"}]}"""

EXAMS = """<table class="gridtable"><tr><th>课程序号</th><th>课程名称</th><th>考试类别</th><th>考试日期</th><th>考试安排</th><th>考试地点</th><th>考试情况</th><th>其它说明</th></tr>
<tr><td>CHEM1120.03</td><td>大学化学</td><td>期末考试</td><td>2026-01-09</td><td>10:30~12:30</td><td>物质学院 1-505</td><td>正常</td><td></td></tr>
<tr><td>EE150.02</td><td>信号与系统</td><td>期末考试</td><td>2026-01-13</td><td>08:00~10:00</td><td>教学中心202</td><td>正常</td><td>带计算器</td></tr>
<tr></tr></table>"""

EMPTY_EXAMS = """<table class="gridtable"><tr><th>课程序号</th><th>课程名称</th><th>考试类别</th><th>考试日期</th><th>考试安排</th><th>考试地点</th><th>考试情况</th><th>其它说明</th></tr><tr></tr></table>"""

GRADES = """<table class="gridtable"><tr><th>学年度</th><th>学期</th><th>门数</th><th>获得学分数</th><th>平均绩点</th></tr>
<tr><td colspan="5">2025-2026学年 门数：2</td></tr>
<tr><td>2025-2026</td><td>3</td><td>1</td><td>2</td><td>4</td></tr>
<tr><td>2025-2026</td><td>2</td><td>10</td><td>25</td><td>3.49</td></tr></table>
<table class="gridtable" id="grid1"><tr><th>学年学期</th><th>学期</th><th>课程代码</th><th>课程序号</th><th>课程名称</th><th>课程类别</th><th>学分</th><th>最终</th><th>绩点</th><th>发布时间</th></tr>
<tr><td>2024-2025</td><td>1</td><td>GEMA1001</td><td>GEMA1001.01</td><td>高等数学I</td><td>小组</td><td>4</td><td>A</td><td>4.0</td><td>2025-01-24 15:03:27</td></tr>
<tr><td>2024-2025</td><td>1</td><td>MT1025</td><td>MT1025.01</td><td>形势与政策（1）</td><td>阶段课程</td><td>0.5</td><td>P(60.0)</td><td></td><td>2025-01-22 11:10:43</td></tr></table>"""

PLAN = """<html><body><div id="tabs1"><ul><li id="tab1">已修课程</li><li id="tab2">培养方案</li></ul><div id="tab1_target"></div><div id="tab2_target"><div id="PrintA">
<p>本科 普通本科生 信息科学与技术学院 电子信息工程 专业培养计划(2026)</p>
<table class="planTable" id="planInfoTable1"><thead>
<tr><td colspan="5" rowspan="2">分类</td><td rowspan="2">课程代码</td><td rowspan="2">课程名称</td><td rowspan="2">学分</td><td colspan="11">建议修读学期</td><td rowspan="2">是否必修</td><td rowspan="2">开课院系</td><td rowspan="2">备注</td></tr>
<tr><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td><td>8</td><td>9</td><td>10</td><td>11</td></tr></thead>
<tr><td class="group">人文社科通识课程</td><td class="group">思政理论课</td><td class="group">思政必修课</td><td>MT1024</td><td class="course">1 形势与政策</td><td>2</td><td class="credit_hour">√</td><td class="credit_hour">√</td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td>是</td><td>思想政治理论课教研部</td><td>大一大二需参加讲座</td></tr>
<tr><td class="group">人文社科通识课程</td><td class="group">创意与艺术课程群</td><td>ARTS1308</td><td class="course">185 像素着色艺术</td><td>2</td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour">√</td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td class="credit_hour"></td><td>否</td><td>创意与艺术学院</td><td></td></tr>
<tr><td colspan="6">备注</td><td colspan="16">培养方案中的非必修课以选课前公布为准</td></tr></table>
</div></div></div></body></html>"""


class Blocked:
    def __init__(self, pages):
        self.pages, self.calls, self.cancelled = pages, 0, threading.Event()

    def request(self, method, url, **kwargs):
        self.calls += 1
        return httpx.Response(200, text=self.pages[min(self.calls - 1, len(self.pages) - 1)])


def handler(request):
    pages = {"/eams/stdExamTable!innerIndex.action": INDEX, "/eams/dataQuery.action": CALENDAR,
             "/eams/stdExamTable!examTable.action": EXAMS, "/eams/teach/grade/course/person!historyCourseGrade.action": GRADES,
             "/eams/myPlan.action": PLAN}
    return httpx.Response(200, text=pages[request.url.path]) if request.url.path in pages else httpx.Response(404)


def remote(transport):
    return Remote(httpx.Client(transport=transport), threading.Event(), ["eams.shanghaitech.edu.cn"])


assert reader["semesters"](CALENDAR) == [{"id": "262", "name": "2025-2026学年秋季"}, {"id": "282", "name": "2026-2027学年秋季"}]
value = reader["index"](INDEX)
assert (value["student"], value["semester_id"], value["target"]) == ("15098", "282", "/eams/stdExamTable!examTable.action?examBatch.id=9&tutorRedirectstudentId=15098")
assert value["batches"] == [{"id": "9", "name": "期末考试（考试周）"}, {"id": "8", "name": "期中考试"}]
try:
    reader["index"]('<form id="loginForm" action="/login"></form>')
    raise AssertionError("登录页必须转为 LoginRequired")
except LoginRequired:
    pass

throttled = Blocked(["<div>请不要过快点击，请稍后再试。</div>", INDEX])
assert reader["read"](throttled, "GET", "https://eams.shanghaitech.edu.cn/eams/x") == INDEX and throttled.calls == 2
stuck = Blocked(["<div>请不要过快点击，请稍后再试。</div>"])
try:
    reader["read"](stuck, "GET", "https://eams.shanghaitech.edu.cn/eams/x")
    raise AssertionError("访问过快提示不得作为数据返回")
except SourceError:
    pass
assert stuck.calls == 3

items = reader["exams"](EXAMS, "2025-2026学年秋季", "https://eams.shanghaitech.edu.cn/eams/stdExamTable!innerIndex.action")
assert len(items) == 2
first = items[0]
assert (first["title"], first["date"], first["window"], first["location"], first["due_at"], first["status"]) == ("大学化学", "2026-01-09", "10:30~12:30", "物质学院 1-505", "2026-01-09T10:30:00+08:00", "正常")
assert first["course_id"] == "eams:grade:CHEM1120.03" and first["id"].startswith("eams:") and items[1]["note"] == "带计算器"
assert reader["exams"](EMPTY_EXAMS, "2026-2027学年秋季", "x") == []
try:
    reader["exams"]("<html><body>maintenance</body></html>", "2026-2027学年秋季", "x")
    raise AssertionError("考试表结构变化必须保留缓存")
except SourceError:
    pass

gpa, courses = reader["grades"](GRADES)
assert (gpa["overall"], gpa["weighted_credits"], gpa["earned_credits"]) == (4.0, 4.0, 27.0)
assert [item["label"] for item in gpa["semesters"]] == ["2025-2026学年夏季", "2025-2026学年春季"]
assert len(courses) == 2 and courses[0]["credits"] == 4.0 and courses[0]["term"] == "2024-2025-1" and courses[0]["semester"] == "2024-fall"
assert courses[0]["published_at"].startswith("2025-01-24T15:03:27") and courses[1]["point"] is None

document = reader["plan"](PLAN)
assert document["title"] == "本科 普通本科生 信息科学与技术学院 电子信息工程 专业培养计划(2026)"
assert [group["path"] for group in document["groups"]] == [["人文社科通识课程", "思政理论课", "思政必修课"], ["人文社科通识课程", "创意与艺术课程群"]]
assert [(course["code"], course["credits"], course["terms"], course["required"]) for course in document["groups"][0]["courses"]] == [("MT1024", 2.0, [1, 2], True)]
assert document["groups"][1]["courses"][0]["terms"] == [4] and document["groups"][1]["courses"][0]["required"] is False
assert document["groups"][0]["courses"][0]["note"] == "大一大二需参加讲座"
assert [course["title"] for group in document["groups"] for course in group["courses"]] == ["形势与政策", "像素着色艺术"]

result = reader["fetch"](remote(httpx.MockTransport(handler)), {})
assert result["issues"] == [] and result["metadata"]["semester"] == "2026-2027学年秋季" and result["metadata"]["student_id"] == "15098"
assert result["metadata"]["exams"] == {"batch": "期末考试（考试周）", "batch_id": "9", "batches": [{"id": "9", "name": "期末考试（考试周）"}, {"id": "8", "name": "期中考试"}]}
assert len(result["assignments"]) == 2 and len(result["courses"]) == 2 and result["metadata"]["gpa"]["overall"] == 4.0
assert result["metadata"]["study_plan"]["groups"][0]["courses"][0]["code"] == "MT1024"
assert all(not result[kind] for kind in ("materials", "announcements", "posts", "lessons", "timetable", "messages"))


def broken(request):
    return httpx.Response(200, text="<html><body>maintenance</body></html>") if request.url.path == "/eams/myPlan.action" else handler(request)


second = reader["fetch"](remote(httpx.MockTransport(broken)), result)
assert second["issues"] == ["培养方案暂时无法读取，已保留上次数据。"] and second["metadata"]["study_plan"] == result["metadata"]["study_plan"] and len(second["courses"]) == 2


async def check_api():
    with sandbox("eams", handler) as context:
        app = FastAPI()
        app.include_router(package.create_router(context))
        context.store.write("snapshot", {"owner": digest("synthetic-account-one"), "data": validate_bundle(result), "updated_at": "2026-01-01T00:00:00+00:00"})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            snapshot = (await client.get("/snapshot")).json()
            assert snapshot["data"]["metadata"]["student_id"] == "15098" and len(snapshot["data"]["assignments"]) == 2
            same = (await client.get("/exams?semester_id=282")).json()
            assert same["batch"] == "期末考试（考试周）" and len(same["exams"]) == 2
            older = (await client.get("/exams?semester_id=262&batch_id=8")).json()
            assert older["semester"] == "2025-2026学年秋季" and older["batch"] == "期中考试" and older["batch_id"] == "8" and len(older["exams"]) == 2
            assert (await client.get("/exams?semester_id=abc")).status_code == 422
            answer = (await client.post("/ask", json={"question": "本学期有哪些考试？"})).json()
            assert answer["answer"] == "合成回答" and answer["model"] == "synthetic"
            assert (await client.post("/ask", json={"question": ""})).status_code == 422
        package.stop(context)


asyncio.run(check_api())
print("eams: throttling retry, exam/grade/plan parsing, per-panel fallback and public API passed")
