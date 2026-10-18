"""Synthetic setup diagnostics; no real QQ service or credentials."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load

qq = load('group-messages').qq


def check():
    client = qq.QQClient('http://127.0.0.1:3000', 'synthetic-secret')
    client.transport.retries = 0
    opener = client.transport.opener = SimpleNamespace(open=Mock())
    failures = [
        (HTTPError(client.base_url, 401, 'unauthorized', {}, None), 'auth', 'HTTP 服务端'),
        (HTTPError(client.base_url, 403, 'forbidden', {}, None), 'auth', '管理页面登录口令'),
        (HTTPError(client.base_url, 404, 'not found', {}, None), 'address', '地址和端口'),
        (URLError('synthetic-secret must not leak'), 'network', '先启动 NapCat'),
    ]
    for error, category, instruction in failures:
        opener.open.side_effect = error
        try:
            client.login_info()
        except qq.APIError as result:
            assert result.category == category and instruction in str(result)
            assert 'synthetic-secret' not in str(result)
        else:
            raise AssertionError('Expected a setup diagnostic')
    opener.open.side_effect = None
    for payload, category, instruction in [
        (b'<html>management page</html>', 'schema', '6099'),
        (json.dumps({'status': 'failed', 'retcode': 100}).encode(), 'account', '已登录'),
    ]:
        opener.open.return_value = io.BytesIO(payload)
        try:
            client.login_info()
        except qq.APIError as result:
            assert result.category == category and instruction in str(result)
        else:
            raise AssertionError('Expected a login diagnostic')
    opener.open.return_value = io.BytesIO(json.dumps({'status': 'ok', 'data': {'user_id': 123}}).encode())
    assert client.login_info() == {'user_id': 123}
    request = opener.open.call_args.args[0]
    assert request.get_header('Authorization') == 'Bearer synthetic-secret'
    assert request.full_url == 'http://127.0.0.1:3000/get_login_info'
    print('PASS: QQ setup diagnostics distinguish service, token, endpoint and login failures without exposing secrets')


if __name__ == '__main__':
    check()
