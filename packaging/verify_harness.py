"""Exercise the bundled interpreter and official Harness against a local synthetic model."""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--bundle',required=True,type=Path)
parser.add_argument('--temporary',required=True,type=Path)
args=parser.parse_args();bundle=args.bundle.resolve();sys.path.insert(0,str(bundle))
args.temporary.mkdir(parents=True,exist_ok=True)
os.environ['CAMPUS_PACKAGED']='1'
os.environ['CAMPUS_DATA_DIR']=str(args.temporary.resolve()/'framework')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from backend.services.ai import harness

requests=[]
class Model(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def handle(self):
        try:super().handle()
        except (ConnectionResetError,ConnectionAbortedError):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        requests.append(body)
        names={item['function']['name'] for item in body['tools']}
        assert 'order_deadlines' in names and 'study_query' not in names
        assert self.headers['Authorization']=='Bearer synthetic-release-key'
        first=not any(item['role']=='tool' for item in body['messages'])
        delta={'tool_calls':[{'index':0,'id':'fixture-sort','type':'function','function':{'name':'order_deadlines','arguments':json.dumps({'items':[{'id':'one','title':'Synthetic','due_at':'2026-11-01T12:00:00+08:00'}]})}}]} if first else {'content':'Synthetic release verified'}
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        for change,finish in ((delta,None),({},'tool_calls' if first else 'stop')):
            chunk={'id':'synthetic','object':'chat.completion.chunk','model':body['model'],'choices':[{'index':0,'delta':change,'finish_reason':finish}]}
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode());self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')


class Modules:
    def __init__(self,data):self.data=data
    @contextmanager
    def use_plugins(self,selected):
        assert selected==['deadlines']
        yield [SimpleNamespace(info={'id':'deadlines'},harness={'name':'campus-deadlines','folder':bundle/'modules'/'deadlines'/'harness','bundle':False})]


server=ThreadingHTTPServer(('127.0.0.1',0),Model)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with tempfile.TemporaryDirectory(dir=args.temporary,prefix='packaged-harness-') as temporary:
        runtime=harness.Harness(Modules(Path(temporary)))
        with patch.object(harness,'prepare',side_effect=AssertionError('Packaged runtime must not install dependencies')),patch.object(harness,'pnpm_path',side_effect=AssertionError('Packaged runtime must not find developer tools')):
            result=runtime.run('Sort synthetic items','[]',['deadlines'],'synthetic-model','synthetic-release-key',connection={'provider':'deepseek','base_url':f'http://127.0.0.1:{server.server_port}/v1'})
        assert result['content']=='Synthetic release verified',result
        assert result['tools'] and all(not item['is_error'] for item in result['tools']),result
        assert len(requests)==2
        assert not any((Path(temporary)/'runtime'/'tmp').iterdir())
    print(json.dumps({'bundled_python':sys.version.split()[0],'harness':'official runtime','plugin':'deadlines','model':'local synthetic only','developer_tools_used':False,'workspace_cleaned':True}))
finally:server.shutdown();server.server_close();thread.join()
