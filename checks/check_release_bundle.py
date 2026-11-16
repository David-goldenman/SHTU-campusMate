"""The release allowlist cannot include user data, development environments or checks."""
import importlib.util
from pathlib import Path
import tempfile

PROJECT=Path(__file__).resolve().parents[1]


def main():
    spec=importlib.util.spec_from_file_location('build_windows',PROJECT/'packaging'/'build_windows.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='release-sources-',dir=PROJECT/'.codex'/'tmp') as temporary:
        root=Path(temporary)
        for name in ['backend/main.py','backend/main.py.bak','web/app.js','web/.private/token.json','modules/example/module.json','modules/example/server/source.py','modules/example/checks/test.py','.private/vault.dpapi','.codex/env/python.exe','scripts/desktop_service.py','scripts/developer.py']:
            file=root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('synthetic')
        assert set(module.source_files(root))=={'backend/main.py','web/app.js','modules/example/module.json','modules/example/server/source.py','scripts/desktop_service.py'}
    print('release bundle: explicit runtime sources, no private data, backups, development environments or tests passed')


if __name__=='__main__':main()
