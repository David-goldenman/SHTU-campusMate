import asyncio
import sys
import threading
from contextlib import contextmanager
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
assert first["course_id"] == "eams:grade:2025-fall:CHEM1120.03" and first["id"].startswith("eams:") and items[1]["note"] == "带计算器"
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

# A repeated section in another year or season is a distinct grade record.
retakes = """<tr><td>2025-2026</td><td>1</td><td>GEMA1001</td><td>GEMA1001.01</td><td>高等数学I</td><td>小组</td><td>4</td><td>D</td><td>1.0</td><td>2026-01-24 15:03:27</td></tr>
<tr><td>2025-2026</td><td>2</td><td>GEMA1001</td><td>GEMA1001.01</td><td>高等数学I</td><td>小组</td><td>4</td><td>C</td><td>2.0</td><td>2026-06-24 15:03:27</td></tr>"""
retake_gpa, retake_courses = reader["grades"](GRADES.rsplit("</table>", 1)[0] + retakes + "</table>")
normalized = validate_bundle({"courses": retake_courses})["courses"]
assert len(normalized) == 4 and len({course["id"] for course in normalized}) == 4
assert retake_gpa["overall"] == round(sum(course["point"] * course["credits"] for course in normalized if course["point"] is not None) / 12, 3)
assert retake_gpa["weighted_credits"] == 12
for term, course in zip(("2024-2025学年秋季", "2025-2026学年秋季", "2025-2026学年春季"), (normalized[0], normalized[2], normalized[3])):
    linked = reader["exams"](EXAMS.replace("CHEM1120.03", "GEMA1001.01"), term, "https://eams.shanghaitech.edu.cn/")
    assert linked[0]["course_id"] == course["id"]

document = reader["plan"](PLAN)
assert document["title"] == "本科 普通本科生 信息科学与技术学院 电子信息工程 专业培养计划(2026)"
assert [group["path"] for group in document["groups"]] == [["人文社科通识课程", "思政理论课", "思政必修课"], ["人文社科通识课程", "创意与艺术课程群"]]
assert [(course["code"], course["credits"], course["terms"], course["required"]) for course in document["groups"][0]["courses"]] == [("MT1024", 2.0, [1, 2], True)]
assert document["groups"][1]["courses"][0]["terms"] == [4] and document["groups"][1]["courses"][0]["required"] is False
assert document["groups"][0]["courses"][0]["note"] == "大一大二需参加讲座"
assert [course["title"] for group in document["groups"] for course in group["courses"]] == ["形势与政策", "像素着色艺术"]
assert '非必修课' in document['notes'][0]
with_credits = reader['plan'](PLAN.replace('<tr><td colspan="6">备注', '<tr><td>应修学分</td><td>145</td></tr><tr><td colspan="6">备注'))
assert with_credits['requirements'][0]['text'] == '应修学分 145'
catalogue = '''<table class="gridtable"><tr><th></th><th>代码</th><th>名称</th><th>学分</th><th>操作</th></tr><tr><td></td><td>DEMO100</td><td>合成课程</td><td>4</td><td><a href="/eams/courseSearchOther!info.action?syllabusIds=9">课程</a></td></tr></table><script>page.pageInfo(1,20,1);</script>'''
catalogue_result = package.search.__globals__['courses'](catalogue)
assert catalogue_result['scope'] == 'course_catalog' and catalogue_result['total'] == 1
assert catalogue_result['items'][0]['syllabus_id'] == 9 and catalogue_result['items'][0]['credits'] == 4

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

# Permission/missing-page failures affect only the failed panel, not the full sync.
previous = {"courses": [{"id": "eams:old-grade", "source": "eams"}], "assignments": [{"id": "eams:old-exam", "source": "eams"}],
            "metadata": {"gpa": {"overall": 1.0}, "study_plan": {"title": "旧培养方案"}, "semesters": result["metadata"]["semesters"]}}
for path, label, panel in [("/eams/myPlan.action", "培养方案", "plan"),
                           ("/eams/teach/grade/course/person!historyCourseGrade.action", "学期成绩", "grades"),
                           ("/eams/stdExamTable!examTable.action", "考试安排", "exams"),
                           ("/eams/dataQuery.action", "学期目录", "catalogue")]:
    for status in (403, 404):
        def unavailable(request):
            return httpx.Response(status) if request.url.path == path else handler(request)

        partial = reader["fetch"](remote(httpx.MockTransport(unavailable)), previous)
        assert partial["issues"] == [label + "暂时无法读取，已保留上次数据。"]
        assert partial["courses"] == (previous if panel == "grades" else result)["courses"]
        assert partial["assignments"] == (previous if panel == "exams" else result)["assignments"]
        assert partial["metadata"]["gpa"] == (previous if panel == "grades" else result)["metadata"]["gpa"]
        assert partial["metadata"]["study_plan"] == (previous if panel == "plan" else result)["metadata"]["study_plan"]
        assert partial["metadata"]["semesters"] == result["metadata"]["semesters"]

def expired(request):
    return httpx.Response(401) if request.url.path == "/eams/myPlan.action" else handler(request)

try:
    reader["fetch"](remote(httpx.MockTransport(expired)), previous)
    raise AssertionError("登录失效必须传播给共享登录恢复，不能当作板块降级")
except LoginRequired:
    pass


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


async def check_account_switch():
    with sandbox("eams", handler) as context:
        app = FastAPI()
        app.include_router(package.create_router(context))
        context.store.write("snapshot", {"owner": digest(context.auth.revision), "data": validate_bundle(result), "updated_at": None})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            # A snapshot read must not become the next account's cached response.
            snapshot = package._source.snapshot

            def switched_snapshot():
                value = snapshot()
                context.auth.revision = "synthetic-account-two"
                return value

            package._source.snapshot = switched_snapshot
            for method, url, kwargs in [("GET", "/exams?semester_id=282", {}), ("POST", "/ask", {"json": {"question": "绩点？"}})]:
                context.auth.revision = "synthetic-account-one"
                response = await client.request(method, url, **kwargs)
                assert response.status_code == 409 and "15098" not in response.text
            package._source.snapshot = snapshot

            # Detect changes both while opening the authenticated client and after I/O.
            authenticated_client = context.auth.authenticated_client
            for stage in ("open", "close"):
                context.auth.revision = "synthetic-account-one"
                requests = []

                def record(request):
                    requests.append(request)
                    return handler(request)

                context.auth.transport = httpx.MockTransport(record)

                @contextmanager
                def switched_client(*args, **kwargs):
                    with authenticated_client(*args, **kwargs) as connection:
                        if stage == "open":
                            context.auth.revision = "synthetic-account-two"
                        yield connection
                    if stage == "close":
                        context.auth.revision = "synthetic-account-two"

                context.auth.authenticated_client = switched_client
                response = await client.get("/exams?semester_id=262&batch_id=8")
                assert response.status_code == 409 and "大学化学" not in response.text
                assert len(requests) == (0 if stage == "open" else 2)
            context.auth.authenticated_client = authenticated_client

            # Switching accounts while AI is running must discard the old answer.
            context.auth.revision = "synthetic-account-one"
            entered, release = threading.Event(), threading.Event()

            def delayed_chat(**kwargs):
                entered.set()
                assert release.wait(5), "AI fixture was not released"
                return {"content": "private-old-account-answer"}

            context.ai.chat = delayed_chat
            pending = asyncio.create_task(client.post("/ask", json={"question": "绩点？"}))
            try:
                assert await asyncio.to_thread(entered.wait, 5), "AI fixture did not start"
                context.auth.revision = "synthetic-account-two"
            finally:
                release.set()
            response = await pending
            assert response.status_code == 409 and "private-old-account-answer" not in response.text

            # A job queued before the switch must not send the stale data to AI.
            context.auth.revision = "synthetic-account-one"
            entered.clear()
            run_in_threadpool = package.run_in_threadpool

            async def switched_threadpool(function, *args, **kwargs):
                context.auth.revision = "synthetic-account-two"
                return await run_in_threadpool(function, *args, **kwargs)

            package.run_in_threadpool = switched_threadpool
            try:
                assert (await client.post("/ask", json={"question": "绩点？"})).status_code == 409
                assert not entered.is_set()
            finally:
                package.run_in_threadpool = run_in_threadpool
        package.stop(context)


asyncio.run(check_api())
asyncio.run(check_account_switch())
print("eams: parsing, semester grade identities, panel 403/404 fallback, login propagation and account-switch isolation passed")
