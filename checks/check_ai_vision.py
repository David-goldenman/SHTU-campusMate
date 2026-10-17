"""Independent image credentials and real Harness image transport to a local fake API."""
import base64
import io
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from PIL import Image
from checks.check_ai import Memory
from backend.services.ai import AIService
from backend.services.ai.routes import AISettings, VisionSettings


def main():
    calls = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, body, self.headers.get('Authorization') or self.headers.get('x-api-key')))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            content = json.dumps({'text': 'SYNTHETIC PAGE 42', 'description': '', 'uncertain': ''})
            path = self.path.split('?', 1)[0]
            if path.endswith('/responses'):
                item={'type':'message','id':'msg_synthetic','role':'assistant','status':'completed','content':[{'type':'output_text','text':content,'annotations':[]}]}
                frames=[{'type':'response.created','response':{'id':'resp_synthetic','status':'in_progress','output':[]}},
                        {'type':'response.output_item.added','output_index':0,'item':{**item,'content':[],'status':'in_progress'}},
                        {'type':'response.content_part.added','output_index':0,'content_index':0,'item_id':item['id'],'part':{'type':'output_text','text':'','annotations':[]}},
                        {'type':'response.output_text.delta','output_index':0,'content_index':0,'item_id':item['id'],'delta':content},
                        {'type':'response.output_item.done','output_index':0,'item':item},
                        {'type':'response.completed','response':{'id':'resp_synthetic','status':'completed','output':[item],'usage':{'input_tokens':2,'output_tokens':3,'total_tokens':5}}}]
            elif path.endswith('/messages'):
                frames=[{'type':'message_start','message':{'id':'msg_synthetic','type':'message','role':'assistant','model':'synthetic-vision','content':[],'usage':{'input_tokens':2,'output_tokens':0}}},
                        {'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}},
                        {'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':content}},
                        {'type':'content_block_stop','index':0},
                        {'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':3}},
                        {'type':'message_stop'}]
            else:
                frames = [{'id':'test','object':'chat.completion.chunk','choices':[{'index':0,'delta':{'role':'assistant','content':content},'finish_reason':None}]},
                          {'id':'test','choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}}]
            for frame in frames:
                self.wfile.write((('event: '+frame['type']+'\n' if 'type' in frame else '')+'data: '+json.dumps(frame)+'\n\n').encode())
            if path.endswith('/chat/completions'):
                self.wfile.write(b'data: [DONE]\n\n')

    temporary = Path(__file__).resolve().parents[1] / '.codex/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(dir=temporary) as name:
            service = AIService(Memory(), Memory())
            service.harness = SimpleNamespace(modules=SimpleNamespace(data=Path(name)))
            service.save_settings(AISettings(api_key='synthetic-chat-key'))
            image = io.BytesIO()
            Image.new('RGB', (96,96), 'white').save(image, format='PNG')
            images = [{'media_type':'image/png','data':base64.b64encode(image.getvalue()).decode('ascii')}]
            base_url = f'http://127.0.0.1:{server.server_port}/v1'
            fields = dict(enabled=True, base_url=base_url, model='synthetic-vision', supports_images=True, quality_confirmed=False, api_key='synthetic-image-key')
            saved = service.save_vision_settings(VisionSettings(**fields))
            assert not saved['ready'] and service.settings()['provider'] == 'deepseek'
            try:
                service.vision('read',images,expected_revision=saved['revision'])
                raise AssertionError('Unconfirmed quality must not send images')
            except HTTPException as error:
                assert error.status_code == 409 and not calls
            saved = service.save_vision_settings(VisionSettings(**{**fields,'quality_confirmed':True}))
            assert saved['ready'] and 'synthetic-image-key' not in json.dumps(saved)
            assert 'synthetic-image-key' not in json.dumps(service.store.values)
            result = service.vision('Read the synthetic page',images,expected_revision=saved['revision'])
            assert json.loads(result['content'])['text'] == 'SYNTHETIC PAGE 42'
            path, body, key = calls[0]
            assert path == '/v1/chat/completions' and key == 'Bearer synthetic-image-key'
            assert body['model'] == 'synthetic-vision'
            assert any(part.get('type') == 'image_url' and part['image_url']['url'].startswith('data:image/')
                       for message in body['messages'] if isinstance(message['content'],list) for part in message['content'])
            for protocol, suffix in [('openai-responses','/responses'), ('anthropic-messages','/messages')]:
                configured=service.save_vision_settings(VisionSettings(**{**fields,'quality_confirmed':True,'protocol':protocol}))
                result=service.vision('Read the synthetic page',images,expected_revision=configured['revision'])
                assert json.loads(result['content'])['text']=='SYNTHETIC PAGE 42'
                assert calls[-1][0].split('?', 1)[0].endswith(suffix) and 'image' in json.dumps(calls[-1][1])
            try:
                service.save_vision_settings(VisionSettings(**{**fields,'base_url':'https://another.example/v1','api_key':None}))
                raise AssertionError('Keys must not follow changed endpoints')
            except HTTPException as error:
                assert error.status_code == 400
            service.save_settings(AISettings(enabled=False))
            assert not service.vision_settings()['ready']
            assert service.vault.get('ai:deepseek')['api_key'] == 'synthetic-chat-key'
            service.save_vision_settings(VisionSettings(base_url=base_url,delete_key=True))
            assert not service.vault.get('ai:vision')
    finally:
        server.shutdown();server.server_close();thread.join()
    print('PASS: image capability/quality gating, independent secrets, endpoint changes, pause and native Harness image transport')


if __name__ == '__main__':
    main()
