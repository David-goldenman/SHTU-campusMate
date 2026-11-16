"""Migration never overwrites existing data and preserves an independent backup."""
import importlib.util
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))


def main():
    spec=importlib.util.spec_from_file_location('data_migration',PROJECT/'scripts'/'migrate_data.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='migration 中文 ',dir=PROJECT/'.codex'/'tmp') as temporary:
        root=Path(temporary);source=root/'old private';source.mkdir()
        with closing(sqlite3.connect(source/'settings.sqlite3')) as connection, connection:
            connection.execute('CREATE TABLE state (value TEXT)');connection.execute("INSERT INTO state VALUES ('synthetic settings')")
        (source/'vault.dpapi').write_bytes(b'synthetic-encrypted-vault')
        (source/'vault.dpapi.lock').write_text('application lock')
        (source/'runtime').mkdir();(source/'runtime'/'private-session').write_text('must not migrate')
        user_files={'modules/academic-assistant/files/runtime/notes.md':'my runtime notes',
                    'modules/academic-assistant/files/runtime/nested/runtime/code.txt':'nested user file',
                    'modules/courses/files/Runtime/lecture.txt':'case-preserving user folder'}
        for name in ('uv.lock','poetry.lock','research-wal','notes-shm','vault.dpapi.lock'):
            user_files['modules/academic-assistant/files/project/'+name]='user-owned '+name
        for relative,content in user_files.items():
            file=source/relative;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content)
        target=root/'new user data'
        result=module.migrate(source,target)
        assert (target/'vault.dpapi').read_bytes()==b'synthetic-encrypted-vault'
        assert not (target/'runtime').exists()
        assert not (target/'vault.dpapi.lock').exists()
        backup=Path(result['backup']);assert (backup/'settings.sqlite3').is_file()
        assert not (backup/'runtime').exists()
        for copy in (source,target,backup):
            for relative,content in user_files.items():
                assert (copy/relative).is_file(),f'User file missing from migration or backup: {copy/relative}'
                assert (copy/relative).read_text()==content
        assert (source/'settings.sqlite3').exists()
        with closing(sqlite3.connect(target/'settings.sqlite3')) as connection:
            assert connection.execute('SELECT value FROM state').fetchone()[0]=='synthetic settings'
        try:module.migrate(source,target);raise AssertionError('Existing data must not be overwritten')
        except FileExistsError:pass
        broken=root/'failed destination'
        replace=module.os.replace
        def fail_final(before,after):
            if Path(after)==broken:raise OSError('synthetic interrupted migration')
            return replace(before,after)
        with patch.object(module.os,'replace',side_effect=fail_final):
            try:module.migrate(source,broken);raise AssertionError('Failure must propagate')
            except OSError:pass
        assert not broken.exists() and (source/'settings.sqlite3').exists()
        assert len(list(root.glob('*.migration-backup-*')))==2
        # A real SQLite WAL must be folded into a standalone database; a filename
        # that only looks like a database or sidecar is still an ordinary document.
        wal_source=root/'wal source';wal_source.mkdir()
        (wal_source/'ordinary.sqlite3').write_text('a user note, not a database')
        (wal_source/'ordinary.sqlite3-wal').write_text('another user note')
        with closing(sqlite3.connect(wal_source/'settings.sqlite3')) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE state (value TEXT)')
            connection.execute("INSERT INTO state VALUES ('committed WAL data')");connection.commit()
            assert (wal_source/'settings.sqlite3-wal').is_file()
            wal_result=module.migrate(wal_source,root/'wal target')
            for copy in (Path(wal_result['directory']),Path(wal_result['backup'])):
                assert not (copy/'settings.sqlite3-wal').exists() and not (copy/'settings.sqlite3-shm').exists()
                with closing(sqlite3.connect(copy/'settings.sqlite3')) as restored:
                    assert restored.execute('SELECT value FROM state').fetchone()[0]=='committed WAL data'
                assert (copy/'ordinary.sqlite3').read_text()=='a user note, not a database'
                assert (copy/'ordinary.sqlite3-wal').read_text()=='another user note'
        invalid=root/'invalid source';invalid.mkdir();(invalid/'settings.sqlite3').write_text('broken application database')
        try:module.migrate(invalid,root/'invalid target');raise AssertionError('Invalid application databases must not be promoted')
        except ValueError:pass
        assert not (root/'invalid target').exists()
    print('migration: explicit copy, preserved source/backup, database validation, no overwrite and failed promotion rollback passed')


if __name__=='__main__':main()
