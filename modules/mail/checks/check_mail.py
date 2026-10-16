import sys
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
    finally:
        package.stop(context)
print('mail: HTML sanitization, malformed entries, body caching, manual priority, AI validation and scoped Agent tokens passed')
