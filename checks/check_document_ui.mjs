import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.argv[2]||'http://127.0.0.1:16666';
const profile=resolve('.codex/tmp/document-ui-'+process.pid);await mkdir(profile,{recursive:true});
function browser(action){const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr);}
function fixture(){
  const original=window.fetch.bind(window),state=window.visionCheck={writes:[],vision:{enabled:false,base_url:'https://api.openai.com/v1',protocol:'openai-completions',model:'',supports_images:false,quality_confirmed:false,key_saved:false,ready:false},reader:{mode:'auto',fallback:true,ocr_backend:'windows',docling_python:'',max_pages:4}};
  const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname,method=options.method||'GET';
    if(path==='/api/v1/ai/settings')return json({enabled:false,provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',key_saved:false,vision:state.vision});
    if(path==='/api/v1/ai/vision/settings'){
      if(method==='PUT'){const body=JSON.parse(options.body);state.writes.push({path,model:body.model});const {api_key,delete_key,...safe}=body;state.vision={...safe,key_saved:delete_key?false:!!api_key||state.vision.key_saved,ready:false};}
      return json(state.vision);
    }
    if(path==='/api/v1/modules/academic-assistant/reader/settings'){
      if(method==='PUT'){state.reader=JSON.parse(options.body);state.writes.push({path,mode:state.reader.mode});}
      return json({...state.reader,vision:state.vision});
    }
    if(method!=='GET')throw new Error('Unexpected write: '+path);
    return original(url,options);
  };
}
let socket;
browser('open');
try{
  const port=(await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0];
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let serial=0;const pending=new Map();
  socket.addEventListener('message',({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(!p)return;clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);});
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>reject(new Error(method)),20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(r=>{assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;});
  const wait=expression=>evaluate(`(async()=>{for(let i=0;i<120;i++){if(${expression})return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timed out: '+${JSON.stringify(expression)});})()`);
  await command('Page.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})()`});
  await command('Page.navigate',{url:base+'/#settings?tab=ai'});
  await wait("document.querySelector('[data-vision-form]')");
  await evaluate("window.preSaveForm=document.querySelector('[data-vision-form]');preSaveForm.closest('details').open=true;var f=preSaveForm.elements;f.model.value='synthetic-image-model';f.api_key.value='synthetic-ui-key';f.supports_images.checked=f.quality_confirmed.checked=f.enabled.checked=true;preSaveForm.requestSubmit()");
  await wait("visionCheck.writes.length===1 && document.querySelector('[data-vision-form]')!==preSaveForm && document.querySelector('[data-vision-form] [name=api_key]')?.value===''");
  assert.equal(await evaluate("document.querySelector('[data-vision-form] [name=model]').value"),'synthetic-image-model');
  assert.equal(await evaluate("document.querySelector('.ai-provider-info').textContent.includes('deepseek-flash')"),true);
  await evaluate("document.querySelector('[data-vision-form]').closest('details').open=true;var f=document.querySelector('[data-vision-form]').elements;f.model.value='another-model';f.model.dispatchEvent(new Event('input',{bubbles:true}))");
  assert(await evaluate("!document.querySelector('[data-vision-form] [name=supports_images]').checked && !document.querySelector('[data-vision-form] [name=quality_confirmed]').checked"));
  for(const [width,height,label] of [[1280,1100,'desktop'],[390,844,'mobile']]){
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<800});
    await wait("innerWidth>850 || document.querySelector('.sidebar').getBoundingClientRect().right<=0");
    await evaluate("document.querySelector('[data-vision-form]').closest('details').open=true;new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    await writeFile(resolve('.codex/tmp/vision-settings-'+label+'.png'),Buffer.from((await command('Page.captureScreenshot',{captureBeyondViewport:true})).data,'base64'));
  }
  await evaluate("window.oldVisionForm=document.querySelector('[data-vision-form]');oldVisionForm.elements.api_key.value='synthetic-draft';location.hash='dashboard'");
  await wait("document.querySelector('.study-menu')");
  assert.equal(await evaluate('oldVisionForm.elements.api_key.value'),'');
  await evaluate("[...document.querySelectorAll('.study-menu button')].find(b=>b.textContent==='资料读取').click()");
  await wait("document.querySelector('dialog[open] [name=ocr_backend]')");
  await evaluate("var f=document.querySelector('dialog[open] form');f.elements.mode.value='local';f.elements.mode.dispatchEvent(new Event('change'));f.elements.max_pages.value='2';f.requestSubmit()");
  await wait("visionCheck.reader.mode==='local' && !document.querySelector('dialog[open]')");
  assert.equal(await evaluate('visionCheck.reader.max_pages'),2);
  await evaluate("[...document.querySelectorAll('.study-menu button')].find(b=>b.textContent==='资料读取').click()");
  await wait("document.querySelector('dialog[open] [name=mode]')?.value==='local'");
  assert(await evaluate("document.querySelector('dialog[open] [name=fallback]').disabled"));
  await writeFile(resolve('.codex/tmp/reader-settings-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await evaluate("location.hash='settings?tab=ai'");
  await wait("document.querySelector('[data-vision-form]') && !document.querySelector('dialog[open]')");
  assert.equal(await evaluate('visionCheck.writes.length'),2);
  console.log('PASS: independent visual settings, quality reset, secret-draft cleanup, desktop/mobile layout, reader preferences and dialog lifecycle');
}finally{socket?.close();browser('close');}
