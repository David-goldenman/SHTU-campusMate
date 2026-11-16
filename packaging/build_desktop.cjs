const path=require('node:path'),fs=require('node:fs');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),deps=path.join(root,'.codex','desktop-build','node_modules');
const {build,Platform,Arch}=require(path.join(deps,'electron-builder'));
process.env.ELECTRON_BUILDER_CACHE=path.join(root,'.codex','cache','electron-builder');
process.env.ELECTRON_GET_USE_PROXY='true';
const config=JSON.parse(fs.readFileSync(path.join(root,'desktop','electron-builder.json')));
build({projectDir:path.join(root,'desktop'),targets:Platform.WINDOWS.createTarget(['dir'],Arch.x64),
 config:{...config,npmRebuild:false,electronDist:path.join(deps,'electron','dist'),extraResources:[],afterPack:async context=>{
   // Python's Windows CopyFile2 path handles the deeply nested Unicode runtime tree.
   const bundle=path.join(root,'.codex','windows-release','bundle');
   const result=spawnSync(path.join(bundle,'runtime','python','python.exe'),['-X','utf8','-c',
     'import shutil,sys; shutil.copytree(sys.argv[1],sys.argv[2],dirs_exist_ok=True)',bundle,path.join(context.appOutDir,'resources','campus')],
     {windowsHide:true,encoding:'utf8'});
   if(result.status!==0)throw new Error(result.stderr||result.error?.message||'Runtime copy failed');
 }}})
 .then(files=>console.log('Desktop build:',files)).catch(error=>{console.error(error);process.exit(1);});
