"""Build the Windows runtime from locked dependencies; never read .private or a global venv."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import Request,urlopen
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
BUILD=PROJECT/'.codex'/'windows-release'
LOCK=json.loads((PROJECT/'packaging'/'runtime-lock.json').read_text(encoding='utf-8'))
SCRIPTS={'desktop_service.py','migrate_data.py','browser.mjs','browser-network.mjs','ids-device-guide.js','dpapi.ps1','read-calendar.ps1'}
SKIP={'.private','.codex','.git','node_modules','__pycache__','checks','tests'}


def source_files(root):
    root=Path(root).resolve()
    candidates=[]
    for name in ('backend','web'):
        candidates.extend((root/name).rglob('*'))
    for module in (root/'modules').glob('*'):
        candidates.append(module/'module.json')
        for name in ('server','web','harness'):candidates.extend((module/name).rglob('*'))
    candidates.extend(root/'scripts'/name for name in SCRIPTS)
    for file in sorted(candidates):
        relative=file.relative_to(root)
        if not file.is_file() or any(part in SKIP or part.startswith('.') for part in relative.parts) or file.name.endswith(('.bak','.packaging-bak','.pyc','.pyo','~')):continue
        if file.is_symlink() or not file.resolve().is_relative_to(root):raise ValueError('Release source escapes project')
        yield relative.as_posix()


def remove_generated(path):
    path=Path(path).resolve()
    if not path.is_relative_to(BUILD.resolve()) or path==BUILD.resolve():raise ValueError('Unsafe build cleanup')
    if path.exists():shutil.rmtree(path)


def run(command,**options):
    print('Build step:',Path(str(command[0])).name,*map(str,command[1:3]),flush=True)
    subprocess.run(list(map(str,command)),cwd=PROJECT,check=True,**options)


def download(url,name):
    cache=BUILD/'downloads';cache.mkdir(parents=True,exist_ok=True)
    target=cache/name
    if target.exists():return target
    pending=target.with_suffix(target.suffix+'.pending')
    with urlopen(Request(url,headers={'User-Agent':'campusMate-build/0.2'}),timeout=90) as response,pending.open('wb') as output:
        shutil.copyfileobj(response,output)
    pending.replace(target)
    return target


def extract(archive,directory):
    directory.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if not (directory/member.filename).resolve().is_relative_to(directory.resolve()):raise ValueError('Unsafe runtime archive')
        if package.testzip():raise ValueError('Incomplete runtime archive')
        package.extractall(directory)


def runtime():
    cache=BUILD/'runtime-cache';python=cache/'python';node=cache/'node'
    if not (python/'python.exe').exists():
        name=f"python-{LOCK['python']}-embed-amd64.zip"
        extract(download(f"https://www.python.org/ftp/python/{LOCK['python']}/{name}",name),python)
    (python/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\nimport site\n',encoding='utf-8')
    requirements=BUILD/'python-requirements.txt'
    run(['uv','export','--locked','--format','requirements-txt','--no-hashes','--no-emit-project','--output-file',requirements],stdout=subprocess.DEVNULL)
    run(['uv','pip','sync','--python',sys.executable,'--target',python/'Lib'/'site-packages','--cache-dir',PROJECT/'.codex'/'cache'/'uv-windows',requirements])
    if not (node/'node.exe').exists():
        name=f"node-v{LOCK['node']}-win-x64.zip";base=f"https://nodejs.org/dist/v{LOCK['node']}/"
        archive=download(base+name,name)
        sums=download(base+'SHASUMS256.txt',f"node-v{LOCK['node']}-SHASUMS256.txt").read_text()
        expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1]==name)
        if hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=expected:raise ValueError('Node archive checksum mismatch')
        unpacked=cache/'node-unpacked';extract(archive,unpacked)
        node.mkdir(parents=True,exist_ok=True)
        for file in ('node.exe','LICENSE'):
            shutil.copy2(unpacked/f"node-v{LOCK['node']}-win-x64"/file,node/file)
        remove_generated(unpacked)
    actual=subprocess.check_output([str(node/'node.exe'),'--version'],text=True).strip()
    if actual!='v'+LOCK['node']:raise ValueError('Unexpected Node runtime version')
    return cache


def harness_template(bundle):
    pnpm=shutil.which('pnpm.cmd') or shutil.which('pnpm')
    if not pnpm or subprocess.check_output([pnpm,'--version'],text=True).strip()!=LOCK['pnpm']:
        raise RuntimeError('Build requires pnpm '+LOCK['pnpm'])
    home=BUILD/'harness-build-home';remove_generated(home)
    workspace=home/'profiles'/'sdk-minimal';workspace.mkdir(parents=True)
    (workspace/'pnpm-workspace.yaml').write_text('packages:\n  - .\nnodeLinker: hoisted\nautoInstallPeers: false\nstoreDir: '+json.dumps((BUILD/'pnpm-store').as_posix())+'\n',encoding='utf-8')
    folders=sorted((bundle/'modules').glob('*/harness'))+[bundle/'backend'/'services'/'ai'/'stream']
    env={**os.environ,'DSH_HOME':str(home),'npm_config_auto_install_peers':'false','npm_config_node_linker':'hoisted',
         'npm_config_store_dir':str(BUILD/'pnpm-store'),'npm_config_cache':str(BUILD/'npm-cache'),
         'TEMP':str(BUILD/'tmp'),'TMP':str(BUILD/'tmp')}
    (BUILD/'tmp').mkdir(exist_ok=True)
    executable=bundle/'runtime'/'python'/'Lib'/'site-packages'/'deepseek_harness_runtime'/'runtime'/'deepseek-harness-sdk-runtime-win-x64.exe'
    run([executable,'plugin','--profile','sdk-minimal','add',*['file:'+folder.as_posix() for folder in folders]],env=env)
    destination=bundle/'runtime'/'harness-home';profile=destination/'profiles'/'sdk-minimal';profile.mkdir(parents=True)
    original=home/'profiles'/'sdk-minimal'
    packages={json.loads((folder/'package.json').read_text())['name']:json.loads((folder/'package.json').read_text())['version'] for folder in folders}
    package=json.loads((original/'package.json').read_text());package['dependencies']=packages
    (profile/'package.json').write_text(json.dumps(package,indent=2),encoding='utf-8')
    for file in ('cordis.yml','cordis.patch.yml'):
        if (original/file).exists():shutil.copy2(original/file,profile/file)
        else:(profile/file).write_text('[]\n',encoding='utf-8')
    # Hoisted packages are self-contained; omit pnpm's machine-specific store metadata.
    modules=profile/'node_modules';modules.mkdir()
    for item in (original/'node_modules').iterdir():
        if item.name.startswith('.') and item.name!='.package-map.json':continue
        if item.is_dir():shutil.copytree(item,modules/item.name)
        else:shutil.copy2(item,modules/item.name)
    (destination/'campus-template.json').write_text(json.dumps({'sdk':LOCK['harness'],'plugins':packages},indent=2),encoding='utf-8')


def build(*,sources_only=False):
    if os.name!='nt':raise RuntimeError('Windows x64 build required')
    BUILD.mkdir(parents=True,exist_ok=True)
    bundle=BUILD/'bundle'
    if sources_only:
        if not (bundle/'runtime'/'python'/'python.exe').exists():raise RuntimeError('Prepare the runtime first')
        for name in ('backend','web','modules','scripts'):remove_generated(bundle/name)
    else:
        cached=runtime();remove_generated(bundle);bundle.mkdir()
        shutil.copytree(cached/'python',bundle/'runtime'/'python')
        shutil.copytree(cached/'node',bundle/'runtime'/'node')
    sources=list(source_files(PROJECT))
    for relative in sources:
        target=bundle/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PROJECT/relative,target)
    remove_generated(bundle/'runtime'/'harness-home');harness_template(bundle)
    packages=[]
    for distribution in metadata.distributions(path=[str(bundle/'runtime'/'python'/'Lib'/'site-packages')]):
        packages.append({'name':distribution.metadata['Name'],'version':distribution.version,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License','See distribution license files')})
    manifest={'product':'campusMate','version':json.loads((PROJECT/'desktop'/'package.json').read_text())['version'],
              'runtimes':LOCK,'python_packages':sorted(packages,key=lambda row:row['name'].lower()),'sources':sources}
    (bundle/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (bundle/'THIRD_PARTY.txt').write_text('Python: runtime/python/LICENSE.txt\nNode.js: runtime/node/LICENSE\nPython package licenses: runtime/python/Lib/site-packages/*.dist-info/ (including licenses/)\nElectron licenses: top-level LICENSE.electron.txt and LICENSES.chromium.html\nFrontend licenses: web/vendor/*/LICENSE*\nWeChat WCDB attribution: modules/group-messages/server/native/WCDB_LICENSE.txt\nDependency versions: release-manifest.json\n',encoding='utf-8')
    print('Runtime prepared:',bundle,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sources-only',action='store_true');args=parser.parse_args()
    build(sources_only=args.sources_only)
