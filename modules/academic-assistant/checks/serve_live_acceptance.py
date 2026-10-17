"""Opt-in real-model browser acceptance with synthetic accounts and separate storage.

This is deliberately outside check_*.py: the ordinary suite never spends model quota.
Only the configured DeepSeek key is read, kept in memory, and used by the normal AI service.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import uvicorn
from fastapi.responses import HTMLResponse

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))

from backend.core.store import Store
from backend.core.vault import Vault
from backend.main import create_app
from backend.services.campus.data import digest, validate_bundle
from checks.check_framework import MemoryVault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credential-store', type=Path, required=True, help='Existing encrypted vault; only ai:deepseek is read.')
    parser.add_argument('--source-port', type=int, default=16666, help='Read current AI model settings from this existing app.')
    parser.add_argument('--port', type=int, default=18766)
    parser.add_argument('--data-dir', type=Path, default=PROJECT / '.codex' / 'live-study-acceptance')
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    if not directory.is_relative_to((PROJECT / '.codex').resolve()):
        parser.error('Acceptance storage must stay inside this checkout .codex directory.')
    if args.port == args.source_port:
        parser.error('Use a separate acceptance port.')
    settings = httpx.get(f'http://127.0.0.1:{args.source_port}/api/v1/ai/settings', trust_env=False).raise_for_status().json()
    if not settings['enabled'] or not settings['key_saved']:
        parser.error('The existing app has no enabled AI connection.')
    vault = MemoryVault()
    vault.save('ai:deepseek', Vault(args.credential_store.resolve()).get('ai:deepseek'))
    directory.mkdir(parents=True, exist_ok=True)
    store = Store(directory / 'state.sqlite3')
    selected = {'academic-assistant', 'assignments', 'blackboard', 'courses', 'dashboard', 'eams', 'gradescope', 'notifications', 'timetable'}
    store.write('modules', {path.name: path.name in selected for path in (PROJECT / 'modules').iterdir() if path.is_dir()})
    store.write('ai:settings', {'enabled': True, 'model': settings['model']})
    revision = lambda provider: 'live-acceptance-synthetic-' + provider
    owner = lambda provider: digest(revision(provider))
    now = datetime.now(timezone.utc).isoformat()
    if not store.read('acceptance:seeded', False):
        course = {'id': 'blackboard:acceptance-math', 'source': 'blackboard', 'title': '测试高等数学', 'code': 'QA101', 'term': '2026-fall'}
        task = {'id': 'blackboard:acceptance-homework', 'source': 'blackboard', 'title': '测试高数作业1', 'course_id': course['id'],
                'due_at': '2026-10-21T22:00:00+08:00', 'submitted': False, 'actionable': True, 'body_text': '合成验收作业，不对应真实课程。'}
        lessons = [{'id': 'timetable:acceptance-math', 'source': 'timetable', 'title': '测试高等数学', 'weekday': 1, 'period_start': 3, 'period_end': 4, 'weeks': [1, 2, 3, 4], 'location': '测试教室A'},
                   {'id': 'timetable:acceptance-algebra', 'source': 'timetable', 'title': '测试线性代数', 'weekday': 2, 'period_start': 3, 'period_end': 4, 'weeks': [1, 2, 3, 4], 'location': '测试教室B'}]
        periods = [{'period': 3, 'start': '10:15', 'end': '11:00'}, {'period': 4, 'start': '11:10', 'end': '11:55'}]
        for module, provider, bundle in [('blackboard', 'ids', {'courses': [course], 'assignments': [task]}), ('gradescope', 'gradescope', {}), ('eams', 'ids', {}),
                                         ('timetable', 'ids', {'timetable': lessons, 'metadata': {'semester': '2026-2027学年秋季', 'semester_id': 'acceptance-2026', 'units': 13, 'week_count': 4, 'periods': periods}})]:
            local = store.for_module(module)
            local.write('snapshot', {'owner': owner(provider), 'data': validate_bundle(bundle), 'updated_at': now})
            local.write('sync', {'owner': owner(provider), 'status': 'ready'})
            if module == 'timetable':
                local.write('semester:' + owner('ids') + ':acceptance-2026', {'week_one': '2026-10-19'})
                local.write('school-calendar:2026', {'checked_at': now, 'terms': {'2026-fall': {'week_one': '2026-10-19', 'closures': []}}})
            local.close()
        store.write('acceptance:seeded', True)
    app = create_app(active_port=args.port, store=store, vault=vault, modules_root=PROJECT / 'modules', data_dir=directory)
    run_model = app.state.ai.run
    def record_result(**options):
        result = run_model(**options)
        # Synthetic content only. Never record plugin_env, headers or credentials.
        with (directory / 'model-results.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at': datetime.now(timezone.utc).isoformat(), 'content': result['content'],
                                     'tools': result['tools'], 'model': result['model']}, ensure_ascii=False) + '\n')
        return result
    app.state.ai.run = record_result
    original_status = app.state.auth.get_status
    def status(provider=None):
        if provider is None:
            return {'providers': [status(name) for name in ('ids', 'coremail', 'gradescope', 'piazza')]}
        return {**original_status(provider), 'username': 'synthetic-acceptance@example.invalid', 'account_revision': revision(provider),
                'identity_verified': True, 'has_password': False, 'has_session': False, 'status': 'ready'}
    app.state.auth.get_status = status
    app.state.auth.get_account_revision = revision
    def no_school_requests(*args, **kwargs):
        raise RuntimeError('Acceptance accounts cannot contact school services; use the seeded synthetic data.')
    app.state.auth.read_with_recovery = no_school_requests
    async def entry(scope, receive, send):
        # Extension-origin top-level navigation is cross-site. This static link starts
        # a normal same-origin navigation without weakening the app's own middleware.
        if scope['type'] == 'http' and scope['path'] == '/acceptance-start' and scope['method'] == 'GET':
            headers = dict(scope.get('headers', []))
            if headers.get(b'host') == f'127.0.0.1:{args.port}'.encode():
                response = HTMLResponse('<!doctype html><meta charset="utf-8"><title>合成数据验收入口</title><h1>主页 AI 对话验收</h1><p>独立测试账号与合成数据，使用真实模型。</p><a href="/">进入测试工作台</a>')
                await response(scope, receive, send)
                return
        if scope['type'] == 'http' and '/tools/' in scope['path']:
            request_bytes, response_bytes, response_status = [], [], 200
            async def capture_receive():
                message = await receive()
                if message['type'] == 'http.request':
                    request_bytes.append(message.get('body', b''))
                return message
            async def capture_send(message):
                nonlocal response_status
                if message['type'] == 'http.response.start':
                    response_status = message['status']
                if message['type'] == 'http.response.body' and response_status >= 400:
                    response_bytes.append(message.get('body', b''))
                await send(message)
            await app(scope, capture_receive, capture_send)
            if response_status >= 400:
                with (directory / 'tool-failures.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'path': scope['path'], 'request': b''.join(request_bytes).decode(),
                                             'status': response_status, 'response': b''.join(response_bytes).decode()}, ensure_ascii=False) + '\n')
        else:
            await app(scope, receive, send)
    print(f'Acceptance app: http://127.0.0.1:{args.port}/acceptance-start - synthetic data, real {settings["model"]}', flush=True)
    uvicorn.run(entry, host='127.0.0.1', port=args.port, log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
