import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {installFixture} from './fixture.mjs';
import {installReplayFixture} from './replay-fixture.mjs';
import {installReplay,waitForStyles} from './replay.mjs';
import {encode} from './encode.mjs';
import {installFeatures} from './features.mjs';
import {sourceVersion} from './source-version.mjs';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..'),root=resolve(video,'..'),work=resolve(root,'.codex/video');
const base='http://127.0.0.1:17666',profile=resolve(work,'replay-browser-'+process.pid),fps=60;
for(const key of ['TEMP','TMP','TMPDIR'])process.env[key]=resolve(work,'tmp');
await Promise.all([mkdir(profile,{recursive:true}),mkdir(resolve(video,'public/recordings'),{recursive:true}),mkdir(resolve(video,'public/screens'),{recursive:true})]);
const definitions=JSON.parse(await readFile(resolve(video,'src/operations.json'),'utf8'));
const source=JSON.parse(await readFile(resolve(video,'production/source-data.json'),'utf8'));
source.curriculum=JSON.parse(await readFile(resolve(video,'production/curriculum.json'),'utf8'));
source.groupChats=JSON.parse(await readFile(resolve(video,'production/group-chats.json'),'utf8'));
const dialogues=JSON.parse(await readFile(resolve(video,'production/dialogues.json'),'utf8'));
source.map=JSON.parse(await readFile(resolve(root,'modules/campus-map/data/places.json'),'utf8'));
source.map.basemap=JSON.parse(await readFile(resolve(root,'modules/campus-map/data/osm-basemap.json'),'utf8'));
source.walking=JSON.parse(await readFile(resolve(root,'modules/campus-map/data/walking-network.json'),'utf8'));
const [bootstrap,themes]=await Promise.all(['/bootstrap','/themes'].map(p=>fetch(base+'/api/v1'+p).then(r=>{assert(r.ok);return r.json();})));
const child=spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',[`--user-data-dir=${profile}`,`--disk-cache-dir=${resolve(profile,'cache')}`,'--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--headless=new','--disable-gpu','--disable-extensions','--disable-component-extensions-with-background-pages','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--no-first-run','--no-default-browser-check','about:blank'],{windowsHide:true,stdio:'ignore',env:process.env});
let socket;
const manifest=[];
try {
  let port;
  for(let n=0;n<100;n++){try{port=(await readFile(resolve(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0];await fetch(`http://127.0.0.1:${port}/json/version`);break;}catch{await new Promise(r=>setTimeout(r,100));}}
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((ok,no)=>{socket.addEventListener('open',ok,{once:true});socket.addEventListener('error',no,{once:true});});
  let serial=0,setup;const pending=new Map(),errors=[];
  socket.addEventListener('message',({data})=>{const m=JSON.parse(data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text);const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.no(new Error(JSON.stringify(m.error))):p.ok(m.result);}});
  const call=(method,params={})=>new Promise((ok,no)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);no(new Error(method+' timed out'));},30000);pending.set(id,{ok,no,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=expression=>call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(r=>{assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;});
  const wait=selector=>evaluate(`(async()=>{for(let n=0;n<200;n++){if(document.querySelector(${JSON.stringify(selector)}))return;await new Promise(r=>setTimeout(r,40));}throw new Error('View not ready: '+${JSON.stringify(selector)});})()`);
  await call('Page.enable');await call('Runtime.enable');await call('Network.enable');
  await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Page.bringToFront');await call('Emulation.setFocusEmulationEnabled',{enabled:true});
  await call('Network.setBlockedURLs',{urls:[base+'/api/v1/*']});
  const selected=process.argv.slice(2).filter(a=>!a.startsWith('--'));
  for(const definition of definitions.filter(d=>!selected.length||selected.includes(d.id))){
    const {id,seconds,theme='default',mode='empty'}=definition,folder=resolve(work,'recordings',id);
    const version=await sourceVersion();
    const mobile=definition.mobile===true,width=mobile?430:1472,height=mobile?860:720,density=mobile?2:1.875;
    await call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:density,mobile});
    await mkdir(folder,{recursive:true});errors.length=0;
    if(setup)await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:setup});
    const injected=`window.filmStyleReady=${waitForStyles.toString()};(${installFixture.toString()})(${JSON.stringify(bootstrap)},${JSON.stringify(themes)},${JSON.stringify(theme)},'empty');window.filmPrepared=(async()=>{await (${installReplayFixture.toString()})(${JSON.stringify(source)},${JSON.stringify(mode)},${JSON.stringify(dialogues)});await (${installFeatures.toString()})(${JSON.stringify(source)});})();`;
    setup=(await call('Page.addScriptToEvaluateOnNewDocument',{source:injected})).identifier;
    await call('Page.navigate',{url:base+'/?film-replay='+id+definition.route});
    try {
      await evaluate('window.filmPrepared');await wait(definition.ready);await evaluate('window.filmStyleReady()');
      if(definition.focus){await evaluate("document.querySelector('[data-home]').click()");await wait('.module-focused .academic-chat');}
      await evaluate('new Promise(r=>setTimeout(r,400))');
      await evaluate(`(${installReplay.toString()})(${JSON.stringify(definition)})`);
      assert.equal(await evaluate('document.documentElement.dataset.theme'),theme);
      const samples=[];let last;
      for(let frame=0;frame<Math.round(seconds*fps);frame++){
        const t=frame/fps,result=await evaluate(`window.filmDemo.advance(${t})`);
        assert.deepEqual(result.unexpected,[],id);
        assert(!result.invalidDialog,'Incomplete dialog data: '+id);
        for(const capture of result.captures){
          const rect=await evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(capture.selector)});const r=n.getBoundingClientRect();return {x:Math.floor(r.x+scrollX),y:Math.floor(r.y+scrollY),width:Math.ceil(r.width),height:Math.ceil(r.height),scale:1};})()`);
          const png=Buffer.from((await call('Page.captureScreenshot',{format:'png',optimizeForSpeed:true,clip:rect,captureBeyondViewport:true})).data,'base64');
          await writeFile(resolve(video,'public/screens',capture.name+'.png'),png);
        }
        if(result.dirty||frame===0){
          const name=String(samples.length).padStart(5,'0')+'.png';
          const png=Buffer.from((await call('Page.captureScreenshot',{format:'png',optimizeForSpeed:true,captureBeyondViewport:false})).data,'base64');
          assert.equal(png.readUInt32BE(16),width*density);assert.equal(png.readUInt32BE(20),height*density);
          await writeFile(resolve(folder,name),png);samples.push({frame,name});last=png;
        }
        if(frame%300===0)console.log(id+' '+t.toFixed(0)+' / '+seconds+'s');
        if(result.next>t+1/fps)frame=Math.min(Math.round(seconds*fps)-1,Math.ceil(result.next*fps)-1);
      }
      await writeFile(resolve(video,'public/screens',id+'.png'),last);
      const list=samples.map((s,i)=>`file '${s.name}'\nduration ${((samples[i+1]?.frame??seconds*fps)-s.frame)/fps}`).join('\n')+`\nfile '${samples.at(-1).name}'\n`;
      await writeFile(resolve(folder,'frames.txt'),list);await writeFile(resolve(folder,'samples.json'),JSON.stringify(samples));
      await encode(folder,resolve(video,'public/recordings',id+'.mp4'),seconds,fps);
      const final=await evaluate('window.filmDemo.advance('+((seconds*fps-1)/fps)+')');
      const report={id,theme,route:definition.route,width:width*density,height:height*density,fps,seconds,captures:samples.length,framing:final.framing,pointer:final.pointer,unexpected:await evaluate('window.filmDemo.unexpected'),stream:await evaluate('window.filmDemo.replayEvents'),errors:[...errors],source:'真实前端；脱敏素材；代码操作与流式协议重放'};
      assert.deepEqual(errors,[],id);
      report.version=version;
      assert.equal((await sourceVersion()).sha256,version.sha256,'界面源码在录制期间发生变化，请同步后重录：'+id);
      if(['schedule','study','advising'].includes(id)){assert(report.stream.includes('delta'));assert(report.stream.includes('complete'));}
      await writeFile(resolve(folder,'report.json'),JSON.stringify(report,null,2));manifest.push(report);console.log('Recorded '+id+' / '+samples.length+' unique frames');
    }catch(error){
      await writeFile(resolve(folder,'error.png'),Buffer.from((await call('Page.captureScreenshot')).data,'base64'));
      console.error(await evaluate('JSON.stringify({text:document.body.innerText,unexpected:filmDemo.unexpected,errors:document.querySelector(".module-error")?.innerText})'));
      throw error;
    }
  }
  const reports=[];for(const d of definitions){try{reports.push(JSON.parse(await readFile(resolve(work,'recordings',d.id,'report.json'),'utf8')));}catch{}}
  await writeFile(resolve(video,'production/captures.json'),JSON.stringify(reports,null,2));
  await writeFile(resolve(video,'src/framing.json'),JSON.stringify(Object.fromEntries(reports.map(r=>[r.id,r.framing||[]])),null,2));
}finally{if(socket?.readyState===WebSocket.OPEN){socket.send(JSON.stringify({id:999999,method:'Browser.close'}));socket.close();}child.unref();}
