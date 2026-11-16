"""Real Electron acceptance with an isolated user profile and no developer PATH."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import build_opener,ProxyHandler

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--executable',required=True,type=Path)
parser.add_argument('--temporary',required=True,type=Path)
args=parser.parse_args();args.temporary.mkdir(parents=True,exist_ok=True)
http=build_opener(ProxyHandler({}))


def wait_result(process,file):
    until=time.monotonic()+45
    while time.monotonic()<until:
        if file.exists():
            value=json.loads(file.read_text(encoding='utf-8'))
            assert 'error' not in value,value
            return value
        assert process.poll() is None,'Desktop exited before its UI was ready'
        time.sleep(.05)
    raise AssertionError('Desktop readiness timeout')


def released(origin):
    port=int(origin.rsplit(':',1)[1]);until=time.monotonic()+15
    while time.monotonic()<until:
        with socket.socket() as client:
            if client.connect_ex(('127.0.0.1',port))!=0:return
        time.sleep(.1)
    raise AssertionError('Desktop left a listening backend')


with tempfile.TemporaryDirectory(prefix='desktop 中文 ',dir=args.temporary) as temporary:
    root=Path(temporary).resolve();data=root/'user data';result=root/'ready.json';second=root/'duplicate.json'
    env={**os.environ,'CAMPUS_DATA_DIR':str(data),'PATH':os.environ['SystemRoot']+'\\System32;'+os.environ['SystemRoot']+'\\System32\\WindowsPowerShell\\v1.0'}
    env.pop('ELECTRON_RUN_AS_NODE',None)
    process=subprocess.Popen([str(args.executable.resolve()),'--port=0','--smoke-test='+str(result),'--smoke-hold=4000'],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        info=wait_result(process,result)
        assert info['ready'] and info['node']=='undefined' and info['process']=='undefined'
        duplicate=subprocess.run([str(args.executable.resolve()),'--port=0','--smoke-test='+str(second)],env=env,creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
        assert duplicate.returncode==0 and not second.exists(),'A duplicate desktop cannot start another backend'
        with http.open(info['origin']+'/api/v1/health',timeout=2) as response:assert json.load(response)['launch_id']==info['launchId']
        process.wait(timeout=25);assert process.returncode==0;released(info['origin'])
        result.unlink()
        crash=subprocess.Popen([str(args.executable.resolve()),'--port=0','--smoke-test='+str(result),'--smoke-hold=30000'],env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            info=wait_result(crash,result);crash.kill();crash.wait(timeout=10);released(info['origin'])
        finally:
            if crash.poll() is None:crash.kill();crash.wait()
        print(json.dumps({'desktop':'passed','single_instance':True,'renderer_node_access':False,'developer_path':False,'normal_exit_port_released':True,'owner_crash_port_released':True,'data_path':'Unicode and spaces'}))
    finally:
        if process.poll() is None:process.kill();process.wait()
