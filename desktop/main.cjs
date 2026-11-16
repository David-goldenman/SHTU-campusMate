const {app,BrowserWindow,dialog,shell}=require('electron');
const fs=require('node:fs'),path=require('node:path');
const {Backend}=require('./host.cjs');
const {assertSeparateStorage}=require('./storage.cjs');

const option=name=>process.argv.find(value=>value.startsWith(name+'='))?.slice(name.length+1);
const smoke=option('--smoke-test');
const dataDir=path.resolve(process.env.CAMPUS_DATA_DIR||path.join(process.env.LOCALAPPDATA,'campusMate','data'));
const executableDir=path.dirname(process.execPath);
const programRoot=path.basename(path.dirname(executableDir))==='versions'?path.dirname(path.dirname(executableDir)):executableDir;
try{if(app.isPackaged)assertSeparateStorage(programRoot,process.env.CAMPUS_DATA_DIR||dataDir);}
catch(error){if(smoke)fs.writeFileSync(smoke,JSON.stringify({error:error.message}));else dialog.showErrorBox('资料目录需要调整',error.message);app.exit(1);}
const profile=path.join(dataDir,'runtime','electron');
fs.mkdirSync(profile,{recursive:true});app.setPath('userData',profile);app.setPath('sessionData',profile);
let backend,window,quitting=false;

function external(url){
  try{if(['http:','https:'].includes(new URL(url).protocol))void shell.openExternal(url);}catch{}
}
function focus(){if(window&&!smoke){if(window.isMinimized())window.restore();window.show();window.focus();}}
if(!app.requestSingleInstanceLock())app.quit();
else{
  app.on('second-instance',focus);
  app.on('window-all-closed',()=>app.quit());
  app.on('before-quit',event=>{
    if(quitting)return;
    event.preventDefault();quitting=true;
    Promise.resolve(backend?.stop()).finally(()=>app.exit(0));
  });
  app.whenReady().then(async()=>{
    const bundle=app.isPackaged?path.join(process.resourcesPath,'campus'):path.resolve(__dirname,'../.codex/windows-release/bundle');
    const system=process.env.SystemRoot||'C:\\Windows',temporary=path.join(dataDir,'runtime','tmp');fs.mkdirSync(temporary,{recursive:true});
    const env={...process.env,CAMPUS_PACKAGED:'1',CAMPUS_DATA_DIR:dataDir,PYTHONUTF8:'1',PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1',
      DSH_RUNTIME_MODE:'exe',TEMP:temporary,TMP:temporary,
      PATH:[path.join(bundle,'runtime','node'),path.join(system,'System32'),system,path.join(system,'System32','WindowsPowerShell','v1.0')].join(path.delimiter)};
    delete env.PYTHONHOME;delete env.PYTHONPATH;delete env.ELECTRON_RUN_AS_NODE;
    backend=new Backend({command:[path.join(bundle,'runtime','python','python.exe'),'-X','utf8','-B',path.join(bundle,'scripts','desktop_service.py')],
      cwd:bundle,dataDir,preferredPort:Number(option('--port')??16666),env});
    const info=await backend.start();
    if(quitting)return;
    window=new BrowserWindow({width:1440,height:960,minWidth:380,minHeight:540,show:!smoke,title:'campusMate',autoHideMenuBar:true,
      webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
    window.webContents.session.setPermissionRequestHandler((_contents,permission,callback,details)=>callback(
      permission==='clipboard-sanitized-write'&&details.requestingUrl?.startsWith(info.origin+'/')));
    window.webContents.setWindowOpenHandler(({url})=>{external(url);return {action:'deny'};});
    for(const event of ['will-navigate','will-redirect'])window.webContents.on(event,(event,url)=>{
      try{if(new URL(url).origin===info.origin)return;}catch{}
      event.preventDefault();external(url);
    });
    backend.on('exit',({expected})=>{if(!expected&&!quitting){if(!smoke)dialog.showErrorBox('本地服务已退出','请重新打开 campusMate。已保存的资料仍保留在本机。');app.quit();}});
    await window.loadURL(info.origin);
    if(smoke){
      let state;
      const until=Date.now()+30000;
      while(Date.now()<until){
        state=await window.webContents.executeJavaScript('({node:typeof require,process:typeof process,ready:!!document.querySelector("[data-module-id=dashboard] .source-toolbar"),title:document.title,width:innerWidth,contentWidth:document.documentElement.scrollWidth})');
        if(state.ready)break;await new Promise(resolve=>setTimeout(resolve,100));
      }
      if(!state.ready||state.node!=='undefined'||state.process!=='undefined')throw new Error('桌面界面验证未通过。');
      fs.writeFileSync(smoke,JSON.stringify({...info,...state,version:app.getVersion()}));
      await new Promise(resolve=>setTimeout(resolve,Number(option('--smoke-hold')??0)));
      app.quit();
    }
  }).catch(async error=>{
    if(smoke)fs.writeFileSync(smoke,JSON.stringify({error:error.message}));
    else dialog.showErrorBox('campusMate 暂时无法启动',error.message);
    quitting=true;await backend?.stop();app.exit(1);
  });
}
