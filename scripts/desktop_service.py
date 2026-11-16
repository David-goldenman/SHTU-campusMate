"""Owned desktop service: reserve the port before startup and stop when the owner exits."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import sys
import threading

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def own_process_tree():
    """A Windows job releases verification browsers/Harness children on forced exit."""
    if os.name!='nt':return None
    size=ctypes.c_size_t
    class Basic(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),
                  ('minimum',size),('maximum',size),('active',wintypes.DWORD),('affinity',size),
                  ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('read','write','other','read_bytes','write_bytes','other_bytes')]
    class Limits(ctypes.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',size),('job_memory',size),('peak_process',size),('peak_job',size)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    limits=Limits();limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel.SetInformationJobObject(handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
        error=ctypes.get_last_error();kernel.CloseHandle(handle);raise ctypes.WinError(error)
    return handle  # Keep until normal process exit, after application shutdown.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=16666)
    parser.add_argument('--launch-id',required=True)
    args=parser.parse_args()
    if not 0<=args.port<=65535:raise ValueError('Invalid local port')
    job=own_process_tree()
    import uvicorn
    from filelock import FileLock
    from backend.core.paths import DATA
    from backend.main import create_app
    runtime=DATA/'runtime'/'launcher';runtime.mkdir(parents=True,exist_ok=True)
    with FileLock(str(runtime/'desktop.lock'),timeout=0),socket.socket() as listener:
        if os.name=='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try:listener.bind(('127.0.0.1',args.port))
        except OSError as error:
            if error.errno not in {48,98,10048}:raise
            listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
        app=create_app(active_port=port);app.state.launch_id=args.launch_id
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,timeout_graceful_shutdown=8))
        state={'pid':os.getpid(),'port':port,'launch_id':args.launch_id,'desktop':True}
        ready=runtime/'server.json';ready.write_text(json.dumps(state),encoding='utf-8')
        def watch_owner():
            try:
                for line in sys.stdin:
                    if line.strip()=='stop':break
            finally:server.should_exit=True
        threading.Thread(target=watch_owner,name='desktop-owner',daemon=True).start()
        print('CAMPUS_DESKTOP_READY '+json.dumps(state),flush=True)
        try:server.run(sockets=[listener])
        finally:
            if ready.exists() and json.loads(ready.read_text(encoding='utf-8')).get('launch_id')==args.launch_id:ready.unlink()


if __name__=='__main__':main()
