import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base=process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap=await(await fetch(base+'/api/v1/bootstrap')).json();
const modules=bootstrap.modules.filter(item=>['dashboard','academic-assistant'].includes(item.id));
const profile=resolve('.codex/tmp/chat-web-'+process.pid);await mkdir(profile,{recursive:true});
function browser(action){const r=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});assert.equal(r.status,0,r.stderr);}
function fixture(modules,categories){
 const original=window.fetch.bind(window),state=window.chatCheck={mode:'answer',unexpected:[],messages:[],chats:[],aborts:0,clipboard:'',profile:{major:'合成专业',cohort_year:2025,direction:'',weekly_hours:null,notes:''}};
 Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{state.clipboard=text;}}});
 const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
 const text='## 本周学习计划\n\n先复习 **向量叠加**，再安排作业。[1]\n\n- 阅读课件\n- 完成自检\n\n| 日期 | 内容 | 建议时长 | 说明 |\n| --- | --- | --- | --- |\n| 周一 | 向量复习 | 30 分钟 | 估计时长 |\n| 周二 | 练习 | 40 分钟 | 自行调整 |\n\n```python\nprint("review")\n```\n\n<script>bad()</script> [危险](javascript:alert(1)) ![外部图片](https://example.edu/tracker.png)\n\n'+Array.from({length:12},(_,i)=>'第 '+(i+1)+' 步：阅读课件后用自己的话解释这个概念，标出还需要补充的问题。').join('\n\n');
 window.fetch=async(url,options={})=>{
  const target=new URL(url,location.origin);if(!target.pathname.startsWith('/api/v1/'))return original(url,options);
  const path=target.pathname.replace('/api/v1',''),method=options.method||'GET';
  if(path==='/bootstrap')return json({version:'synthetic',csrf_token:'synthetic',modules,categories});
  if(path==='/modules')return json({modules,categories});
  if(path==='/settings')return json({port:16666,active_port:16666,restart_required:false,storage:{directory:'.private',encryption:'Synthetic'}});
  if(path==='/data/backups')return json({backups:[]});
  if(path==='/auth/providers')return json({providers:[]});
  if(path==='/ai/settings')return json({enabled:true,key_saved:true,model:'deepseek-flash'});
  if(path==='/modules/dashboard/snapshot')return json({status:'ready',updated_at:'2026-10-17T00:00:00+08:00',stats:{courses:6,pending:3,materials:24,ready_sources:1},upcoming:[],notifications:[],agenda:[],data:{issues:[],metadata:{source_metadata:{blackboard:{status:"ready"}}}}});
  if(path==='/modules/academic-assistant/presets')return json({items:[{label:'安排作业',prompt:'安排合成作业'},{label:'准备复习',prompt:'准备合成复习'}]});
  if(path==='/modules/academic-assistant/profile'){if(method==='PUT')state.profile=JSON.parse(options.body);return json({profile:state.profile,academic:{}});}
  if(path==='/modules/academic-assistant/chat')return json({messages:state.messages,conversation_id:state.active_id,owner:'synthetic-owner'});
  if(path==='/modules/academic-assistant/conversations'){
    if(method==='POST'){state.active_id=String(state.chats.length+1).padStart(32,'0');state.messages=[];const item={id:state.active_id,title:'合成对话 '+(state.chats.length+1),archived:false,updated_at:'2026-10-17T00:00:0'+state.chats.length+'Z',messages:state.messages};state.chats.push(item);return json(item);}
    return json({items:state.chats,active_id:state.active_id});
  }
  if(path.startsWith('/modules/academic-assistant/conversations/')){
    const identity=path.split('/')[4],item=state.chats.find(item=>item.id===identity);
    if(method==='PUT'){Object.assign(item,JSON.parse(options.body));return json(item);}
    if(method==='DELETE'){state.chats=state.chats.filter(item=>item.id!==identity);if(state.active_id===identity){state.active_id=state.chats[0]?.id;state.messages=state.chats[0]?.messages||[];}return json({deleted:true});}
    state.active_id=identity;state.messages=item.messages;return json({conversation:item,messages:item.messages});
  }
  if(path==='/modules/academic-assistant/chat/stream'){
   const mode=state.mode,body=JSON.parse(options.body),messages=state.chats.find(item=>item.id===body.conversation_id).messages;let closed=false;
   const stream=new ReadableStream({start(controller){
    const emit=value=>{if(!closed)controller.enqueue(new TextEncoder().encode(JSON.stringify(value)+'\n'));};
    options.signal?.addEventListener('abort',()=>{if(!closed){closed=true;state.aborts++;controller.error(new DOMException('aborted','AbortError'));}},{once:true});
    (async()=>{
     emit({type:'activity',steps:[{name:'document',label:'读取作业或课件页码',status:'running'}]});await new Promise(r=>setTimeout(r,200));
     if(mode==='error'){emit({type:'error',status:409,detail:'合成来源暂未连接，请重新连接。'});closed=true;controller.close();return;}
     emit({type:'reset'});emit({type:'delta',text});
     await new Promise(r=>setTimeout(r,mode==='hold'?4000:1200));if(closed)return;
     if(mode==='truncated'){closed=true;controller.close();return;}
     emit({type:'delta',text:'\n\n**根据实际进度调整。**'});
     const answer={role:'assistant',text:text+'\n\n**根据实际进度调整。**',model:'deepseek-flash',created_at:'2026-10-17T00:00:00+08:00',citations:[3,4].map(page=>({source_id:'synthetic:page:'+page,record_id:'synthetic:slides',title:'合成课件.pdf',quote:'<script>synthetic</script> Vectors add by components.',page,kind:'pdf',url:'https://example.edu/course',download_url:'/api/v1/modules/blackboard/file?material_id=synthetic'})),navigation:null,tools:[]};
     messages.push({role:'user',text:body.message},answer);emit({type:'complete',message:answer});closed=true;controller.close();
    })();
   },cancel(){closed=true;}});
   return new Response(stream,{headers:{'Content-Type':'application/x-ndjson'}});
  }
  state.unexpected.push(path);return json({detail:'Unexpected synthetic API'},400);
 };
}
let socket;browser('open');
try{
 const port=(await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0],tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((ok,no)=>{socket.addEventListener('open',ok,{once:true});socket.addEventListener('error',no,{once:true});});
 let serial=0;const pending=new Map(),errors=[];
 socket.addEventListener('message',({data})=>{const m=JSON.parse(data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.no(new Error(JSON.stringify(m.error))):p.ok(m.result);}});
 const command=(method,params={})=>new Promise((ok,no)=>{const id=++serial,timer=setTimeout(()=>no(new Error(method)),20000);pending.set(id,{ok,no,timer});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(r=>{assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;});
 await command('Page.enable');await command('Runtime.enable');await command('Network.enable');await command('Network.setBlockedURLs',{urls:[base+'/api/v1/*']});
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)})`});
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url:base+'/#dashboard'});
 await evaluate(`window.waitFor=async condition=>{for(let i=0;i<160;i++){if(condition())return;await new Promise(r=>setTimeout(r,50));}throw new Error('UI condition timed out');};waitFor(()=>document.querySelector('[data-chat-form]'))`);
 await evaluate(`new Promise(r=>setTimeout(r,200))`);
 assert(await evaluate(`!document.querySelector('.module-zone').classList.contains('module-focus')`),'Homepage starts with deadlines visible');
 assert(await evaluate(`document.querySelector('[data-history-toggle]>span').textContent==='历史对话' && getComputedStyle(document.querySelector('[data-history-toggle]>span')).display!=='none'`),'History has a visible text label');
 await evaluate(`document.querySelector('[data-history-toggle]').click();waitFor(()=>document.querySelector('[data-history-toggle]').getAttribute('aria-expanded')==='true')`);
 assert(await evaluate(`document.activeElement.matches('[data-history-search]')`),'History opens at search');
 await evaluate(`document.querySelector('[data-history-close]').click()`);
 assert(await evaluate(`document.activeElement.matches('[data-history-toggle]')`),'Closing history returns focus to its entry');
 await evaluate(`document.querySelector('[data-home]').click()`);
 await evaluate(`document.querySelector('[data-home]').click();true`);
 assert(await evaluate(`document.querySelector('#study-message').getBoundingClientRect().bottom<innerHeight`),'desktop input visible');
 await evaluate(`document.querySelector('[data-profile-toggle]').click();document.querySelector('[name=direction]').value='保留草稿';document.querySelector('[data-profile-form]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.study-prompts').open=true;document.querySelector('[data-example="0"]').click();document.querySelector('[data-chat-form]').requestSubmit();true`);
 await evaluate(`waitFor(()=>document.querySelector('.study-streaming h2'))`);
 assert(await evaluate(`document.querySelector('#study-message').disabled && !document.querySelector('[data-stop]').hidden`));
 await evaluate(`(()=>{const node=document.querySelector('[data-messages]');node.scrollTop=0;node.dispatchEvent(new Event('scroll'));return true;})()`);
 await evaluate(`waitFor(()=>!document.querySelector('#study-message').disabled)`);
 assert(await evaluate(`document.querySelector('[data-messages]').scrollTop===0 && !document.querySelector('[data-latest]').hidden`),'stream leaves reading position');
 const result=await evaluate(`(()=>{const root=document.querySelector('.academic-chat');root.querySelector('.study-references').open=true;return {headings:root.querySelectorAll('.study-markdown h2').length,strong:root.querySelectorAll('.study-markdown strong').length,tables:root.querySelectorAll('.study-table table').length,codes:root.querySelectorAll('pre code').length,scripts:root.querySelectorAll('script').length,images:root.querySelectorAll('img').length,groups:root.querySelectorAll('.study-reference-list article').length,labels:root.querySelector('.study-references').textContent,draft:root.querySelector('[name=direction]').value};})()`);
 assert.equal(result.headings,1);assert(result.strong>=2);assert.equal(result.tables,1);assert.equal(result.codes,1);assert.equal(result.scripts,0);assert.equal(result.images,0);assert.equal(result.groups,1);assert.match(result.labels,/第 3 页/);assert.match(result.labels,/第 4 页/);assert.equal(result.draft,'保留草稿');
 await evaluate(`document.querySelector('.study-copy-code').click();waitFor(()=>chatCheck.clipboard.includes('print('))`);
 await writeFile(resolve('.codex/tmp/chat-markdown-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 assert(await evaluate(`document.querySelector('[data-messages]').clientHeight>=350`),'Focused conversation uses the viewport height');
 assert(await evaluate(`(()=>{const width=document.querySelector('.study-assistant .study-text').getBoundingClientRect().width;return width>=600&&width<=800;})()`),'Desktop reply keeps a comfortable reading width');
 await evaluate(`document.querySelector('[data-new-chat]').click();waitFor(()=>chatCheck.chats.length===2&&!!document.querySelector('.study-welcome'))`);
 assert(await evaluate(`document.querySelector('.module-zone').classList.contains('module-focus')`),'Explicit new chat opens the composer even when empty');
 await evaluate(`document.querySelector('[data-history-toggle]').click();waitFor(()=>document.querySelectorAll('[data-open-chat]').length===2).then(()=>document.querySelectorAll('[data-open-chat]')[1].click()).then(()=>waitFor(()=>document.querySelectorAll('.study-message').length===2))`);
 await evaluate(`document.querySelector('[data-history-toggle]').click();waitFor(()=>!document.querySelector('.study-history').hidden).then(()=>{const search=document.querySelector('[data-history-search]');search.value='不存在的对话';search.dispatchEvent(new Event('input'));})`);
 assert.equal(await evaluate(`document.querySelectorAll('[data-open-chat]').length`),0,'History search filters the visible list');
 await evaluate(`(()=>{const search=document.querySelector('[data-history-search]');search.value='';search.dispatchEvent(new Event('input'));const button=[...document.querySelectorAll('[data-archive-chat]')].find(node=>node.dataset.archiveChat===chatCheck.active_id);button.closest('details').open=true;button.click();return waitFor(()=>chatCheck.chats[0].archived);})()`);
 assert(await evaluate(`document.querySelector('[data-send]').disabled`),'Archived conversation is readable and cannot receive messages');
 await evaluate(`document.querySelector('[data-history-filter=archived]').click();document.querySelector('[data-archive-chat]').closest('details').open=true;document.querySelector('[data-archive-chat]').click();waitFor(()=>!chatCheck.chats[0].archived)`);
 await evaluate(`(()=>{document.querySelector('[data-history-filter=active]').click();const button=[...document.querySelectorAll('[data-delete-chat]')].find(node=>node.dataset.deleteChat!==chatCheck.active_id);button.closest('details').open=true;button.click();return waitFor(()=>document.querySelector('dialog[open] [value=confirm]')).then(()=>document.querySelector('dialog[open] [value=confirm]').click()).then(()=>waitFor(()=>chatCheck.chats.length===1)).then(()=>document.querySelector('[data-history-close]').click());})()`);
 await command('Emulation.setDeviceMetricsOverride',{width:1366,height:768,deviceScaleFactor:1,mobile:false});await evaluate(`new Promise(r=>setTimeout(r,200))`);
 assert(await evaluate(`document.querySelector('#study-message').getBoundingClientRect().bottom<innerHeight`),'small desktop input visible');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await evaluate(`new Promise(r=>setTimeout(r,200))`);
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`));assert(await evaluate(`document.querySelector('#study-message').getBoundingClientRect().bottom<innerHeight`),'mobile input visible');
 assert(await evaluate(`document.querySelector('[data-history-toggle]>span').getBoundingClientRect().width>40`),'History label remains visible on mobile');
 await evaluate(`document.querySelector('[data-history-toggle]').click();waitFor(()=>!document.querySelector('.study-history').hidden)`);
 assert(await evaluate(`document.querySelector('.study-conversation').inert && getComputedStyle(document.querySelector('.study-history-scrim')).display==='block'`),'History drawer separates the underlying conversation');
 await evaluate(`document.querySelector('.study-history-scrim').click()`);
 assert(await evaluate(`!document.querySelector('.study-conversation').inert && document.activeElement.matches('[data-history-toggle]')`),'Closing the drawer restores its entry and the conversation');
 await writeFile(resolve('.codex/tmp/chat-markdown-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 for(const mode of ['hold','error','truncated']){
  await evaluate(`chatCheck.mode='${mode}';document.querySelector('#study-message').value='合成重试问题';document.querySelector('[data-chat-form]').requestSubmit();true`);
  if(mode==='hold')await evaluate(`waitFor(()=>document.querySelector('.study-streaming h2')).then(()=>document.querySelector('[data-stop]').click())`);
  await evaluate(`waitFor(()=>!document.querySelector('#study-message').disabled && !!document.querySelector('[data-error]').textContent)`);
  assert.equal(await evaluate(`document.querySelector('#study-message').value`),'合成重试问题');assert.equal(await evaluate(`document.querySelectorAll('.study-message').length`),2);
 }
 await evaluate(`chatCheck.mode='hold';document.querySelector('[data-chat-form]').requestSubmit();waitFor(()=>document.querySelector('.study-streaming h2')).then(()=>document.querySelector('[data-new-chat]').click()).then(()=>waitFor(()=>chatCheck.chats.length===2&&!document.querySelector('[data-return-running]').hidden))`);
 assert(await evaluate(`!document.querySelector('#study-message').disabled`),'A second conversation remains editable while the original generates');
 await evaluate(`document.querySelector('[data-return-running]').click();waitFor(()=>document.querySelector('.study-streaming h2')).then(()=>document.querySelector('.study-model').click()).then(()=>waitFor(()=>document.querySelector('[data-settings-tab="ai"][aria-selected="true"]')))`);
 assert.equal(await evaluate(`chatCheck.aborts`),1,'Leaving an active chat keeps the request running; only explicit Stop aborts');
 assert.equal(await evaluate(`!!document.querySelector('link[href*="/academic-assistant/"]')`),false);
 await evaluate(`document.querySelector('[data-nav="dashboard"]').click();waitFor(()=>document.querySelector('[data-chat-form]'))`);
 await evaluate(`waitFor(()=>!document.querySelector('#study-message').disabled)`);
 assert.equal(await evaluate(`document.querySelectorAll('.study-message').length`),4,'Returning restores the same turn exactly once');
 await evaluate(`document.querySelector('[data-new-chat]').click();waitFor(()=>chatCheck.chats.length===3&&!!document.querySelector('.study-welcome'))`);
 await evaluate(`document.querySelector('[data-history-toggle]').click();waitFor(()=>document.querySelectorAll('[data-open-chat]').length===3).then(()=>document.querySelector('[data-open-chat="'+chatCheck.chats[0].id+'"]').click()).then(()=>waitFor(()=>document.querySelectorAll('.study-message').length===4))`);
 await evaluate(`chatCheck.mode='answer';document.querySelector('#study-message').value='回车合成问题';document.querySelector('#study-message').focus();true`);
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,modifiers:8,text:'\r'});
 await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,modifiers:8});
 assert(await evaluate(`!document.querySelector('#study-message').disabled && document.querySelector('#study-message').value.includes(String.fromCharCode(10))`),'Shift+Enter inserts a line break');
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
 await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
 await evaluate(`waitFor(()=>document.querySelector('#study-message').disabled).then(()=>waitFor(()=>!document.querySelector('#study-message').disabled))`);
 assert.equal(await evaluate(`document.querySelectorAll('.study-message').length`),6,'Enter sends once after returning to the homepage');
 assert.deepEqual(await evaluate(`chatCheck.unexpected`),[]);assert.deepEqual(errors,[]);
 console.log('PASS chat UI: real progressive rendering, Markdown security, grouped pages, copy, reading position, desktop/mobile input visibility, stop, retry, truncated stream, AI settings and cleanup');
}finally{socket?.close();browser('close');}
