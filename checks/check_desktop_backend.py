"""Run the actual desktop worker with synthetic user data, then close its owner pipe."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener,ProxyHandler

PROJECT=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='desktop backend 中文 ',dir=PROJECT/'.codex'/'tmp') as temporary:
        root=Path(temporary)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen()
            with (root/'output.log').open('w',encoding='utf-8') as output:
                process=subprocess.Popen([sys.executable,'-X','utf8','-B',str(PROJECT/'scripts'/'desktop_service.py'),'--port',str(occupied.getsockname()[1]),'--launch-id','synthetic-desktop'],
                    cwd=PROJECT,env={**os.environ,'CAMPUS_DATA_DIR':str(root/'user data')},stdin=subprocess.PIPE,stdout=output,stderr=output,text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:
                    until=time.monotonic()+20;state=None;http=build_opener(ProxyHandler({}))
                    while time.monotonic()<until:
                        text=(root/'output.log').read_text(encoding='utf-8')
                        for line in text.splitlines():
                            if line.startswith('CAMPUS_DESKTOP_READY '):state=json.loads(line.split(' ',1)[1])
                        if state:
                            try:
                                with http.open(f"http://127.0.0.1:{state['port']}/api/v1/health",timeout=.3) as response:
                                    if json.load(response)['launch_id']=='synthetic-desktop':break
                            except OSError:pass
                        if process.poll() is not None:raise AssertionError(text)
                        time.sleep(.05)
                    else:raise AssertionError('Desktop readiness timeout')
                    assert state['port']!=occupied.getsockname()[1]
                    assert (root/'user data'/'settings.sqlite3').exists()
                    process.stdin.close();process.wait(timeout=20)
                    assert process.returncode==0,(root/'output.log').read_text(encoding='utf-8')
                    assert not (root/'user data'/'runtime'/'launcher'/'server.json').exists()
                    with socket.socket() as probe:assert probe.connect_ex(('127.0.0.1',state['port']))!=0
                finally:
                    if process.poll() is None:process.kill();process.wait()
    print('desktop backend: real startup, busy-port fallback, Unicode data root, owner exit, graceful module shutdown and released port passed')


if __name__=='__main__':main()
