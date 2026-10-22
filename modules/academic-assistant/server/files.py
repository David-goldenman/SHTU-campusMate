"""Persistent local files with workspace approvals and an explicit full-access mode."""
import asyncio
import os
import stat
import threading
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.services.campus.analysis import account_revision

MAX_BYTES = 1024 * 1024
FILE_LOCK = threading.RLock()


class FileSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['workspace', 'full']
    workspace: str = Field(default='', max_length=2000)
    account_revision: str = Field(min_length=1, max_length=100)
    expected_revision: str = Field(max_length=100)


class FileOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['list', 'read', 'write', 'edit', 'mkdir']
    path: str = Field(default='.', max_length=2000)
    content: str = Field(default='', max_length=200000)
    old_text: str = Field(default='', max_length=200000)
    new_text: str = Field(default='', max_length=200000)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=12000, ge=1, le=20000)


class FileDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allow: bool
    account_revision: str = Field(min_length=1, max_length=100)


def settings(context):
    owner = account_revision(context)
    saved = context.store.read('file-settings:' + owner, {})
    default_root = (context.data_dir / 'files' / owner).resolve()
    if not saved.get('workspace'):
        default_root.mkdir(parents=True, exist_ok=True)
    return {'mode': saved.get('mode', 'workspace'), 'workspace': saved.get('workspace') or str(default_root),
            'revision': saved.get('revision', ''), 'account_revision': owner}


def local_path(value):
    if not value.strip() or '\x00' in value or value.startswith(('\\\\', '//')):
        raise HTTPException(422, '请使用本机文件路径，不支持网络共享、设备或空路径。')
    path = Path(value).expanduser()
    if os.name == 'nt' and any(':' in part for part in path.parts[1:]):
        raise HTTPException(422, '不支持设备路径或文件的替代数据流。')
    return path


def save_settings(context, body):
    with FILE_LOCK:
        current = settings(context)
        if body.account_revision != current['account_revision'] or body.expected_revision != current['revision']:
            raise HTTPException(409, '账号或文件访问设置已更新，请刷新后重试。')
        root = local_path(body.workspace or current['workspace'])
        if not root.is_absolute():
            raise HTTPException(422, 'workspace 需要使用绝对路径。')
        root = root.resolve()
        if root.exists() and not root.is_dir():
            raise HTTPException(422, 'workspace 必须是文件夹。')
        root.mkdir(parents=True, exist_ok=True)
        context.store.write('file-settings:' + current['account_revision'], {'mode': body.mode, 'workspace': str(root), 'revision': uuid4().hex})
        return settings(context)


def version(path):
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


class Files:
    def __init__(self, task):
        self.task = task
        self.reads = {}
        self.pending = {}
        self.approval_seconds = 75

    def decide(self, identity, body):
        self.task.check()
        pending = self.pending.get(identity)
        if not pending or body.account_revision != self.task.owner:
            raise HTTPException(409, '这条审批已失效或账号已切换。')
        if pending['decision'] is not None:
            raise HTTPException(409, '这条审批已经处理。')
        pending['decision'] = body.allow
        return {'decided': True}

    async def authorize(self, body, path, config):
        root = Path(config['workspace']).resolve()
        if config['mode'] == 'full' or path.is_relative_to(root):
            return
        identity = uuid4().hex
        request = {'id': identity, 'action': body.action, 'path': str(path), 'account_revision': self.task.owner,
                   'content': body.content if body.action == 'write' else None,
                   'old_text': body.old_text if body.action == 'edit' else None,
                   'new_text': body.new_text if body.action == 'edit' else None}
        pending = self.pending[identity] = {'request': request, 'decision': None}
        self.task.emit({'type': 'file-approval', 'approval': request})
        try:
            deadline = asyncio.get_running_loop().time() + self.approval_seconds
            while pending['decision'] is None:
                self.task.check()
                if asyncio.get_running_loop().time() >= deadline:
                    raise HTTPException(409, '文件访问审批超时，本次未执行。需要时可重新发起。')
                await asyncio.sleep(.1)
            self.task.check()
            if not pending['decision']:
                raise HTTPException(403, '用户拒绝了本次文件访问，不要改用其他路径或工具绕过。')
        finally:
            self.pending.pop(identity, None)
            self.task.emit({'type': 'file-approval-closed', 'id': identity})

    async def operate(self, body):
        self.task.check()
        config = settings(self.task.context)
        supplied = local_path(body.path)
        requested = supplied if supplied.is_absolute() else Path(config['workspace']) / supplied
        path = requested.resolve()
        await self.authorize(body, path, config)
        self.task.check()
        try:
            with FILE_LOCK:
                self.task.check()
                if config != settings(self.task.context) or path != requested.resolve():
                    raise HTTPException(409, '访问设置或路径指向已变化，请重新读取。')
                result = self.execute(body, path)
        except HTTPException:
            raise
        except (OSError, UnicodeError, ValueError) as error:
            raise HTTPException(422, '本地文件操作未完成：' + str(error)[:300]) from None
        return result

    def execute(self, body, path):
        if path.exists() and not (path.is_dir() or stat.S_ISREG(path.stat().st_mode)):
            raise HTTPException(422, '仅支持普通文件和文件夹。')
        if body.action == 'list':
            entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
            selected = entries[body.offset:body.offset + min(body.limit, 200)]
            return {'path': str(path), 'items': [{'name': item.name, 'directory': item.is_dir(), 'path': str(item)} for item in selected],
                    'total': len(entries), 'next_offset': body.offset + len(selected)}
        if body.action == 'read':
            before = version(path)
            if before[2] > MAX_BYTES:
                raise HTTPException(422, '文本文件超过 1 MiB，请先拆分；此工具不读取二进制文件。')
            with path.open('r', encoding='utf-8-sig', newline='') as stream:
                content = stream.read()
            if '\x00' in content:
                raise HTTPException(422, '这是二进制文件，请使用适合其格式的资料读取工具。')
            if before != version(path):
                raise HTTPException(409, '文件在读取过程中变化，请重读。')
            self.reads[str(path)] = before
            chunk = content[body.offset:body.offset + body.limit]
            return {'path': str(path), 'text': chunk, 'total_chars': len(content), 'offset': body.offset,
                    'next_offset': body.offset + len(chunk), 'has_more': body.offset + len(chunk) < len(content)}
        if body.action == 'mkdir':
            path.mkdir(parents=True, exist_ok=True)
        else:
            exists = path.exists()
            if exists and self.reads.get(str(path)) != version(path):
                raise HTTPException(409, '覆盖或编辑已有文件前请先读取；文件可能已被用户修改。')
            if body.action == 'edit':
                if not exists or not body.old_text:
                    raise HTTPException(422, '编辑需要已有文件和非空的待替换原文。')
                with path.open('r', encoding='utf-8-sig', newline='') as stream:
                    old = stream.read()
                if old.count(body.old_text) != 1:
                    raise HTTPException(409, '原文必须只匹配一处，请重读并提供足够上下文。')
                content = old.replace(body.old_text, body.new_text, 1)
            else:
                content = body.content
            if len(content.encode('utf-8')) > MAX_BYTES:
                raise HTTPException(422, '写入文本不能超过 1 MiB。')
            if '\x00' in content:
                raise HTTPException(422, '文本工具不能写入二进制空字符。')
            path.parent.mkdir(parents=True, exist_ok=True)
            if exists:
                # Prepare next to the target, then recheck before replacing it.
                temporary = path.with_name('.' + path.name + '.' + uuid4().hex + '.tmp')
                try:
                    with path.open('rb') as stream:
                        has_bom = stream.read(3) == b'\xef\xbb\xbf'
                    with temporary.open('x', encoding='utf-8-sig' if has_bom else 'utf-8', newline='') as stream:
                        stream.write(content)
                    if self.reads[str(path)] != version(path):
                        raise HTTPException(409, '文件已被修改，本次未覆盖，请重新读取。')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                with path.open('x', encoding='utf-8', newline='') as stream:
                    stream.write(content)
            self.reads.pop(str(path), None)
        change = {'applied': True, 'domain': 'files', 'action': body.action, 'after': {'title': path.name, 'path': str(path)},
                  'local_only': True, 'affected_count': 1}
        self.task.changes.append(change)
        self.task.emit({'type': 'change', 'change': change})
        return {'path': str(path), 'saved': True, 'change': change}
