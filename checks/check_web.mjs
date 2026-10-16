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

function fixture(initial) {
  const savedFetch = window.fetch.bind(window);
  const providers = ['gradescope','piazza','ids','coremail'].map(id => ({id,name:id,username:'',has_password:false,has_session:false,status:'not_connected',identity_verified:false,automatic_recovery:false,...(id === 'ids' ? {targets:['blackboard','elrc','timetable'],target:'blackboard',device:{configured:false,pending:false,enabled:true,setup:{status:'idle'}}} : {})}));
  const state = window.webCheck = {modules:initial.map(item => ({...item,enabled:true,status:'ready'})),providers,calls:[],unexpected:[],failLogin:true};
  const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
  window.fetch = async (url,options={}) => {
    const path = new URL(url,location.origin).pathname.replace('/api/v1','');
    if (!new URL(url,location.origin).pathname.startsWith('/api/v1/')) return savedFetch(url,options);
    const method = options.method || 'GET', body = options.body ? JSON.parse(options.body) : {};
    state.calls.push({path,method,target:body.target});
    if (path === '/bootstrap') return json({version:'synthetic',csrf_token:'synthetic',modules:state.modules});
    if (path === '/settings') return json({port:16666,active_port:16666,storage:{directory:'.codex/synthetic',encryption:'synthetic'}});
    if (path === '/ai/settings') return json({model:'deepseek-flash',enabled:false,key_saved:false});
    if (path === '/auth/providers') return json({providers});
    if (path === '/modules' || path === '/modules/reload') return json({modules:state.modules});
    const toggle = path.match(/^\/modules\/([^/]+)$/);
    if (toggle && method === 'PUT') {
      const item = state.modules.find(item => item.id === toggle[1]);
      item.enabled = body.enabled; item.status = body.enabled ? 'ready' : 'disabled';
      return json({modules:state.modules});
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
    if (path === '/modules/dashboard/snapshot') {
      if (state.dashboardEmpty) return json({status:'partial',stats:{courses:0,pending:0,materials:0,ready_sources:0},upcoming:[],notifications:[],data:{issues:['piazza: 请先连接账号。','作业管理模块未启用或暂时不可用。'],metadata:{source_metadata:{piazza:{status:'not_connected'}}},courses:[]}});
      const due = new Date(Date.now()+86400000).toISOString();
      return json({status:'ready',updated_at:due,stats:{courses:6,pending:2,materials:12,ready_sources:1},upcoming:[{id:'test-task',title:'合成课程 · 项目报告',course_title:'界面测试课程',due_at:due,url:'https://example.invalid/task'}],notifications:[{title:'合成通知：有新附件',summary:'仅用于界面回归检查，不代表真实来源已接入。',citations:[{title:'合成附件来源',url:'https://example.invalid/post'}]}],data:{issues:[],metadata:{source_metadata:{piazza:{status:'ready',updated_at:due}}},courses:[{id:'test-course',title:'合成课程',current:true,url:'https://example.invalid/course',source:'synthetic',term:'合成学期'}]}});
    }
    if (path === '/modules/timetable/schedule') {
      const future = new Date(Date.now()+86400000).toISOString(), past = new Date(Date.now()-86400000).toISOString();
      const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      return json({status:'ready',sources:{timetable:{updated_at:future}},data:{metadata:{week_count:18,semester:'合成学期'},issues:[],undated:1,timetable:[{id:'class',title:'合成课程',weekday:1,period_start:1,period_end:2,weeks:[1,2],teacher:'合成教师',location:'测试教室'}],events:[{id:'past',title:'过去的作业',event_type:'deadline',at:past,source:'gradescope',submitted:true},{id:'quiz',title:'Quiz 1',event_type:'deadline',at:future,source:'blackboard',submitted:false},{id:'exam',title:'合成期末考试',event_type:'exam',at:future,source:'eams',start_time:'09:00',window:'09:00–11:00',location:'考试教室'},{id:'untimed-exam',title:'今日考试',event_type:'exam',at:today+'T00:00:00+08:00',date:today,source:'eams',start_time:''}]}});
    }
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
  // Read-only screenshots of the actual local empty workspace, before synthetic APIs.
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`window.waitFor = async condition => {for(let n=0;n<100;n++){if(condition())return;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error('UI preview timed out');};`});
  await command('Page.navigate',{url:base + '/#dashboard'});
  await evaluate(`waitFor(()=>document.querySelector('.dashboard-stat') && document.querySelector('link[href*="/dashboard/"]')?.sheet)`);
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  for (const [label,width,height] of [['desktop',1440,1060],['tablet',768,1024],['mobile',375,812]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<850});
    assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),label + ' dashboard fits the viewport');
    await evaluate(`window.scrollTo(0,0);true`);
    await writeFile(resolve('.codex/tmp/ui-overview-' + label + '.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  }
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  await command('Network.setBlockedURLs',{urls:[base + '/api/v1/*']});
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)})`});
  await command('Page.navigate',{url:'about:blank'});
  await command('Page.navigate',{url:base + '/#settings'});
  await evaluate(`window.waitFor = async condition => {for(let n=0;n<100;n++){if(condition())return;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error('UI condition timed out at ' + location.hash + ': ' + document.body.innerText.slice(0,1800));}; waitFor(()=>window.webCheck && document.querySelector('[data-credentials=gradescope]'))`);
  assert.equal(await evaluate(`(()=>{document.querySelector('[data-settings-jump="ai"]').click();return document.activeElement.textContent;})()`),'统一 AI 服务');
  assert.equal(await evaluate(`location.hash`),'#settings','Settings shortcuts preserve the application route');
  await evaluate(`document.querySelector('[data-settings-jump="accounts"]').click();true`);
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
  await evaluate(`location.hash='timetable'; waitFor(()=>document.querySelector('[data-events]'))`);
  const timetable = await evaluate(`(()=>{const body=document.querySelector('[data-module-id=timetable]');const future=body.querySelector('[data-events]').innerText;const range=body.querySelector('[data-range]');range.value='all';range.dispatchEvent(new Event('change'));const all=body.querySelector('[data-events]').innerText;const kind=body.querySelector('[data-kind]');kind.value='exam';kind.dispatchEvent(new Event('change'));return {future,all,exam:body.querySelector('[data-events]').innerText,classes:body.querySelector('[data-grid]').innerText,undated:body.querySelector('[data-undated]').innerText};})()`);
  assert.match(timetable.future,/Quiz 1/); assert.match(timetable.future,/合成期末考试/); assert.doesNotMatch(timetable.future,/过去的作业/);
  assert.match(timetable.future,/今日考试/); assert.match(timetable.future,/具体时间待公布/);
  assert.match(timetable.all,/过去的作业/); assert.doesNotMatch(timetable.exam,/Quiz 1/); assert.match(timetable.classes,/合成课程/); assert.match(timetable.undated,/1 条/);
  await evaluate(`location.hash='settings';waitFor(()=>document.querySelector('[data-module-toggle=timetable]'))`);
  assert.equal(await evaluate(`document.querySelector('link[href*="/timetable/"]')===null`),true,'Timetable styles are removed');
  await evaluate(`window.toggleModule=async(id)=>{const input=document.querySelector('[data-module-toggle="'+id+'"]');input.checked=!input.checked;input.dispatchEvent(new Event('change'));await waitFor(()=>document.querySelector('[data-module-toggle="'+id+'"]')!==input);};toggleModule('timetable')`);
  assert.equal(await evaluate(`!!document.querySelector('[data-nav=timetable]')`),false);
  await evaluate(`toggleModule('blackboard')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),true);
  await evaluate(`toggleModule('gradescope')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),false);
  await evaluate(`toggleModule('assistant')`); assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-nav]')].map(a=>a.dataset.nav)`),['settings']);
  await evaluate(`location.hash='timetable';waitFor(()=>location.hash==='#settings' && document.querySelector('[data-module-toggle=timetable]'))`);
  // The populated dashboard uses only the synthetic API, never user records.
  const dashboard = bootstrap.modules.find(item=>item.id==='dashboard');
  assert(dashboard?.frontend_url,'Dashboard is enabled for UI checks');
  await evaluate(`webCheck.modules = ${JSON.stringify([dashboard,...modules])};document.querySelector('#reload-modules').click();waitFor(()=>document.querySelector('[data-nav=dashboard]'))`);
  await evaluate(`location.hash='dashboard';waitFor(()=>document.querySelector('.deadline-row') && document.querySelector('link[href*="/dashboard/"]')?.sheet)`);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('.stat-value')].map(node=>node.textContent)`),['6','2','12','1']);
  assert.match(await evaluate(`document.querySelector('.dashboard-notifications').textContent`),/合成附件来源/);
  for (const width of [1440,768,375]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<850});
    assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'Populated dashboard fits at '+width);
  }
  await evaluate(`location.hash='settings';waitFor(()=>document.querySelector('[data-settings-jump]'))`);
  assert.equal(await evaluate(`document.querySelector('link[href*="/dashboard/"]')===null`),true,'Dashboard styles are removed on navigation');
  await evaluate(`webCheck.dashboardEmpty=true;location.hash='dashboard';waitFor(()=>document.querySelector('.dashboard-connect-notice'))`);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('.stat-value')].map(node=>node.textContent)`),['—','—','—','—']);
  assert.match(await evaluate(`document.querySelector('[data-issues]').textContent`),/作业管理模块未启用/,'Connection guidance preserves unrelated failures');
  assert.deepEqual(await evaluate(`webCheck.unexpected`),[]);
  console.log('PASS: desktop/tablet/mobile dashboards, source status, settings shortcuts, dashboard cleanup, combined timetable, module-driven navigation, password login/retry, saved-password reuse, MFA/browser flow, device polling, preserved drafts, mobile layout and cleanup');
} finally {
  socket?.close();
  browser('close');
}
