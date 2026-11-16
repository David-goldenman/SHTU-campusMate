"""Version promotion, failed upgrades and rollback use synthetic files only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

PROJECT=Path(__file__).resolve().parents[1]


def main():
    if os.name!='nt':print('Windows installer behavior: Windows-only check');return
    with tempfile.TemporaryDirectory(prefix='installer 中文 ',dir=PROJECT/'.codex'/'tmp') as temporary:
        root=Path(temporary);install=root/'程序 目录';payload=root/'payload'
        required=['campusMate.exe','resources/app.asar','resources/campus/runtime/python/python.exe','resources/campus/runtime/node/node.exe','resources/campus/scripts/desktop_service.py','resources/campus/runtime/harness-home/campus-template.json']
        for relative in required:
            file=payload/relative;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('synthetic program')
        manifest=payload/'resources/campus/release-manifest.json'
        userdata=root/'user data';userdata.mkdir();(userdata/'notes.txt').write_text('keep my notes')
        def command(mode='Install',success=True,target=None,environment=None):
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(PROJECT/'packaging'/'install.ps1'),
                '-Mode',mode,'-PayloadDirectory',str(payload),'-InstallDirectory',str(target or install),'-NoShortcuts','-SkipLaunchCheck'],capture_output=True,env=environment)
            assert (result.returncode==0)==success,result.stderr.decode(errors='replace')
        def state():return json.loads((install/'current.json').read_text(encoding='utf-8-sig'))
        manifest.write_text(json.dumps({'product':'campusMate','version':'0.1.0'}))
        fake_local=root/'LocalAppData'
        isolated={key:value for key,value in os.environ.items() if key!='CAMPUS_DATA_DIR'}
        isolated['LOCALAPPDATA']=str(fake_local)
        command(success=False,target=fake_local/'campusMate',environment=isolated)
        assert not (fake_local/'campusMate'/'versions').exists(),'Program installation cannot overlap the default user-data root'
        native=payload/'resources/campus/runtime/python/Lib/site-packages/synthetic_native.pyd';native.parent.mkdir(parents=True);native.write_text('synthetic native extension')
        command(success=False,target=root/('very-long-install-directory-'*4),environment=isolated)
        native.unlink()
        install.mkdir();unrelated=install/'unrelated.txt';unrelated.write_text('must stay')
        command(success=False);assert unrelated.read_text()=='must stay';unrelated.unlink()
        command();first=state()
        # A version upgrade must replace old maintenance code with current safety checks.
        (install/'install.ps1').write_text("throw 'obsolete maintenance script'\n")
        manifest.write_text(json.dumps({'product':'campusMate','version':'0.2.0'}));command();second=state()
        assert second['previous']==first['current'] and second['current']!=first['current']
        assert (install/'versions'/first['current']/'campusMate.exe').exists()
        alias=root/'parent alias'
        link=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',
            "New-Item -ItemType Junction -Path '"+str(alias).replace("'","''")+"' -Target '"+str(root).replace("'","''")+"' | Out-Null"],capture_output=True)
        assert link.returncode==0,link.stderr.decode(errors='replace')
        try:
            assert alias.resolve()==root.resolve()
            notes=install/'data'/'notes.txt';notes.parent.mkdir();notes.write_text('synthetic user notes')
            for mode in ('Install','Rollback','Uninstall'):
                # Program ancestor is a junction, actual data is inside the program tree.
                environment={**isolated,'CAMPUS_DATA_DIR':str(notes.parent)}
                command(mode,success=False,target=alias/install.name,environment=environment)
                assert state()==second and notes.read_text()=='synthetic user notes'
                # The data path can hide the same overlap through its ancestor instead.
                environment={**isolated,'CAMPUS_DATA_DIR':str(alias/install.name/'data')}
                command(mode,success=False,environment=environment)
                assert state()==second and notes.read_text()=='synthetic user notes'
                # Default data ancestry is checked even when CAMPUS_DATA_DIR is absent.
                command(mode,success=False,environment={**isolated,'LOCALAPPDATA':str(alias)})
                assert state()==second and notes.read_text()=='synthetic user notes'
            # Exercise the actual maintenance entrypoint retained by upgraded installations.
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(install/'install.ps1'),
                '-Mode','Rollback','-InstallDirectory',str(install),'-NoShortcuts','-SkipLaunchCheck'],capture_output=True,env=isolated)
            assert result.returncode==0,result.stderr.decode(errors='replace')
            assert state()['current']==first['current'],'Upgraded maintenance must remain usable'
            command('Rollback',environment=isolated);assert state()==second
            notes.unlink();notes.parent.rmdir()
        finally:
            if alias.is_junction():os.rmdir(alias)
        (payload/'resources/campus/runtime/python/python.exe').unlink();command(success=False)
        assert state()==second,'Failed validation cannot change the active installation'
        command('Rollback');assert state()['current']==first['current']
        assert (userdata/'notes.txt').read_text()=='keep my notes'
        command('Uninstall');assert not install.exists()
        assert (userdata/'notes.txt').read_text()=='keep my notes'
    print('Windows install: ancestor junction guards, maintenance upgrades, Unicode/space paths, failed promotion, rollback and uninstall preserving data passed')


if __name__=='__main__':main()
