"""Installed resources stay read-only; private paths are explicit and relocatable."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]


def paths(environment):
    env = {key: value for key, value in os.environ.items() if key not in {'CAMPUS_DATA_DIR', 'CAMPUS_PACKAGED'}}
    env.update(environment)
    return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c',
        'import json; from backend.core.paths import PROJECT,DATA,RUNTIME; print(json.dumps([str(PROJECT),str(DATA),str(RUNTIME)]))'],
        cwd=PROJECT, env=env, capture_output=True, text=True, encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory(prefix='release paths 中文 ', dir=PROJECT / '.codex' / 'tmp') as temporary:
        directory=Path(temporary)
        custom=directory / '用户 数据'
        result=paths({'CAMPUS_DATA_DIR':str(custom)})
        assert result.returncode==0,result.stderr
        values=json.loads(result.stdout)
        assert Path(values[1])==custom,'An explicit user directory must own all persistent data'
        assert Path(values[2])==custom/'runtime'
        (directory/'alias-parent').mkdir()
        ios_data=directory/'alias-parent'/'..'/'iOS data'
        result=paths({'CAMPUS_DATA_DIR':str(ios_data)})
        assert result.returncode==0,result.stderr
        assert Path(json.loads(result.stdout)[1])==ios_data,'The iOS boot path equality must preserve an explicit directory spelling'
        result=paths({'CAMPUS_PACKAGED':'1','LOCALAPPDATA':str(directory)})
        assert result.returncode==0,result.stderr
        assert Path(json.loads(result.stdout)[1])==directory/'campusMate'/'data'
        assert paths({'CAMPUS_DATA_DIR':'relative-user-data'}).returncode!=0
        assert Path(json.loads(paths({}).stdout)[1])==PROJECT/'.private'
    print('release paths: Unicode/space user directory, packaged default, invalid relative path and unchanged development storage passed')


if __name__=='__main__':
    main()
