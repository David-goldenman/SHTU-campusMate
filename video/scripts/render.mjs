import {mkdir,writeFile,rename} from 'node:fs/promises';
import assert from 'node:assert/strict';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {archive} from './archive.mjs';
import {sourceVersion} from './source-version.mjs';
import {reviewOffsets} from './review.mjs';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..'),work=resolve(video,'../.codex/video');
process.chdir(video);
for(const name of ['TEMP','TMP','TMPDIR'])process.env[name]=resolve(work,'tmp');
await mkdir(resolve(work,'tmp'),{recursive:true});
const {bundle}=await import('@remotion/bundler');
const {openBrowser,selectComposition,renderMedia,renderStill}=await import('@remotion/renderer');
const film=JSON.parse(readFileSync(resolve(video,'src/film.json'),'utf8'));
const operations=JSON.parse(readFileSync(resolve(video,'src/operations.json'),'utf8'));
const browser=await openBrowser('chrome',{chromiumOptions:{gl:'angle'},logLevel:'info'});
try {
  const serveUrl=await bundle({entryPoint:resolve(video,'src/index.ts'),outDir:resolve(work,'bundle'),publicDir:resolve(video,'public'),rootDir:video,enableCaching:true});
  const composition=await selectComposition({serveUrl,id:'CampusHub',puppeteerInstance:browser});
  console.log(`CampusHub: ${composition.width}x${composition.height}, ${composition.fps}fps, ${composition.durationInFrames} frames`);
  if(process.argv.includes('--stills')){
    const out=resolve(work,'stills');await mkdir(out,{recursive:true});
    let cursor=0;const manifest=[];
    for(const scene of film.scenes){
      const offsets=reviewOffsets(scene,operations);
      for(const [index,seconds] of offsets.entries()){
        const frame=Math.floor((cursor+seconds)*film.fps),name=scene.id+'-'+index+'.png';
        await renderStill({serveUrl,composition,puppeteerInstance:browser,frame,output:resolve(out,name),imageFormat:'png',logLevel:'error'});
        manifest.push({scene:scene.id,frame,seconds:cursor+seconds,file:name});console.log('Still '+name);
      }
      cursor+=scene.seconds;
    }
    for(const scene of ['mail','schedule','themes']){
      const at=film.scenes.slice(0,film.scenes.findIndex(s=>s.id===scene)).reduce((n,s)=>n+s.seconds,0);
      for(const delta of [-1,-.55,.05,.6,1.1]){
        const name=`transition-${scene}-${delta}.png`,frame=Math.round((at+delta)*film.fps);
        await renderStill({serveUrl,composition,puppeteerInstance:browser,frame,output:resolve(out,name),imageFormat:'png',logLevel:'error'});
        manifest.push({scene:'transition-'+scene,frame,seconds:at+delta,file:name});
      }
    }
    await writeFile(resolve(out,'manifest.json'),JSON.stringify(manifest,null,2));
  }else{
    await archive();
    const version=await sourceVersion(),pending=resolve(work,'rendered.mp4');
    await mkdir(resolve(video,'output'),{recursive:true});let bucket=-1;
    const result=await renderMedia({serveUrl,composition,puppeteerInstance:browser,outputLocation:pending,codec:'h264',crf:14,pixelFormat:'yuv420p',x264Preset:'fast',audioBitrate:'256k',imageFormat:'png',concurrency:8,logLevel:'error',onProgress:({progress,renderedFrames})=>{const current=Math.floor(progress*20);if(current!==bucket){bucket=current;console.log(`Rendering ${Math.round(progress*100)}% / ${renderedFrames} frames`);}},metadata:{title:'campusMate · 校园工作台',artist:'AAA罗德岛工程部',comment:'PERSONAL LEARNING TERMINAL | Nord 真实界面 · 演示数据与对话重放'}});
    assert.equal((await sourceVersion()).sha256,version.sha256,'导出期间界面源码已更新，请同步素材后重新导出。');
    await rename(pending,resolve(video,'output/校园工作台.mp4'));
    await writeFile(resolve(work,'render-result.json'),JSON.stringify(result,null,2));
    console.log('Rendered output/校园工作台.mp4');
  }
}finally{await browser.close({silent:true});}

