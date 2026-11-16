"""Explicit, same-Windows-user migration. Stop both applications before copying."""
import argparse
import ctypes
from ctypes import wintypes
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import uuid


def running(directory):
    state=directory/'runtime'/'launcher'/'server.json'
    if not state.exists():return False
    try:pid=int(json.loads(state.read_text(encoding='utf-8'))['pid'])
    except (OSError,ValueError,KeyError,TypeError):
        raise RuntimeError('启动状态无法确认，请先通过原启动器停止应用。') from None
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:return ctypes.get_last_error()==5
        try:
            status=wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle,ctypes.byref(status)) or status.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False


def is_database(path):
    if path.is_symlink() or not path.is_file():return False
    with path.open('rb') as stream:
        return stream.read(16)==b'SQLite format 3\x00'


def copy_database(source,target):
    # Merge committed WAL pages into a standalone, validated database copy.
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original:
        with closing(sqlite3.connect(target)) as destination:
            original.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise ValueError('本地数据库检查失败，未启用迁移副本。')


def copy_persistent(source,target,*,exclude_runtime=False):
    target.mkdir()
    for path in source.iterdir():
        if exclude_runtime and path.name.lower() in {'runtime','vault.dpapi.lock'}:continue
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
            raise ValueError('迁移不跟随链接或联接目录。')
        if path.is_dir():copy_persistent(path,target/path.name)
        elif path.name.endswith(('-wal','-shm')) and is_database(path.with_name(path.name[:-4])):
            continue
        elif is_database(path):copy_database(path,target/path.name)
        else:shutil.copy2(path,target/path.name)


def migrate(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if not source.is_dir() or not is_database(source/'settings.sqlite3'):
        raise ValueError('请选择含 settings.sqlite3 的旧数据目录。')
    if source==destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('原目录与目标目录必须互不包含。')
    if running(source) or running(destination):raise RuntimeError('请先关闭原版与桌面版，再迁移资料。')
    if destination.exists() and any(destination.iterdir()):raise FileExistsError('目标已有用户数据，拒绝覆盖。')
    destination.parent.mkdir(parents=True,exist_ok=True)
    marker=uuid.uuid4().hex[:12]
    backup=destination.with_name(destination.name+'.migration-backup-'+marker)
    staging=destination.with_name(destination.name+'.migration-pending-'+marker)
    try:
        copy_persistent(source,backup,exclude_runtime=True)
        shutil.copytree(backup,staging)
        if destination.exists():destination.rmdir()  # only a previously verified empty directory
        os.replace(staging,destination)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return {'directory':str(destination),'backup':str(backup),'original_preserved':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(migrate(args.source,args.destination),ensure_ascii=False))
