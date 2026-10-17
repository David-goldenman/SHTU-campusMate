// Run against a local demo; API requests in the test window use synthetic data.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap = await (await fetch(base + '/api/v1/bootstrap')).json();
const modules = bootstrap.modules.filter(item => ['timetable','blackboard','gradescope','assistant','deadlines'].includes(item.id));
assert(modules.find(item => item.id === 'timetable')?.frontend_url, 'Enable the timetable module before checking its UI');
const profile = resolve('.codex/tmp/web-check-' + process.pid);
await mkdir(profile,{recursive:true});
function browser(action) {
  const result = spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stderr);
}

function fixture(initial, categories) {
  const savedFetch = window.fetch.bind(window);
  const providers = ['gradescope','piazza','ids','coremail'].map(id => ({id,name:id,username:'',has_password:false,has_session:false,status:'not_connected',identity_verified:false,automatic_recovery:false,...(id === 'ids' ? {targets:['blackboard','elrc','timetable'],target:'blackboard',device:{configured:false,pending:false,enabled:true,setup:{status:'idle'}}} : {})}));
  const ai = {provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',custom:false,enabled:false,key_saved:false,providers:[{provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',custom:false,key_saved:false}]};
  ai.providers.push({provider:'openai',display_name:'OpenAI',model:'gpt-4',custom:false,key_saved:false});
  const state = window.webCheck = {modules:initial.map(item => ({...item,enabled:true,status:'ready'})),providers,ai,calls:[],unexpected:[],failLogin:true,localEvents:[]};
  const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
  window.fetch = async (url,options={}) => {
    const path = new URL(url,location.origin).pathname.replace('/api/v1','');
    if (!new URL(url,location.origin).pathname.startsWith('/api/v1/')) return savedFetch(url,options);
    const method = options.method || 'GET', body = options.body ? JSON.parse(options.body) : {};
    state.calls.push({path,method,target:body.target});
    if (path === '/bootstrap') return json({version:'synthetic',csrf_token:'synthetic',modules:state.modules,categories});
    if (path === '/settings') return json({port:16666,active_port:16666,storage:{directory:'.codex/synthetic',encryption:'synthetic'}});
    if (path === '/data/backups') return json({backups:[]});
    if (path === '/ai/catalog') return json({providers:[{id:'deepseek',name:'DeepSeek',models:['deepseek-flash','deepseek-v4-pro']},{id:'openai',name:'openai',models:['gpt-4']}],protocols:['openai-completions','openai-responses','anthropic-messages']});
    if (path === '/ai/settings') {
      if (method === 'PUT') {
        const {api_key,...publicBody} = body;
        const row = {...(ai.providers.find(row=>row.provider===body.provider)||{}),...publicBody,key_saved:Boolean(api_key)};
        ai.providers = [...ai.providers.filter(item=>item.provider!==row.provider),row];
        Object.assign(ai,row,{enabled:body.enabled});
      }
      return json(ai);
    }
    if (path === '/auth/providers') return json({providers});
    if (path === '/modules' || path === '/modules/reload') return json({modules:state.modules,categories});
    const toggle = path.match(/^\/modules\/([^/]+)$/);
    if (toggle && method === 'PUT') {
      const item = state.modules.find(item => item.id === toggle[1]);
      item.enabled = body.enabled; item.status = body.enabled ? 'ready' : 'disabled';
      return json({modules:state.modules,categories});
    }
    const auth = path.match(/^\/auth\/([^/]+)\/(.+)$/);
    if (auth) {
      const provider = providers.find(item => item.id === auth[1]);
      if (auth[2] === 'credentials') Object.assign(provider,{username:body.username,has_password:true,status:'login_required'});
      if (auth[2] === 'login') {
        await new Promise(resolve => setTimeout(resolve,350));
        if (state.failLogin) {
          state.failLogin = false;
          Object.assign(provider,{status:'verification_required',message:'请在官方窗口完成合成验证码。'});
          return json({detail:provider.message},409);
        }
        Object.assign(provider,{status:'ready',has_session:true,message:'',identity_verified:true});
      }
      if (auth[2] === 'browser') Object.assign(provider,{status:'verification_required',message:'请在官方窗口完成登录后连接。'});
      if (auth[2] === 'import-session') Object.assign(provider,{status:'ready',has_session:true,message:''});
      if (auth[2] === 'device/start') provider.device.setup = {status:'waiting',message:'正在等待合成复核。'};
      if (auth[2] === 'status' && provider.device?.setup.status === 'waiting') provider.device = {configured:true,pending:false,enabled:true,setup:{status:'ready',message:'合成设备已绑定。'}};
      return json(provider);
    }
    if (path === '/modules/timetable/schedule') {
      const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      const start = new Date((new URL(url,location.origin).searchParams.get('week_start') || today) + 'T12:00:00+08:00');
      start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
      const days = Array.from({length:7},(_,i) => ({date:new Date(start.valueOf() + i*86400000).toISOString().slice(0,10),events:[]}));
      const at = today + 'T09:00:00+08:00';
      const events = [{id:'quiz',title:'Quiz 1',event_type:'deadline',at,source:'blackboard',submitted:false},{id:'exam',title:'合成期末考试',event_type:'exam',at,source:'eams',start_time:'09:00',location:'考试教室'},{id:'untimed-exam',title:'今日考试',event_type:'exam',at:today+'T00:00:00+08:00',date:today,source:'eams',start_time:''},...state.localEvents];
      const course = {id:'class',title:'合成课程',source:'timetable',event_type:'class',at:days[1].date+'T08:15:00+08:00',ends_at:days[1].date+'T09:55:00+08:00',period_start:1,period_end:2,teacher:'合成教师',location:'测试教室'};
      for (const day of days) day.events = events.filter(item=>item.at.slice(0,10)===day.date);
      days[1].events.push(course);
      return json({status:'ready',updated_at:at,sources:{},data:{metadata:{week_count:18,semester:'合成学期'},issues:[],undated:1,timetable:[course],events},calendar:{week_start:days[0].date,week_end:days[6].date,week_one:days[0].date,teaching_week:1,days}});
    }
    if (path === '/modules/timetable/calendar-settings') return json({week_one:'2026-09-14',source:'school'});
    if (path === '/modules/timetable/commands' && method === 'POST') {
      const item = {...body.event,id:'local:test',source:'local',at:body.event.starts_at};state.localEvents.push(item);return json({applied:true,event:item});
    }
    if (path === '/modules/timetable/events' && method === 'POST') {
      const item = {...body,id:'local:test',source:'local',at:body.starts_at};state.localEvents.push(item);return json(item,201);
    }
    if (path === '/modules/timetable/events/local%3Atest' && method === 'DELETE') {state.localEvents=[];return json({deleted:true});}
    state.unexpected.push(path);
    return json({detail:'Unexpected synthetic API: ' + path},400);
  };
}

let socket;
browser('open');
try {
  const port = (await readFile(profile + '/DevToolsActivePort','utf8')).split(/\r?\n/)[0];
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let serial = 0;
  const pending = new Map();
  socket.addEventListener('message',({data}) => {
    const message = JSON.parse(data), task = pending.get(message.id);
    if (!task) return;
    clearTimeout(task.timer); pending.delete(message.id);
    message.error ? task.reject(new Error(JSON.stringify(message.error))) : task.resolve(message.result);
  });
  const command = (method,params={}) => new Promise((resolve,reject) => {
    const id = ++serial, timer = setTimeout(() => {pending.delete(id);reject(new Error('Timed out: ' + method));},20000);
    pending.set(id,{resolve,reject,timer}); socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate = expression => command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result => {assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;});
  await command('Page.enable');
  await command('Network.enable');
  await command('Network.setBlockedURLs',{urls:[base + '/api/v1/*']});
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)})`});
  await command('Page.navigate',{url:base + '/#settings'});
  await evaluate(`window.waitFor = async condition => {for(let n=0;n<100;n++){if(condition())return;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error('UI condition timed out');}; waitFor(()=>window.webCheck && document.querySelector('[data-credentials=gradescope]'))`);
  const login = await evaluate(`(async()=>{
    const form=document.querySelector('[data-credentials=gradescope]'), card=form.closest('article');
    form.closest('details').open=true;
    form.elements.username.value='synthetic-user';form.elements.password.value='synthetic-password';form.dispatchEvent(new Event('input',{bubbles:true}));
    const other=document.querySelector('[data-credentials=piazza]');other.elements.password.value='synthetic-draft';
    const ai=document.querySelector('#ai-form');ai.elements.api_key.value='synthetic-key-draft';window.originalAI=ai;
    card.querySelector('[data-show-password]').click();const shown=form.elements.password.type==='text';
    form.requestSubmit();const busy=card.querySelector('fieldset').disabled;
    card.querySelector('[data-auth-action=browser]').click();
    await waitFor(()=>!card.querySelector('fieldset').disabled);
    const failure=card.querySelector('[data-auth-feedback]').textContent;
    const cleared=form.elements.password.value==='' && form.elements.password.type==='password';
    form.requestSubmit();await waitFor(()=>!card.querySelector('fieldset').disabled);
    const ready=card.querySelector('.status-badge').textContent==='已连接';
    const before=webCheck.calls.length;form.elements.username.value='another-user';form.dispatchEvent(new Event('input',{bubbles:true}));
    const required=form.elements.password.required;form.requestSubmit();
    return {shown,busy,failure,cleared,ready,required,invalidBlocked:webCheck.calls.length===before,draft:other.elements.password.value,aiDraft:ai.elements.api_key.value,sameAI:ai===document.querySelector('#ai-form'),saves:webCheck.calls.filter(c=>c.path==='/auth/gradescope/credentials').length,logins:webCheck.calls.filter(c=>c.path==='/auth/gradescope/login').length,browsers:webCheck.calls.filter(c=>c.path==='/auth/gradescope/browser').length};
  })()`);
  assert.deepEqual({...login,failure:undefined},{shown:true,busy:true,failure:undefined,cleared:true,ready:true,required:true,invalidBlocked:true,draft:'synthetic-draft',aiDraft:'synthetic-key-draft',sameAI:true,saves:1,logins:2,browsers:0});
  assert.match(login.failure,/验证码/);
  await evaluate(`(async()=>{const card=document.querySelector('[data-provider=ids]');card.querySelector('[data-auth-target]').value='elrc';card.querySelector('[data-auth-action=browser]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);card.querySelector('[data-auth-action=import-session]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);card.querySelector('[data-device-action=start]').click();await waitFor(()=>document.querySelector('#dialog').open);document.querySelector('#dialog button[value=confirm]').click();await waitFor(()=>card.innerText.includes('已绑定 ·'));if(document.querySelector('#ai-form')!==originalAI)throw new Error('Device polling replaced settings');return true;})()`);
  assert.deepEqual(await evaluate(`webCheck.calls.filter(c=>['/auth/ids/browser','/auth/ids/import-session'].includes(c.path)).map(c=>c.target)`),['elrc','elrc']);
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector('[data-provider=gradescope]').scrollIntoView(); true`);
  await writeFile(resolve('.codex/tmp/web-check-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate(`new Promise(resolve=>setTimeout(resolve,300))`);
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'Mobile settings fit the viewport');
  assert(await evaluate(`document.querySelector('.sidebar').getBoundingClientRect().right<=0`),'Mobile sidebar starts closed');
  await writeFile(resolve('.codex/tmp/web-check-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector('[data-settings-tab=ai]').click();document.querySelector('[data-ai-edit=deepseek]').click();waitFor(()=>document.querySelector('[data-ai-editor]')?.open)`);
  assert(await evaluate(`document.querySelector('[data-ai-editor]').matches(':modal')`),'Provider editor traps focus in a native dialog');
  assert(await evaluate(`document.querySelector('[data-ai-edit=deepseek]').getBoundingClientRect().height<=36`),'Desktop provider actions stay compact');
  assert(await evaluate(`document.querySelector('#ai-form [type=radio]').getBoundingClientRect().width<=24`),'Provider options use compact radio controls');
  await evaluate(`document.querySelector('#ai-form').elements.api_key.value='synthetic-cancelled-key'`);
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await evaluate(`waitFor(()=>!document.querySelector('[data-ai-editor]').open && document.querySelector('#ai-form').elements.api_key.value==='')`);
  assert(await evaluate(`document.activeElement.matches('[data-ai-edit=deepseek]')`),'Closing the editor restores focus to its row');
  await evaluate(`document.querySelector('[data-ai-edit=deepseek]').click();waitFor(()=>document.querySelector('[data-ai-editor]').open)`);
  await evaluate(`document.querySelector('#ai-form').elements.api_key.value='synthetic-saved-key';document.querySelector('#ai-form').requestSubmit();waitFor(()=>webCheck.ai.enabled && document.querySelector('#ai-form')?.hidden === true)`);
  assert.equal(await evaluate(`webCheck.ai.enabled`),true,'Saving a key enables AI');
  await evaluate(`document.querySelector('[data-ai-use=openai]').click();waitFor(()=>webCheck.ai.provider==='openai')`);
  assert.equal(await evaluate(`webCheck.ai.enabled`),true,'Environment authentication providers can be selected without a saved key');
  await evaluate(`document.querySelector('[data-ai-add]').click();waitFor(()=>document.querySelector('#ai-form')?.hidden === false)`);
  await evaluate(`(()=>{const f=document.querySelector('#ai-form');f.querySelector('[name=mode][value=custom]').click();f.elements.provider_id.value='campus-gateway';f.elements.display_name.value='合成服务';f.elements.base_url.value='https://gateway.example/v1';f.elements.protocol.value='anthropic-messages';f.elements.model.value='synthetic-model';f.elements.api_key.value='synthetic-custom-key';f.requestSubmit();})()`);
  await evaluate(`waitFor(()=>webCheck.ai.provider==='campus-gateway' && document.querySelector('#ai-form')?.hidden === true)`);
  assert.equal(await evaluate(`webCheck.ai.protocol`),'anthropic-messages');
  assert.equal(await evaluate(`document.querySelector('#ai-form').elements.api_key.value`),'','Saved secret is cleared from the form');
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate(`document.querySelector('[data-ai-edit=campus-gateway]').click();waitFor(()=>document.querySelector('[data-ai-editor]').open)`);
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth && document.querySelector('[data-ai-editor]').scrollWidth<=document.querySelector('[data-ai-editor]').clientWidth`),'Mobile provider dialog fits');
  await evaluate(`location.hash='timetable'; waitFor(()=>document.querySelector('[data-calendar]'))`);
  assert.equal(await evaluate(`!!document.querySelector('[data-ai-editor][open]')`),false,'Leaving settings closes the editor');
  const timetable = await evaluate(`(()=>{const body=document.querySelector('[data-module-id=timetable]');return {content:body.innerText,days:body.querySelectorAll('[data-calendar] thead th').length,today:body.querySelector('th.is-today')?.textContent};})()`);
  assert.match(timetable.content,/Quiz 1/);assert.match(timetable.content,/合成期末考试/);assert.match(timetable.content,/合成课程/);assert.match(timetable.content,/时间待公布/);assert.equal(timetable.days,8);assert.match(timetable.today,/今天/);
  await evaluate(`(async()=>{document.querySelector('[data-add]').click();const form=document.querySelector('.planner-event-form');form.elements.title.value='合成讲座';form.elements.starts_at.value=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())+'T16:00';form.requestSubmit();await waitFor(()=>!document.querySelector('#dialog').open);await waitFor(()=>document.querySelector('.week-planner').innerText.includes('合成讲座'));})()`);
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await writeFile(resolve('.codex/tmp/timetable-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'Mobile planner fits the viewport');
  await writeFile(resolve('.codex/tmp/timetable-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await evaluate(`location.hash='settings';waitFor(()=>document.querySelector('[data-module-toggle=timetable]'))`);
  assert.equal(await evaluate(`document.querySelector('link[href*="/timetable/"]')===null`),true,'Timetable styles are removed');
  await evaluate(`window.toggleModule=async(id)=>{document.querySelector('[data-settings-tab=modules]').click();const input=document.querySelector('[data-module-toggle="'+id+'"]');input.checked=!input.checked;input.dispatchEvent(new Event('change'));await waitFor(()=>document.querySelector('[data-module-toggle="'+id+'"]')!==input);};toggleModule('timetable')`);
  assert.equal(await evaluate(`!!document.querySelector('[data-nav=timetable]')`),false);
  await evaluate(`toggleModule('blackboard')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),true);
  await evaluate(`toggleModule('gradescope')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),false);
  await evaluate(`toggleModule('assistant')`); assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-nav]')].map(a=>a.dataset.nav)`),['settings']);
  await evaluate(`location.hash='timetable';waitFor(()=>location.hash.split('?')[0]==='#settings' && document.querySelector('[data-module-toggle=timetable]'))`);
  assert.deepEqual(await evaluate(`webCheck.unexpected`),[]);
  console.log('PASS: combined timetable, module-driven navigation, password login/retry, saved-password reuse, MFA/browser flow, device polling, preserved drafts, mobile layout and cleanup');
} finally {
  socket?.close();
  browser('close');
}
