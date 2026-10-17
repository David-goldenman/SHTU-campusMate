import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from backend.core.themes import catalog

installed = catalog(PROJECT / 'web/themes')
assert installed['items'][0]['id'] == 'default'
assert {'default', 'observatory', 'star-notes'} <= {item['id'] for item in installed['items']}
assert not installed['errors']
with tempfile.TemporaryDirectory(dir=PROJECT / '.codex/tmp') as directory:
    root = Path(directory)
    folder = root / 'sample'
    folder.mkdir()
    (folder / 'view.js').write_text('export function mount() {}', encoding='utf-8')
    manifest = {'id':'sample','name':'Sample','api_version':1,'views':{'mail':'view.js'},'styles':[]}
    path = folder / 'theme.json'
    path.write_text(json.dumps(manifest),encoding='utf-8')
    result = catalog(root)
    assert result['items'][0]['views']['mail'] == '/assets/themes/sample/view.js'
    for invalid in ({'api_version':2}, {'id':'other'}, {'views':{'mail':'../../../backend/main.py'}}, {'styles':['missing.css']}):
        path.write_text(json.dumps({**manifest, **invalid}), encoding='utf-8')
        result=catalog(root)
        assert not result['items'] and len(result['errors'])==1
print('themes: local discovery, versioned view entries, asset boundaries and isolated invalid manifests passed')
