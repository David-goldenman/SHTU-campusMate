"""Synthetic school APIs for the integrated app and browser verification."""
import html
import json
from contextlib import asynccontextmanager, contextmanager

import httpx

from backend.core.store import Store
from backend.main import create_app
from checks.check_framework import MemoryVault

PDF = b"%PDF-1.4\nsynthetic course material\n%%EOF"


def school(request):
    host, path = request.url.host, request.url.path
    if host == "mail.shanghaitech.edu.cn":
        if path.endswith("readMessage.jsp"):
            assert b"markRead=false" in request.content
            return httpx.Response(200, json={"code": "S_OK", "var": {"mail": {"mainPartData": {"content": '<p>实验课地点调整为教学楼 101。<br>请按时参加。</p><script>bad()</script><img src="https://tracking.example/">'}, "attachments": []}}})
        return httpx.Response(200, json={"code": "S_OK", "var": [{"id": "m1", "subject": "程序设计课程通知", "from": "合成教务", "receivedDate": "2026-10-16 09:00:00", "flags": {"read": False}}, {"id": "m2", "subject": "校园讲座报名", "from": "合成校园服务", "receivedDate": "2026-10-15 14:00:00", "flags": {"read": True}}], "total": 2})
    if host == "eams.shanghaitech.edu.cn":
        if path.endswith("dataQuery.action"):
            return httpx.Response(200, text='{id:1,schoolYear:"2026-2027",name:"1"}')
        if "!courseTable.action" in path:
            mask = "0" * 34 + "1" * 18 + "0"
            return httpx.Response(200, text=f'''<table><tr><td>CS100</td><td><a class="cs-detail-link" data-course-id="11">程序设计</a></td></tr></table><script>
var table=new CourseTable(2026,91);var unitCount=13;var teachers=[{{name:"合成教师"}}];
activity=new TaskActivity(t.join(','),n.join(','),"11(CS100)","程序设计","1","教学楼101","{mask}",null);
index=1*unitCount+4;index=1*unitCount+5;table.marshalTable(35,1,18);</script>''')
        return httpx.Response(200, text='bg.form.addInput(form,"ids","123");semesterCalendar({value:"1"});')
    if host == "www.gradescope.com":
        if path == "/account":
            return httpx.Response(200, text='<div id="account-show"><h3 class="courseList--term">Fall 2026</h3><div><a class="courseBox" href="/courses/1001"><span class="courseBox--name">程序设计</span><span class="courseBox--shortname">CS 100</span></a></div></div>')
        if path == "/courses/1001":
            return httpx.Response(200, text='''<table id="assignments-student-table"><tbody><tr><td class="table--primaryLink"><button data-assignment-id="2101">实验作业一</button></td><td class="submissionStatus">No Submission</td><td><time class="submissionTimeChart--dueDate" datetime="2026-10-20T12:00:00+08:00"></time></td></tr><tr><td class="table--primaryLink">预告作业</td><td class="submissionStatus">No Submission</td><td><time class="submissionTimeChart--releaseDate" datetime="2099-10-20T12:00:00+08:00"></time></td></tr></tbody></table>''')
        if "/assignments/2101/" in path:
            props = {"assignment": {"title": "实验作业一", "submission_allowed": True, "submission_format": "online", "template_url": "https://production-gradescope-uploads.s3-us-west-2.amazonaws.com/statement.pdf"}, "questions": [{"content": "编写并解释一个合成程序。"}]}
            return httpx.Response(200, text='<div data-react-class="AssignmentSubmissionViewer" data-react-props="' + html.escape(json.dumps(props), quote=True) + '"></div>')
    if host == "production-gradescope-uploads.s3-us-west-2.amazonaws.com":
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    if host == "elearning.shanghaitech.edu.cn":
        if "/portal/" in path:
            return httpx.Response(200, text='<div id="module:_185_1"><a href="/launcher?type=Course&amp;id=_101_1">CS100 2026-2027学年秋季学期</a></div><div id="module:_186_1"></div>')
        if path.endswith("users/me/courses"):
            return httpx.Response(200, json={"results": [{"courseId": "_101_1"}]})
        if path.endswith("courses/_101_1"):
            return httpx.Response(200, json={"name": "程序设计", "courseId": "CS100"})
        if path.endswith("contents/_201_1/children"):
            return httpx.Response(200, json={"results": [{"id": "_202_1", "title": "讲义一.pdf", "parentId": "_201_1", "contentHandler": {"id": "resource/x-bb-file"}}, {"id": "_203_1", "title": "实验作业", "parentId": "_201_1", "contentHandler": {"id": "resource/x-bb-assignment"}, "availability": {"available": "Yes"}, "body": "<p>完成实验并在原站提交。</p>", "created": "2026-10-01T08:00:00+08:00"}]})
        if path.endswith("/contents"):
            return httpx.Response(200, json={"results": [{"id": "_201_1", "title": "第一章", "contentHandler": {"id": "resource/x-bb-folder"}, "hasChildren": True}]})
        if path.endswith("/attachments"):
            return httpx.Response(200, json={"results": [{"id": "_401_1", "fileName": "讲义一.pdf"}]})
        if path.endswith("/download") or path.startswith("/bbcswebdav/"):
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        if path.endswith("gradebook/users/me"):
            return httpx.Response(200, json={"results": [{"columnId": "_301_1", "displayGrade": {}}]})
        if path.endswith("gradebook/columns"):
            return httpx.Response(200, json={"results": [{"id": "_301_1", "contentId": "_203_1", "name": "实验作业", "grading": {"due": "2026-10-20T12:00:00+08:00"}, "score": {"possible": 10}}]})
        if "myGrades" in path:
            return httpx.Response(200, text='<div id="grades_wrapper"><div id="301" class="sortable_item_row">No Submission</div></div>')
        if path.endswith("listContent.jsp"):
            return httpx.Response(200, text='<li id="contentListItem:_203_1"><a href="/bbcswebdav/synthetic/statement.pdf">作业说明.pdf</a></li>')
        if path.endswith("/announcement"):
            return httpx.Response(200, text='<form id="announcementForm"><ul id="announcementList"><li id="notice1"><h3 class="item">下周实验室调整</h3><div class="details"><div class="vtbegenerated">下周实验课在教学楼101进行。</div></div></li></ul></form>')
    if host == "piazza.com":
        method = request.url.params.get("method")
        if method == "user_profile.get_profile":
            return httpx.Response(200, json={"result": {"all_classes": {"pc1": {"nid": "pc1", "name": "程序设计讨论", "num": "CS100", "term": "Fall 2026"}}}})
        if method == "network.get_my_feed":
            return httpx.Response(200, json={"result": {"feed": [{"id": "p1", "nr": 1, "subject": "实验讨论与答疑", "snippet": "合成讨论摘要", "updated": "2026-10-16T08:00:00Z"}]}})
        return httpx.Response(200, json={"result": {"nr": 1, "history": [{"subject": "实验讨论与答疑", "content": "<p>请先阅读实验资料。</p>"}], "children": [{"id": "r1", "history": [{"content": "合成回复"}]}]}})
    if host == "elrc.shanghaitech.edu.cn":
        if path.endswith("semester/manage/current"):
            data = {"currentSemester": {"showSemester": "2026-2027-1", "startTime": "2026-08-31"}}
        elif path.endswith("participated/courses/list"):
            data = {"results": [{"entityData": {"contentId_": "ec1", "name_": "程序设计", "courseNumber": "CS100", "semester_show_name": "2026-2027学年秋季", "course_semester_id": "term1"}}]}
        elif path.endswith("get/course/details"):
            data = {"courseId": "rc1"}
        elif path.endswith("chapter/info"):
            data = [{"info": {"guid_": "chapter1", "chapter_name": "第一章", "chapter_describe": "课程简介"}, "childInfo": [{"info": {"guid_": "material1", "chapter_name": "课堂资料", "chapter_describe": "合成教学资料"}}]}]
        elif path.endswith("video/review/1"):
            data = {"results": [{"id": "video1", "courseId": "rc1", "courseName": "程序设计录播", "showSemester": "2026-2027-1"}]}
        elif path.endswith("recording/video/info"):
            data = {"courseName": "程序设计录播", "recordingVideoInfoShows": [{"week": 1, "recordInfoDetailList": [{"weekDate": "2026-09-01", "section": "5-6", "videoInfoList": [{"videoId": "stream1", "videoName": "教师全景"}, {"videoId": "student1", "videoName": "学生全景"}]}]}]}
        elif path.endswith("smart/voice/select"):
            data = {"data": [{"type": "model_sobey_smart_voice_", "metadata": [{"textLanguage": {"text_source": "合成课程转写。"}, "_in": 10000000, "_out": 20000000}]}]}
        elif path.endswith("knowledge/summary"):
            data = [{"chapterTitle": "课程要点", "chapterContent": "<p>合成课程摘要。</p>"}]
        else:
            raise AssertionError("Unrecognized synthetic ELRC path: " + path)
        return httpx.Response(200, json={"status": 200, "data": data})
    raise AssertionError("Unrecognized synthetic endpoint: " + host + path)


def ai_answer(**kwargs):
    if "context" in kwargs:
        data = json.loads(kwargs["context"])
        prompt = kwargs["prompt"]
    else:
        documents = [item["content"].split("\n", 1)[1] for item in kwargs["messages"] if item["content"].startswith("本次资料 JSON")]
        data, prompt = json.loads(documents[0]), "assistant"
    if isinstance(data, list):
        content = {"labels": [{"message_id": item["id"], "label": "教学与课程", "reason": "合成分类"} for item in data]}
    else:
        selected = next((item for item in data["items"] if item["kind"] == "announcements"), data["items"][0])
        if '"notifications"' in prompt:
            content = {"notifications": [{"title": "下周实验室调整", "summary": "请关注课程公告中的教室安排。", "importance": "important", "why": "影响上课地点", "event_at": None, "citation_ids": [selected["id"]]}]}
        else:
            content = {"text": "本学期课程与实验安排已整理，具体时间和地点请查看所附来源。", "insufficient_context": False, "citation_ids": [selected["id"]], "labels": []}
    return {"content": content, "model": "deepseek-flash", "usage": {"total_tokens": 17}}


def fixture_app(directory, port=18666):
    directory.mkdir(parents=True, exist_ok=True)
    store, vault = Store(directory / "settings.sqlite3"), MemoryVault()
    for provider in ("ids", "coremail", "gradescope", "piazza"):
        vault.save("auth:credentials:" + provider, {"username": "synthetic@example.edu", "password": "synthetic-password"})
        vault.save("auth:session:" + provider, {"cookies": [], "sid": "synthetic-sid"})
        store.write("auth:state:" + provider, {"status": "ready"})
    store.write("ai:settings", {"enabled": True, "model": "deepseek-flash"})
    vault.save("ai:deepseek", {"api_key": "synthetic-key"})
    app = create_app(active_port=port, store=store, vault=vault, data_dir=directory)
    app.state.ai.generate = ai_answer
    app.state.ai.chat = ai_answer
    app.state.auth.browser.close = lambda provider: None
    app.state.auth.browser.close_all = lambda: None
    app.state.fixture_requests = []

    def transport(request):
        app.state.fixture_requests.append(str(request.url))
        return school(request)

    @contextmanager
    def authenticated(provider, target=None, *, cancelled=None):
        with app.state.auth._client_lock(provider, cancelled):
            with httpx.Client(transport=httpx.MockTransport(transport)) as client:
                yield client

    app.state.auth.authenticated_client = authenticated
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            for entry in app.state.modules.entries.values():
                source = getattr(entry.package, "_source", None)
                if source is not None:
                    source.run()
                    value = source.snapshot()
                    assert value["status"] == "ready", (entry.info["id"], value, app.state.fixture_requests[-12:])
            yield

    app.router.lifespan_context = lifespan
    return app
