// Self-contained synthetic mailbox UI: no backend credentials, mail, AI or live service.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdir,mkdtemp,readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const project=fileURLToPath(new URL('../../../',import.meta.url));
await mkdir(resolve(project,'.codex/tmp'),{recursive:true});
const profile=await mkdtemp(resolve(project,'.codex/tmp/mail-outage-'));
function fixture(){
  const state=window.mailFixture={owner:'account-a',session:'session-1',epoch:'1',autoOwnerOverride:new URLSearchParams(location.search).has('initial-owner-race')?'account-b':null,failure:0,intelligenceFailure:0,ownerFailure:false,calls:[],writes:[]};
  const controller=new AbortController();
  const message=()=>({id:'mail:1',source_id:'1',title:state.owner+' notice',sender:'fixture@example.edu',received_at:'2026-11-16T12:00:00+08:00',unread:true,classification:{bucket:'focus',category:'Synthetic',reason:'fixture',summary:'Summary',by:'rule',review_pending:false}});
  const preferences=()=>({degree:'bachelor',year:2,major:state.owner,courses:[],shape:'unknown',mental:'unknown',interests:{research:'digest'},requirements:''});
  const context={signal:controller.signal,services:{},ui:{
    escape:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    useStyle:()=>()=>{},bindMenus:()=>{},toast:value=>{state.toast=value;},
    safeAction:(_button,action)=>async()=>{try{return await action();}catch(error){state.toast=error.message;}},
    dialog:(_title,form)=>{const dialog=document.createElement('dialog');dialog.append(form);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove(),{once:true});dialog.showModal();return dialog;},
  },api:async(path,options={})=>{
    state.calls.push(path);
    if(path==='/snapshot'){
      if(state.failure)throw Object.assign(new Error('Synthetic snapshot outage'),{status:state.failure});
      return {account_revision:state.snapshotOwnerOverride||state.owner,session_revision:state.snapshotSessionOverride||state.session,status:'ready',updated_at:'2026-11-16T04:00:00Z',data:{messages:[message()],metadata:{uid_validity:state.epoch},issues:[]}};
    }
    if(path==='/auto-sync'){
      if(state.ownerFailure)throw Object.assign(new Error('Cannot verify owner'),{status:503});
      return {owner:state.autoOwnerOverride||state.owner,session_revision:state.session,uid_validity:state.epoch,enabled:true,configured:true,state:'watching',revision:state.owner};
    }
    if(path==='/intelligence'){
      if(state.intelligenceFailure)throw Object.assign(new Error('Synthetic intelligence outage'),{status:state.intelligenceFailure});
      return {owner:state.owner,session_revision:state.session,uid_validity:state.epoch,messages:[message()],preferences:preferences(),effective_preferences:preferences(),buckets:{focus:'Focus',recommend:'Recommended',digest:'Digest',filter:'Filtered'},interests:{research:'Research'},review_status:{enabled:false}};
    }
    if(path.startsWith('/message?'))return {body_html:'<p>'+state.owner+' reader body</p>'+Array.from({length:50},()=>'<p>Reader scroll fixture</p>').join('')};
    if(path==='/preferences'&&options.method==='PUT'){state.writes.push({owner:state.owner,body:options.body});return {};}
    throw new Error('Unexpected synthetic API: '+path);
  }};
  state.abort=()=>controller.abort();
  import('/mail/web/index.js').then(module=>module.mount(document.querySelector('#mail'),context)).then(dispose=>{state.dispose=dispose;state.ready=true;}).catch(error=>{state.error=error.stack;});
}
const server=createServer(async(request,response)=>{
  try{
    const pathname=new URL(request.url,'http://localhost').pathname;
    if(pathname==='/'){
      response.setHeader('Content-Type','text/html; charset=utf-8');
      response.end('<!doctype html><meta charset="utf-8"><div id="mail"></div><style>.mail-reader{height:120px;overflow:auto}.mail-inbox{height:120px;overflow:auto}.mail-row{display:block}dialog{max-width:80vw}</style><script>('+fixture.toString()+')()</script>');return;
    }
    const folder=pathname.startsWith('/assets/')?resolve(project,'web'):pathname.startsWith('/mail/')?resolve(project,'modules/mail'):null;
    if(!folder){response.writeHead(404).end();return;}
    const relative=pathname.startsWith('/assets/')?pathname.slice(8):pathname.slice(6);
    const filename=resolve(folder,relative);
    if(!filename.startsWith(folder+sep)){response.writeHead(403).end();return;}
    response.setHeader('Content-Type',extname(filename)==='.js'?'text/javascript; charset=utf-8':'text/plain');
    response.end(await readFile(filename));
  }catch{response.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
function browser(action){const result=spawnSync(process.execPath,[resolve(project,'scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr);}
let socket;
try{
  browser('open');
  const port=(await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0];
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let serial=0;const pending=new Map();
  socket.addEventListener('message',({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(!p)return;clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);});
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>reject(new Error(method)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result=>{assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;});
  const wait=expression=>evaluate(`(async()=>{for(let i=0;i<100;i++){if(${expression})return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timed out: '+${JSON.stringify(expression)}+' '+window.mailFixture?.error);})()`);
  await command('Page.enable');
  if(process.argv.includes('--identity-only')){
    await command('Page.navigate',{url:base+'?initial-owner-race=1'});
    await wait('window.mailFixture?.ready || window.mailFixture?.error');
    assert.equal(await evaluate('Boolean(mailFixture.ready)'),false,'Initial intelligence A must not publish after status confirms owner B');
    assert.equal(await evaluate("Boolean(document.querySelector('.mail-columns'))"),false);
    console.log('PASS: initial intelligence/status owner mismatch rejected before publication');
  }else{
  await command('Page.navigate',{url:base});
  await wait('window.mailFixture?.ready');
  await evaluate("document.querySelector('[data-message]').click()");
  await wait("document.querySelector('[data-reader]').textContent.includes('account-a reader body')");
  await evaluate("window.originalColumns=document.querySelector('.mail-columns');window.originalReader=document.querySelector('[data-reader]');originalReader.scrollTop=100;document.querySelector('[data-search]').value='account-a';document.querySelector('[data-preferences]').click();window.oldDraft=document.querySelector('dialog[open] form');oldDraft.elements.requirements.value='Unsaved preference draft';mailFixture.failure=503;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-status]').textContent.includes('保留当前页面')");
  assert(await evaluate("document.querySelector('.mail-columns')===originalColumns && document.querySelector('[data-reader]')===originalReader && originalReader.scrollTop===100"),'A same-owner outage keeps reader DOM and scroll');
  assert.equal(await evaluate("document.querySelector('[data-search]').value"),'account-a');
  assert.equal(await evaluate("document.querySelector('dialog[open] [name=requirements]').value"),'Unsaved preference draft');
  await evaluate("mailFixture.failure=0;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-status]').textContent==='数据状态'");
  assert(await evaluate("document.querySelector('.mail-columns')===originalColumns && document.querySelector('[data-reader]')===originalReader"),'Recovery keeps the existing reading view');
  assert.equal(await evaluate("document.querySelector('dialog[open] [name=requirements]').value"),'Unsaved preference draft');
  await evaluate("mailFixture.owner='account-b';mailFixture.failure=503;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
  await evaluate('oldDraft.requestSubmit()');
  assert.equal(await evaluate('mailFixture.writes.length'),0,'A closed old-owner form cannot submit into the new account');
  await evaluate("mailFixture.failure=0;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-messages]')?.textContent.includes('account-b notice')");
  assert(await evaluate("!document.querySelector('#mail').textContent.includes('account-a') && document.querySelector('[data-search]').value===''"),'Changed-owner recovery rebuilds without old selection, search or mail');
  for(const [failure,ownerFailure] of [[503,true],[409,false]]){
    await evaluate(`document.querySelector('[data-preferences]').click();mailFixture.failure=${failure};mailFixture.ownerFailure=${ownerFailure};window.dispatchEvent(new Event('campus:mail-updated'))`);
    await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
    await evaluate("mailFixture.failure=0;mailFixture.ownerFailure=false;window.dispatchEvent(new Event('campus:mail-updated'))");
    await wait("document.querySelector('[data-messages]')?.textContent.includes('account-b notice')");
  }
  // Rendering can fail after a successful lightweight snapshot; it must use the same ownership gate.
  await evaluate("document.querySelector('[data-message]').click()");
  await wait("document.querySelector('[data-reader]').textContent.includes('account-b reader body')");
  await evaluate("window.intelligenceColumns=document.querySelector('.mail-columns');window.intelligenceReader=document.querySelector('[data-reader]');intelligenceReader.scrollTop=80;document.querySelector('[data-search]').value='account-b';document.querySelector('[data-preferences]').click();window.intelligenceDraft=document.querySelector('dialog[open] form');intelligenceDraft.elements.requirements.value='Draft during intelligence outage';mailFixture.intelligenceFailure=503;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-status]').textContent.includes('保留当前页面')");
  assert(await evaluate("document.querySelector('.mail-columns')===intelligenceColumns && document.querySelector('[data-reader]')===intelligenceReader && intelligenceReader.scrollTop===80"),'An intelligence 503 retains same-owner reader DOM and scroll');
  assert.equal(await evaluate("document.querySelector('dialog[open] [name=requirements]').value"),'Draft during intelligence outage');
  assert.equal(await evaluate("document.querySelector('[data-search]').value"),'account-b');
  await evaluate("mailFixture.intelligenceFailure=0;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-status]').textContent==='数据状态'");
  assert(await evaluate("document.querySelector('.mail-columns')===intelligenceColumns && document.querySelector('[data-reader]')===intelligenceReader"),'Intelligence recovery preserves the current reading view');
  assert.equal(await evaluate("document.querySelector('dialog[open] [name=requirements]').value"),'Draft during intelligence outage');
  await evaluate("mailFixture.owner='account-c';mailFixture.intelligenceFailure=503;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
  await evaluate('intelligenceDraft.requestSubmit()');
  assert.equal(await evaluate('mailFixture.writes.length'),0,'An intelligence failure after account change cannot leave writable old-owner forms');
  await evaluate("mailFixture.intelligenceFailure=0;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-messages]')?.textContent.includes('account-c notice')");
  assert(await evaluate("!document.querySelector('#mail').textContent.includes('account-b') && document.querySelector('[data-search]').value===''"),'Intelligence owner changes rebuild without stale mail or filters');
  for(const [failure,ownerFailure] of [[503,true],[409,false]]){
    await evaluate(`document.querySelector('[data-preferences]').click();mailFixture.intelligenceFailure=${failure};mailFixture.ownerFailure=${ownerFailure};window.dispatchEvent(new Event('campus:mail-updated'))`);
    await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
    await evaluate("mailFixture.intelligenceFailure=0;mailFixture.ownerFailure=false;window.dispatchEvent(new Event('campus:mail-updated'))");
    await wait("document.querySelector('[data-messages]')?.textContent.includes('account-c notice')");
  }
  for(const field of ['snapshotOwnerOverride','snapshotSessionOverride']){
    await evaluate(`document.querySelector('[data-preferences]').click();mailFixture.${field}='superseded-generation';window.dispatchEvent(new Event('campus:mail-updated'))`);
    await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
    await evaluate(`mailFixture.${field}=null;window.dispatchEvent(new Event('campus:mail-updated'))`);
    await wait("document.querySelector('[data-messages]')?.textContent.includes('account-c notice')");
  }
  await evaluate("document.querySelector('[data-message]').click()");
  await wait("document.querySelector('[data-reader]').textContent.includes('account-c reader body')");
  await evaluate("document.querySelector('[data-preferences]').click();window.oldSessionForm=document.querySelector('dialog[open] form');oldSessionForm.elements.requirements.value='Old credential draft';mailFixture.session='session-2';window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-reader]').textContent.includes('reader body')");
  await evaluate('oldSessionForm.requestSubmit()');
  assert.equal(await evaluate('mailFixture.writes.length'),0,'Coherent new credentials must revoke the previous credential-bound form');
  await evaluate("document.querySelector('[data-message]').click()");
  await wait("document.querySelector('[data-reader]').textContent.includes('account-c reader body')");
  await evaluate("document.querySelector('[data-preferences]').click();mailFixture.epoch='2';mailFixture.intelligenceFailure=503;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("!document.querySelector('dialog[open]') && !document.querySelector('[data-content]').childElementCount");
  await evaluate("mailFixture.intelligenceFailure=0;window.dispatchEvent(new Event('campus:mail-updated'))");
  await wait("document.querySelector('[data-messages]')?.textContent.includes('account-c notice')");
  await evaluate('mailFixture.abort();mailFixture.dispose?.()');
  await command('Page.navigate',{url:base+'?initial-owner-race=1'});
  await wait('window.mailFixture?.ready || window.mailFixture?.error');
  assert.equal(await evaluate('Boolean(mailFixture.ready)'),false,'Initial intelligence A must not publish after status confirms owner B');
  assert.equal(await evaluate("Boolean(document.querySelector('.mail-columns'))"),false);
  console.log('PASS: snapshot/intelligence outages preserve verified same-owner reading and drafts; owner/session/epoch boundaries reject stale publication and clear old dialogs/data');
  }
}finally{socket?.close();try{browser('close');}finally{await new Promise(resolve=>server.close(resolve));}}
