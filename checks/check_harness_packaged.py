"""A packaged task uses only preinstalled plugin versions, never pnpm or downloads."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT))
from backend.services.ai import harness
from fastapi import HTTPException


def main():
    with tempfile.TemporaryDirectory(prefix='harness-release-',dir=PROJECT/'.codex'/'tmp') as temporary:
        root=Path(temporary);template=root/'template';template.mkdir()
        plugin=root/'module';plugin.mkdir()
        package={'name':'campus-synthetic','version':'1.0.0'}
        (plugin/'package.json').write_text(json.dumps(package))
        entry=SimpleNamespace(harness={'name':package['name'],'folder':plugin,'bundle':False})
        (template/'campus-template.json').write_text(json.dumps({'sdk':'0.1.5rc1','plugins':{package['name']:'1.0.0','campus-harness-stream':'0.1.0'}}))
        (template/'profiles').mkdir();(template/'profiles'/'fixture.txt').write_text('preinstalled')
        with patch.object(harness,'BUNDLED_HARNESS',template):
            home=root/'task';harness.copy_bundled_home(home,[entry],streaming=True)
            assert (home/'profiles'/'fixture.txt').read_text()=='preinstalled'
            (home/'profiles'/'fixture.txt').write_text('isolated task')
            assert (template/'profiles'/'fixture.txt').read_text()=='preinstalled'
            (plugin/'package.json').write_text(json.dumps({**package,'version':'2.0.0'}))
            try:harness.copy_bundled_home(root/'mismatch',[entry],streaming=False);raise AssertionError('Unbundled plugin version must fail')
            except HTTPException as error:assert error.status_code==503
    print('packaged Harness: isolated writable homes and exact preinstalled plugin versions passed')


if __name__=='__main__':main()
