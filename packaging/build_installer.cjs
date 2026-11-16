const path=require('node:path'),fs=require('node:fs');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),build=path.join(root,'.codex','windows-release');
process.env.ELECTRON_BUILDER_CACHE=path.join(root,'.codex','cache','electron-builder');
process.env.ELECTRON_GET_USE_PROXY='true';
const {getMakeNsisPath}=require(path.join(root,'.codex','desktop-build','node_modules','app-builder-lib','out','toolsets','windows.js'));
const quote=value=>"'"+value.replaceAll("'","''")+"'";
(async()=>{
 const compiler=await getMakeNsisPath('1.2.1');
 const version=JSON.parse(fs.readFileSync(path.join(root,'desktop','package.json'))).version;
 const output=path.join(build,'campusMate-'+version+'-Setup.exe');
 // NSIS's compile-time File walker still has MAX_PATH limits. The temporary alias
 // names only this generated payload; no files move and existing drives are skipped.
 let drive;
 for(const letter of ['Z','Y','X','W','V','U','T','S','R']){
   if(fs.existsSync(letter+':\\'))continue;
   const mapped=spawnSync('subst.exe',[letter+':',path.join(build,'desktop','win-unpacked')],{windowsHide:true});
   if(mapped.status===0){drive=letter+':';break;}
 }
 if(!drive)throw new Error('No temporary build drive is available');
 try{
   const args=['/V3','/DPAYLOAD='+drive+'\\','/DOUTPUT='+output,'/DSCRIPTS='+__dirname,path.join(__dirname,'installer.nsi')];
   const command='& '+[compiler.path,...args].map(quote).join(' ')+'; exit $LASTEXITCODE';
   const result=spawnSync('powershell.exe',['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-Command',command],
     {env:{...process.env,...compiler.env},windowsHide:true,stdio:'inherit'});
   if(result.status!==0)throw new Error('Installer compiler failed: '+result.status);
 }finally{spawnSync('subst.exe',[drive,'/D'],{windowsHide:true});}
 console.log('Installer:',output,fs.statSync(output).size);
})().catch(error=>{console.error(error);process.exit(1);});
