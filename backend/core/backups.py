"""Local module snapshots. Call mutations only while module workers are stopped."""
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


class Backups:
    def __init__(self, store, data):
        self.store, self.data = store, Path(data).resolve()
        self.root = self.data / 'backups'

    def checked(self, path):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(self.data):
            raise HTTPException(409, '数据目录包含链接或位于项目私有目录之外，操作已停止。')
        return path

    def rename(self, source, destination):
        self.checked(source)
        self.checked(destination)
        for attempt in range(20):
            try:
                source.rename(destination)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.1)

    def files(self, directory):
        self.checked(directory)
        result = {}
        if directory.exists():
            for parent, directories, filenames in directory.walk():
                for name in directories + filenames:
                    self.checked(parent / name)
                for name in filenames:
                    path = parent / name
                    if not path.is_file():
                        raise HTTPException(409, '数据中存在无法备份的文件。')
                    result[path.relative_to(directory).as_posix()] = path.stat().st_size
        return result

    def folder(self, backup_id):
        self.checked(self.root)
        if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{12}', backup_id):
            raise HTTPException(404, '备份不存在。')
        folder = self.checked(self.root / backup_id)
        if not folder.is_dir():
            raise HTTPException(404, '备份不存在。')
        return folder

    def list(self):
        self.checked(self.root)
        result = []
        if self.root.exists():
            for folder in sorted(self.root.iterdir(), reverse=True):
                if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{12}', folder.name):
                    continue
                try:
                    metadata, _ = self.validate(folder.name)
                    result.append({**metadata, 'valid': True})
                except (HTTPException, OSError, ValueError, TypeError, KeyError):
                    result.append({'id': folder.name, 'valid': False, 'reason': 'invalid'})
        return result

    def validate(self, backup_id):
        folder = self.folder(backup_id)
        try:
            self.checked(folder / 'metadata.json')
            self.checked(folder / 'state.json')
            metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
            if metadata['version'] != 1 or metadata['id'] != backup_id or metadata['reason'] not in {'manual', 'before_clear', 'before_restore'}:
                raise ValueError
            rows = json.loads((folder / 'state.json').read_text(encoding='utf-8'))
            if not isinstance(rows, list):
                raise ValueError
            seen = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 3 or not all(isinstance(value, str) for value in row):
                    raise ValueError
                namespace, key, value = row
                if not re.fullmatch(r'module:[a-z][a-z0-9_-]{0,47}', namespace) or (namespace, key) in seen:
                    raise ValueError
                json.loads(value)
                seen.add((namespace, key))
            files = self.files(folder / 'modules')
            if (not (folder / 'modules').is_dir() or files != metadata['files']
                    or metadata['file_count'] != len(files)
                    or metadata['size_bytes'] != sum(files.values()) + (folder / 'state.json').stat().st_size):
                raise ValueError
            return {key: metadata[key] for key in ('id', 'created_at', 'reason', 'size_bytes', 'file_count')}, rows
        except (OSError, ValueError, TypeError, KeyError):
            raise HTTPException(409, '备份不完整或格式不正确，当前数据未更改。') from None

    def create(self, reason='manual'):
        self.checked(self.root).mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc)
        backup_id = timestamp.strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12]
        staging = self.root / ('.creating-' + backup_id)
        destination = self.root / backup_id
        source = self.checked(self.data / 'modules')
        self.files(source)
        staging.mkdir()
        try:
            if source.exists():
                shutil.copytree(source, staging / 'modules')
            else:
                (staging / 'modules').mkdir()
            (staging / 'state.json').write_text(json.dumps(self.store.export_modules(), ensure_ascii=False), encoding='utf-8')
            files = self.files(staging / 'modules')
            metadata = {'version': 1, 'id': backup_id, 'created_at': timestamp.isoformat(), 'reason': reason,
                        'file_count': len(files), 'size_bytes': sum(files.values()) + (staging / 'state.json').stat().st_size, 'files': files}
            (staging / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
            self.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return {key: value for key, value in metadata.items() if key not in {'version', 'files'}}

    def restore(self, backup_id):
        _, rows = self.validate(backup_id)
        previous = self.create('before_restore')
        work = self.data / ('.restore-' + uuid.uuid4().hex)
        current = self.checked(self.data / 'modules')
        work.mkdir()
        old = work / 'previous'
        replaced = committed = False
        try:
            shutil.copytree(self.folder(backup_id) / 'modules', work / 'next')
            if current.exists():
                self.rename(current, old)
            try:
                self.rename(work / 'next', current)
                replaced = True
                self.store.restore_modules(rows)
                committed = True
            except Exception:
                if replaced:
                    shutil.rmtree(current)
                if old.exists():
                    self.rename(old, current)
                raise
        finally:
            # Keep the previous files if a filesystem rollback itself could not finish.
            if committed or not old.exists():
                shutil.rmtree(work)
        return {'restored': backup_id, 'backup': previous}

    def delete(self, backup_id):
        folder = self.folder(backup_id)
        self.files(folder)
        shutil.rmtree(folder)
