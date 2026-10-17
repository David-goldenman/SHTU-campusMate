"""Provider configuration, credential separation and official adapter routing, using synthetic data."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from checks.check_ai import Memory
from backend.services.ai import AIService
from backend.services.ai.provider import complete_with_harness
from backend.services.ai.routes import AISettings


def main():
    service = AIService(Memory(), Memory())
    catalog = service.catalog()
    assert len(catalog['providers']) == 39 and len(catalog['protocols']) == 3
    service.save_settings(AISettings(api_key='synthetic-deepseek-key'))
    saved = service.save_settings(AISettings(provider='openai', model='gpt-4', api_key='synthetic-openai-key'))
    assert saved['enabled'] and saved['provider'] == 'openai' and saved['key_saved']
    assert 'synthetic' not in json.dumps(saved) and 'synthetic' not in json.dumps(service.store.values)
    service.save_settings(AISettings(provider='deepseek'))
    assert service.vault.get('ai:deepseek')['api_key'] == 'synthetic-deepseek-key'
    assert service.vault.get('ai:provider:openai')['api_key'] == 'synthetic-openai-key'
    for fields in ({'provider':'unknown','model':'m'}, {'base_url':'https://elsewhere.example'},
                   {'provider':'test','custom':True,'model':'m','base_url':'http://example.com'},
                   {'provider':'test','custom':True,'model':'m','base_url':'https://key@example.com'},
                   {'provider':'test','custom':True,'model':'m','base_url':'https://example.com/?key=secret'}):
        try:
            service.save_settings(AISettings(**fields))
            raise AssertionError(fields)
        except HTTPException as error:
            assert error.status_code == 400
    service.save_settings(AISettings(provider='test',custom=True,model='m',base_url='https://example.com/v1',api_key='synthetic-custom-key'))
    try:
        service.save_settings(AISettings(base_url='https://changed.example/v1'))
        raise AssertionError('Endpoint changes must not reuse a credential')
    except HTTPException as error:
        assert error.status_code == 400
    service.delete_provider('test')
    assert not service.settings()['enabled'] and not service.vault.get('ai:provider:test')
    assert service.vault.get('ai:deepseek')

    calls = []
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, body))
            assert self.headers['Authorization'] == 'Bearer synthetic-model-key'
            assert body['model'] == 'synthetic-model'
            assert body['messages'][0]['role'] == 'system'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            frames = [{'id':'test','object':'chat.completion.chunk','choices':[{'index':0,'delta':{'role':'assistant','content':'合成摘要'},'finish_reason':None}]},
                      {'id':'test','choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}}]
            for frame in frames:
                self.wfile.write(('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n').encode())
            self.wfile.write(b'data: [DONE]\n\n')

    project = Path(__file__).resolve().parents[1]
    temporary = project / '.codex/tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1',0),Model)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(dir=temporary) as name:
            config = {'provider':'synthetic-gateway','custom':True,'protocol':'openai-completions',
                      'model':'synthetic-model','base_url':f'http://127.0.0.1:{server.server_port}/v1','key_saved':True}
            result = complete_with_harness([{'role':'system','content':'合成指令'}, {'role':'user','content':'合成问题'}], config, 'synthetic-model-key', Path(name))
            assert result['content'] == '合成摘要' and calls[0][0] == '/v1/chat/completions'
    finally:
        server.shutdown();server.server_close();thread.join()
    print('PASS: official provider catalog, automatic enable, credential separation, endpoint validation and native adapter completion')


if __name__ == '__main__':
    main()
