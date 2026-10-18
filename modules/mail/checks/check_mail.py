import sys
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from checks.module_support import load, sandbox

package = load("mail")
reader = sys.modules[package.__name__ + ".reader"]
html = '<p onclick="bad()">课程<br>通知</p><table><tr><td colspan="2">地点</td></tr></table><script>bad()</script><a href="javascript:bad()">链接</a><img src="https://tracking.example/" alt="示意图">'
body = reader.presentation(html)
assert '<table>' in body["body_html"] and '<br/>' in body["body_html"]
assert not any(value in body["body_html"] for value in ('onclick', 'javascript:', 'tracking.example', '<script'))


def handler(request):
    if request.url.params.get("func") == "mbox:listMessages":
        return httpx.Response(200, json={"code":"S_OK", "var":[{"id":"m1","subject":"课程通知","receivedDate":"2026-10-01 08:00:00","from":{"name":"合成发件人","email":"synthetic@example.edu"}}, {"subject":"缺少标识"}]})
    assert b'markRead=false' in request.content
    return httpx.Response(200, json={"code":"S_OK", "var":{"mail":{"mainPartData":{"content":html}}}})


imap_message = EmailMessage()
imap_message["Subject"] = "IMAP 课程通知"
imap_message["From"] = "合成 IMAP 发件人 <imap@example.edu>"
imap_message["Date"] = "Sat, 18 Oct 2026 09:00:00 +0800"
imap_message.set_content("纯文本正文")
imap_message.add_alternative('<p>IMAP 课程通知</p><script>bad()</script><img src="https://tracking.example/pixel" alt="示意图"><p>请在周一提交。</p>', subtype="html")
imap_message.add_attachment(b"synthetic-attachment", maintype="application", subtype="octet-stream", filename="说明.txt")
IMAP_RAW = imap_message.as_bytes()


class SyntheticImap:
    """Only the IMAP commands used by the module; no network or credentials."""
    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b"10 11"]
        if command == "FETCH" and "HEADER.FIELDS" in str(args[1]):
            parts = []
            for uid in str(args[0]).split(","):
                flags = b"\\Seen" if uid == "11" else b""
                subject = b"IMAP notice" if uid == "11" else b"IMAP unread notice"
                header = b"From: IMAP sender <imap@example.edu>\r\nSubject: " + subject + b"\r\nDate: Sat, 18 Oct 2026 09:00:00 +0800\r\n\r\n"
                prefix = b'1 (UID ' + uid.encode() + b' FLAGS (' + flags + b') BODY[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)] {' + str(len(header)).encode() + b'}'
                parts.extend([(prefix, header), b")"])
            return "OK", parts
        if command == "FETCH" and str(args[1]) == "(BODY.PEEK[])":
            return "OK", [(b'1 (UID 11 BODY[] {' + str(len(IMAP_RAW)).encode() + b'}', IMAP_RAW), b")"]
        raise AssertionError((command, args))


with sandbox("mail", handler) as context:
    app = FastAPI()
    app.include_router(package.create_router(context))
    source = package._source
    try:
        source.run()
        assert source.snapshot()["status"] == "partial"
        assert source.snapshot()["data"]["messages"][0]["received_at"].endswith('+08:00')
        with TestClient(app) as client:
            assert client.get('/labels').json()["labels"]["mail:m1"]["by"] == 'rule'
            assert client.get('/message',params={"message_id":"mail:m1"}).status_code == 200
            assert '课程' in source.snapshot()["data"]["messages"][0]["body_text"]
            assert client.post('/labels',json={"message_id":"mail:m1","label":"我的分类"}).status_code == 200
            client.post('/classify')
            assert client.get('/labels').json()["labels"]["mail:m1"]["by"] == 'manual'
            token = client.post('/agent/token').json()["token"]
            headers = {"Authorization":"Bearer " + token}
            assert client.get('/agent/pending').status_code == 401
            assert client.get('/agent/pending',headers=headers).status_code == 200
            assert client.post('/labels',headers=headers,json={"message_id":"mail:m1","label":"Agent"}).status_code == 409
            context.ai.result["content"] = {"labels":[{"message_id":"mail:m1","label":"AI分类","reason":"合成"}]}
            assert client.post('/ai-classify',json={"message_ids":["mail:m1"]}).status_code == 200
            assert client.get('/labels').json()["labels"]["mail:m1"]["label"] == '我的分类'
            context.ai.result["content"] = {"labels":[{"message_id":"other","label":"非法"}]}
            assert client.post('/ai-classify',json={"message_ids":["mail:m1"]}).status_code == 502
            owner = source.owner()
            context.auth.revision = 'second-account'
            from fastapi import HTTPException
            try:
                package.save(context,'labels',{'mail:m1':{'label':'旧账号'}},owner)
                raise AssertionError('Account changes must reject stale writes')
            except HTTPException as error:
                assert error.status_code == 409
            assert client.get('/labels').json()["labels"] == {}
            assert client.get('/agent/pending',headers=headers).status_code == 401
        context.auth.mailbox = SyntheticImap()
        source.run()
        snapshot = source.snapshot()
        assert snapshot["status"] in {"ready", "partial"} and snapshot["data"]["metadata"]["transport"] == "imap"
        imap_messages = snapshot["data"]["messages"]
        assert [item["source_id"] for item in imap_messages] == ["11", "10"]
        assert imap_messages[0]["received_at"].endswith("+08:00") and imap_messages[0]["unread"] is False and imap_messages[1]["unread"] is True
        with TestClient(app) as client:
            detail = client.get('/message',params={"message_id":"mail:11"})
            assert detail.status_code == 200
            assert '请在周一提交' in detail.json()["body_text"]
            assert 'tracking.example' not in detail.json()["body_html"] and '<script' not in detail.json()["body_html"]
            assert detail.json()["attachments"][0]["name"] == "说明.txt"
    finally:
        package.stop(context)
print('mail: HTML sanitization, malformed entries, body caching, manual priority, AI validation and scoped Agent tokens passed')
