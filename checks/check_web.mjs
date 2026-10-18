// Run against a local demo; API requests in the test window use synthetic data.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap = await (await fetch(base + '/api/v1/bootstrap')).json();
const themeCatalog=await(await fetch(base+'/api/v1/themes')).json();
const modules = bootstrap.modules.filter(item => ['timetable','assignments','blackboard','gradescope','assistant','deadlines'].includes(item.id));
assert(modules.find(item => item.id === 'timetable')?.frontend_url, 'Enable the timetable module before checking its UI');
const profile = resolve('.codex/tmp/web-check-' + process.pid);
await mkdir(profile,{recursive:true});
function browser(action) {
  const result = spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stderr);
}

function fixture(initial, categories, themeCatalog) {
  const savedFetch = window.fetch.bind(window);
  const providers = ['gradescope','piazza','ids','coremail'].map(id => ({id,name:id,username:'',has_password:false,has_session:false,status:'not_connected',identity_verified:false,automatic_recovery:false,...(id === 'ids' ? {targets:['blackboard','elrc','timetable'],target:'blackboard',device:{configured:false,pending:false,enabled:true,setup:{status:'idle'}}} : {}),...(id === 'coremail' ? {imap:{configured:false,host:'imap.shanghaitech.edu.cn',port:993,ssl:true,username:'',password_saved:false,verified_at:null}} : {})}));
  const ai = {provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',custom:false,enabled:false,key_saved:false,providers:[{provider:'deepseek',display_name:'DeepSeek',model:'deepseek-flash',base_url:'https://api.deepseek.com',custom:false,key_saved:false}]};
  ai.providers.push({provider:'openai',display_name:'OpenAI',model:'gpt-4',custom:false,key_saved:false});
  const state = window.webCheck = {modules:initial.map(item => ({...item,enabled:true,status:'ready'})),providers,ai,calls:[],unexpected:[],failLogin:true,localEvents:[],assignmentOrder:{},assignmentDue:{}};
  const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
  window.fetch = async (url,options={}) => {
    const path = new URL(url,location.origin).pathname.replace('/api/v1','');
    if (!new URL(url,location.origin).pathname.startsWith('/api/v1/')) return savedFetch(url,options);
    const method = options.method || 'GET', body = options.body ? JSON.parse(options.body) : {};
    state.calls.push({path,method,target:body.target,body});
    if (path === '/bootstrap') return json({version:'synthetic',csrf_token:'synthetic',modules:state.modules,categories});
    if (path === '/themes') return json(themeCatalog);
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
      if (auth[1] === 'coremail' && auth[2] === 'imap' && method === 'PUT') {
        Object.assign(provider,{status:'ready',identity_verified:true,automatic_recovery:true,imap:{configured:true,host:'imap.shanghaitech.edu.cn',port:body.port,ssl:body.ssl,username:body.username,password_saved:true,verified_at:new Date().toISOString()}});
      }
      if (auth[1] === 'coremail' && auth[2] === 'imap' && method === 'DELETE') {
        Object.assign(provider,{status:'not_connected',identity_verified:false,automatic_recovery:false,imap:{configured:false,host:'imap.shanghaitech.edu.cn',port:993,ssl:true,username:'',password_saved:false,verified_at:null}});
      }
      if (auth[1] === 'coremail' && auth[2] === 'imap/check') Object.assign(provider,{status:'ready'});
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
      if (auth[2] === 'browser') {
        Object.assign(provider,{status:'verification_required',message:'请在官方窗口完成登录后连接。'});
        if (provider.id === 'ids') Object.assign(provider,{browser_target:body.target || 'blackboard',connection:{status:'waiting_for_login'}});
      }
      if (auth[2] === 'import-session') {
        Object.assign(provider,{status:'ready',has_session:true,message:''});
        if (provider.id === 'ids') Object.assign(provider,{connection:{status:'complete'},services:['blackboard','elrc','ecourse','timetable'].map(id=>({id,status:id==='ecourse'&&body.target!=='ecourse'?'verification_required':'ready'}))});
      }
      if (auth[2] === 'device/start') provider.device.setup = {status:'waiting',message:'正在等待合成复核。'};
      if (auth[2] === 'status' && provider.device?.setup.status === 'waiting') provider.device = {configured:true,pending:false,enabled:true,setup:{status:'ready',message:'合成设备已绑定。'}};
      return json(provider);
    }
    if (path === '/modules/timetable/schedule') {
      const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      const monday = value => {
        const date = new Date(value + 'T12:00:00+08:00');
        date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
        return date.toISOString().slice(0,10);
      };
      const currentWeek = monday(today);
      const start = new Date(monday(new URL(url,location.origin).searchParams.get('week_start') || today) + 'T12:00:00+08:00');
      const days = Array.from({length:7},(_,i) => ({date:new Date(start.valueOf() + i*86400000).toISOString().slice(0,10),events:[]}));
      const at = today + 'T09:00:00+08:00';
      const events = [{id:'quiz',title:'Quiz 1',event_type:'deadline',at,source:'blackboard',submitted:false},{id:'exam',title:'合成期末考试',event_type:'exam',at,source:'eams',start_time:'09:00',location:'考试教室'},{id:'untimed-exam',title:'今日考试',event_type:'exam',at:today+'T00:00:00+08:00',date:today,source:'eams',start_time:''},...state.localEvents];
      const course = {id:'class',title:'合成课程',source:'timetable',event_type:'class',at:days[1].date+'T08:15:00+08:00',ends_at:days[1].date+'T09:55:00+08:00',period_start:1,period_end:2,teacher:'合成教师',location:'测试教室'};
      for (const day of days) day.events = events.filter(item=>item.at.slice(0,10)===day.date);
      days[1].events.push(course,{...course,id:'one-period',title:'合成课程：面向信息科学的概率论与数理统计及课堂讨论',period_start:12,period_end:12,at:days[1].date+'T19:50:00+08:00',ends_at:days[1].date+'T20:35:00+08:00'});
      const homeworkEnd = new Date(new Date(currentWeek + 'T12:00:00+08:00').valueOf() + 6*86400000).toISOString().slice(0,10);
      const homework = {week_start:currentWeek,start:currentWeek,end:homeworkEnd,pending:1,late:1,items:[
        {id:'homework-pending',title:'合成待交作业',course_title:'合成课程',due_at:today+'T20:00:00+08:00',offset:0,late:false},
        {id:'homework-late',title:'合成迟交作业',course_title:'合成课程',due_at:today+'T18:00:00+08:00',offset:0,late:true}]};
      const overviewWeeks = Array.from({length:4},(_,index) => {
        const offset = index - 1, first = new Date(new Date(currentWeek + 'T12:00:00+08:00').valueOf() + offset * 7 * 86400000);
        const weekDays = Array.from({length:7},(_,i) => ({date:new Date(first.valueOf() + i * 86400000).toISOString().slice(0,10),events:[]}));
        const reminders = homework.items.filter(item => item.offset === offset).map(item => ({...item,event_type:'deadline',at:item.due_at,homework:true,platform:'Blackboard',category:item.late ? 'late' : 'pending'}));
        for (const day of weekDays) {
          day.events = events.filter(item => item.at.slice(0,10) === day.date);
          day.events.push(...reminders.filter(item => item.at.slice(0,10) === day.date));
          if (offset === 0 && day.date === days[1].date) day.events.push(course);
        }
        return {offset,week_start:weekDays[0].date,week_end:weekDays[6].date,week_one:currentWeek,teaching_week:5 + offset,periods:[],days:weekDays,conflicts:{items:[],complete:true,message:''}};
      });
      const overview = {week_start:homework.week_start,start:homework.start,end:homework.end,weeks:overviewWeeks,pending:homework.pending,late:homework.late};
      return json({status:'ready',updated_at:at,sources:{},data:{metadata:{week_count:18,semester:'合成学期'},issues:[],timetable:[course],events},calendar:{week_start:days[0].date,week_end:days[6].date,week_one:days[0].date,teaching_week:1,days},homework,overview,school_calendar:{available:true,pages:1,url:'https://www.shanghaitech.edu.cn/1024/list.htm',pdf_url:null,checked_at:at,error:null,due:false,version:'synthetic'}});
    }
    if (path === '/modules/timetable/calendar/refresh' && method === 'POST') return json({week_one:'2026-09-14',source:'school'});
    if (path === '/modules/assignments/snapshot') {
      const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      const monday = new Date(today+'T12:00:00+08:00');
      monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
      const week18 = new Date(monday.valueOf() + (17 * 7 + 6) * 86400000).toISOString().slice(0,10);
      const savedDue = state.assignmentDue['assignment-a'];
      const values = [
        {id:'assignment-a',title:'合成作业 A',course_title:'合成课程',source:'blackboard',availability:'open',submitted:false,due_at:savedDue || week18+'T23:59:00+08:00',due_default:!savedDue,due_source:savedDue ? 'manual' : 'default',category:'pending',current:true,url:'https://example.test/a',overdue:false,score:null,max_score:null},
        {id:'assignment-b',title:'合成作业 B',course_title:'合成课程',source:'gradescope',availability:'open',submitted:false,due_at:today+'T21:00:00+08:00',due_default:false,due_source:'source',category:'pending',current:true,url:'https://example.test/b',overdue:false,score:null,max_score:null},
      ];
      const order = state.assignmentOrder.pending;
      if (order) values.sort((left,right) => order.indexOf(left.id) - order.indexOf(right.id));
      return json({status:'ready',updated_at:today+'T09:00:00+08:00',data:{assignments:values,issues:[]},account_revision:'synthetic-revision',order:state.assignmentOrder,due_overrides:state.assignmentDue});
    }
    if (path === '/modules/assignments/order' && method === 'PUT') {
      if (body.account_revision !== 'synthetic-revision') return json({detail:'账号已切换，请重新读取作业后再排序。'},409);
      state.assignmentOrder = {...state.assignmentOrder,[body.section]:body.ids};
      return json({order:state.assignmentOrder,account_revision:'synthetic-revision'});
    }
    if (path === '/modules/assignments/deadline' && method === 'PUT') {
      if (body.account_revision !== 'synthetic-revision') return json({detail:'账号已切换，请重新读取作业后再设置截止时间。'},409);
      if (body.due_at) state.assignmentDue = {...state.assignmentDue,[body.assignment_id]:body.due_at};
      else { delete state.assignmentDue[body.assignment_id]; }
      return json({assignment_id:body.assignment_id,due_at:body.due_at || null,due_overrides:state.assignmentDue,account_revision:'synthetic-revision'});
    }
    if (path === '/modules/timetable/calendar-settings') return json({week_one:'2026-09-14',source:'school'});
    if (path === '/modules/timetable/commands' && method === 'POST') {
      const item = {...body.event,id:'local:test',source:'local',at:body.event.starts_at};state.localEvents.push(item);return json({applied:true,event:item});
    }
    if (path === '/modules/timetable/events' && method === 'POST') {
      const item = {...body,id:'local:test',source:'local',at:body.starts_at};state.localEvents.push(item);return json(item,201);
    }
    if (path === '/modules/timetable/commands' && method === 'POST') {
      if (body.action === 'create') {
        const item = {...body.event,id:'local:test',source:'local',at:body.event.starts_at};state.localEvents.push(item);
        return json({applied:true,after:item});
      }
      if (body.action === 'delete') state.localEvents = [];
      return json({applied:true});
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
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)},${JSON.stringify(themeCatalog)})`});
  await command('Page.navigate',{url:base + '/#settings'});
  await evaluate(`window.waitFor = async condition => {for(let n=0;n<100;n++){if(condition())return;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error('UI condition timed out');}; waitFor(()=>window.webCheck && document.querySelector('[data-credentials=gradescope]'))`);
  const login = await evaluate(`(async()=>{
    const form=document.querySelector('[data-credentials=gradescope]'), card=form.closest('article');
    card.querySelector('.provider-connection').open=true;form.closest('details').open=true;
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
  const imap = await evaluate(`(async()=>{
    const card=document.querySelector('[data-provider=coremail]');card.querySelector('.provider-connection').open=true;
    const form=card.querySelector('[data-imap-form]'),host=form.querySelector('#imap-host');
    const initial={host:host.value,port:form.elements.port.value,ssl:form.elements.ssl.checked,readonly:host.readOnly};
    card.querySelector('[data-imap-guide]').click();
    await waitFor(()=>document.querySelector('#dialog').open);
    const page1=!document.querySelector('[data-guide-page="1"]').hidden;
    const image1=document.querySelector('[data-guide-page="1"] img');
    await image1.decode().catch(()=>{});
    const loaded1=image1.complete&&image1.naturalWidth>0;
    document.querySelector('[data-guide-next]').click();
    await waitFor(()=>!document.querySelector('[data-guide-page="2"]').hidden);
    const page2=!document.querySelector('[data-guide-page="2"]').hidden;
    const count=document.querySelector('[data-guide-count]').textContent;
    const image2=document.querySelector('[data-guide-page="2"] img');
    await image2.decode().catch(()=>{});
    const loaded2=image2.complete&&image2.naturalWidth>0;
    document.querySelector('[data-guide-done]').click();
    await waitFor(()=>!document.querySelector('#dialog').open);
    form.elements.username.value='synthetic-mail@example.edu';form.elements.password.value='synthetic-app-password';
    form.elements.port.value='143';form.elements.ssl.checked=false;
    form.dispatchEvent(new Event('input',{bubbles:true}));
    form.requestSubmit();
    await waitFor(()=>!card.querySelector('fieldset').disabled&&card.querySelector('.status-badge').textContent==='已连接');
    const saved={configured:card.querySelector('[data-imap-state]').textContent.includes('IMAP 已配置'),officialHidden:card.querySelector('[data-browser-options]').hidden,passwordCleared:form.elements.password.value==='',state:card.querySelector('[data-imap-state]').textContent};
    const call=webCheck.calls.find(item=>item.path==='/auth/coremail/imap'&&item.method==='PUT');
    card.querySelector('[data-imap-check]').click();
    await waitFor(()=>!card.querySelector('fieldset').disabled);
    card.querySelector('[data-imap-forget]').click();
    await waitFor(()=>document.querySelector('#dialog').open);
    document.querySelector('#dialog button[value=confirm]').click();
    await waitFor(()=>!card.querySelector('fieldset').disabled&&card.querySelector('.status-badge').textContent==='待连接');
    return {initial,page1,page2,loaded1,loaded2,count,saved,body:call.body,checked:webCheck.calls.some(item=>item.path==='/auth/coremail/imap/check'),forgotten:webCheck.calls.some(item=>item.path==='/auth/coremail/imap'&&item.method==='DELETE'),cleared:form.elements.username.value===''};
  })()`);
  assert.deepEqual(imap.initial,{host:'imap.shanghaitech.edu.cn',port:'993',ssl:true,readonly:true});
  assert(imap.page1 && imap.page2 && imap.loaded1 && imap.loaded2,'Both guide pages display their screenshot');
  assert.equal(imap.count,'第 2 / 2 页');
  assert.equal(imap.body.username,'synthetic-mail@example.edu');
  assert.deepEqual({port:imap.body.port,ssl:imap.body.ssl},{port:143,ssl:false});
  assert(imap.saved.configured && imap.saved.officialHidden && imap.saved.passwordCleared,'IMAP is preferred and the official entry is dropped');
  assert.match(imap.saved.state,/imap\.shanghaitech\.edu\.cn:143 · 非 SSL/);
  assert(imap.checked && imap.forgotten && imap.cleared,'IMAP check and removal use dedicated endpoints');
  await evaluate(`(async()=>{
    const card=document.querySelector('[data-provider=ids]');card.querySelector('.provider-connection').open=true;
    card.querySelector('[data-auth-action=browser]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);
    card.querySelector('[data-auth-action=import-session]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);
    if(!card.querySelector('[data-school-services]').textContent.includes('已连接 3 / 4'))throw new Error('Partial school-service connection must stay visible');
    card.querySelector('[data-school-verify=ecourse]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);
    card.querySelector('[data-auth-action=import-session]').click();await waitFor(()=>!card.querySelector('fieldset').disabled);
    if(!card.querySelector('[data-school-services]').textContent.includes('已连接 4 / 4'))throw new Error('Per-service verification must preserve the other connections');
    card.querySelector('.auth-device').open=true;card.querySelector('[data-device-action=start]').click();await waitFor(()=>document.querySelector('#dialog').open);
    document.querySelector('#dialog button[value=confirm]').click();await waitFor(()=>card.querySelector('.auth-device>summary').textContent.includes('已绑定'));
    if(document.querySelector('#ai-form')!==originalAI)throw new Error('Device polling replaced settings');return true;
  })()`);
  assert.deepEqual(await evaluate(`webCheck.calls.filter(c=>['/auth/ids/browser','/auth/ids/import-session'].includes(c.path)).map(c=>c.target || 'default')`),['default','blackboard','ecourse','ecourse']);
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
  assert(await evaluate(`!document.querySelector('.planner-overview').open && document.querySelector('.planner-week-detail').open`),'The weekly timetable starts visible and the four-week overview expands on demand');
  assert(await evaluate(`Boolean(document.querySelector('.planner-week-detail .planner-school-calendar'))`),'The school calendar panel is nested under the weekly details');
  const calendarRefreshes = await evaluate(`webCheck.calls.filter(c=>c.path==='/modules/timetable/calendar/refresh').length`);
  const calendarSchedules = await evaluate(`webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length`);
  await evaluate(`document.querySelector('[data-calendar-refresh]').click();waitFor(()=>webCheck.calls.filter(c=>c.path==='/modules/timetable/calendar/refresh').length>${calendarRefreshes}&&webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length>${calendarSchedules})`);
  assert(await evaluate(`webCheck.calls.some(c=>c.path==='/modules/timetable/calendar/refresh'&&c.method==='POST')`),'The school calendar can be refreshed manually');
  assert(await evaluate(`Boolean(document.querySelector('[data-calendar-image="1"] img'))`),'Cached calendar pages render as clickable images');
  await evaluate(`document.querySelector('[data-calendar-image="1"]').click();waitFor(()=>document.querySelector('#dialog').open)`);
  assert.equal(await evaluate(`document.querySelector('#dialog-title').textContent`),'校历 · 第 1 页');
  await evaluate(`document.querySelector('#dialog').click()`);
  await evaluate(`waitFor(()=>!document.querySelector('#dialog').open)`);
  assert(await evaluate(`!document.querySelector('#dialog').open`),'Clicking the calendar dialog backdrop closes the zoom view');
  await evaluate(`document.querySelector('.planner-overview').open=true`);
  const timetable = await evaluate(`(()=>{const body=document.querySelector('[data-module-id=timetable]'),overview=body.querySelector('[data-overview]');return {content:body.innerText,days:body.querySelectorAll('[data-calendar] thead th').length,today:body.querySelector('th.is-today')?.textContent,overviewCols:overview.querySelectorAll('thead th').length,overviewRows:overview.querySelectorAll('tr').length,overviewWeeks:overview.querySelectorAll('tbody tr').length,todayBeijing:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date()),overviewToday:overview.querySelector('.overview-day.is-today')?.dataset.overviewDate,overviewPinned:Boolean(overview.compareDocumentPosition(body.querySelector('.planner-toolbar'))&Node.DOCUMENT_POSITION_FOLLOWING),homeworkItems:overview.querySelectorAll('.overview-item.is-late').length,platforms:[...overview.querySelectorAll('.overview-platform')].map(item=>item.textContent)};})()`);
  assert.match(timetable.content,/合成课程/);assert.equal(timetable.days,8);assert.match(timetable.today,/今天/);
  assert.match(timetable.content,/近四周作业日程/);assert.match(timetable.content,/不随上方周切换按钮变化/);assert.match(timetable.content,/待完成 1 · 迟交 1/);assert.match(timetable.content,/合成迟交作业/);assert.match(timetable.content,/第 5 周/);assert.equal(timetable.overviewCols,8);assert.equal(timetable.overviewRows,5);assert.equal(timetable.overviewWeeks,4);assert.equal(timetable.overviewToday,timetable.todayBeijing);assert(timetable.overviewPinned,'Assignment schedule stays pinned above the week buttons');assert.equal(timetable.homeworkItems,1);assert.deepEqual(timetable.platforms,['Blackboard','Blackboard']);
  const overviewBefore = await evaluate(`document.querySelector('[data-overview]').innerText`);
  const scheduleCalls = await evaluate(`webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length`);
  await evaluate(`document.querySelector('[data-shift="7"]').click(); waitFor(()=>webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length>${scheduleCalls})`);
  assert.equal(await evaluate(`document.querySelector('[data-overview]').innerText`),overviewBefore,'Week buttons do not change the assignment schedule');
  const shiftedCalls = await evaluate(`webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length`);
  await evaluate(`document.querySelector('[data-today]').click(); waitFor(()=>webCheck.calls.filter(c=>c.path==='/modules/timetable/schedule').length>${shiftedCalls})`);
  await evaluate(`(async()=>{document.querySelector('[data-add]').click();const form=document.querySelector('.planner-event-form');form.elements.title.value='合成讲座';form.elements.starts_at.value=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date())+'T16:00';form.requestSubmit();await waitFor(()=>!document.querySelector('#dialog').open);await waitFor(()=>document.querySelector('.week-planner').innerText.includes('合成讲座'));})()`);
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  assert(await evaluate(`! [...document.querySelectorAll('.lesson-block .calendar-event')].some(card=>getComputedStyle(card).overflowY==='auto'||card.scrollHeight>card.clientHeight+1)`),'Course cards fit their grid slots without internal scrolling');
  await evaluate(`document.querySelector('.calendar-desktop [data-event=one-period]').click()`);
  assert(await evaluate(`document.querySelector('#dialog').open && document.querySelector('#dialog-title').textContent.includes('课堂讨论')`),'A truncated single-period title opens in full');
  await evaluate(`document.querySelector('#dialog').close();document.querySelector('.planner-overview [data-event=homework-late]').click()`);
  assert(await evaluate(`document.querySelector('#dialog').open && document.querySelector('#dialog-title').textContent==='合成迟交作业'`),'Timetable events retain their detail action');
  await evaluate(`document.querySelector('#dialog').close()`);
  await writeFile(resolve('.codex/tmp/timetable-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`),'Mobile planner fits the viewport');
  await writeFile(resolve('.codex/tmp/timetable-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await evaluate(`location.hash='assignments';waitFor(()=>document.querySelectorAll('[data-assignment]').length===2)`);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-assignment]')].map(item=>item.dataset.assignment)`),['assignment-a','assignment-b']);
  assert.match(await evaluate(`document.querySelector('[data-assignment="assignment-a"]').innerText`),/待完成 · 时间待定/);
  assert(await evaluate(`Boolean(document.querySelector('[data-assignment="assignment-a"] [data-due-editor]'))`),'Undated assignments expose an inline deadline editor');
  await evaluate(`document.querySelector('[data-assignment="assignment-a"] [data-due-toggle]').click()`);
  assert.equal(await evaluate(`document.querySelector('[data-assignment="assignment-a"] [data-due-editor]').hidden`),false);
  await evaluate(`(()=>{const card=document.querySelector('[data-assignment="assignment-a"]');card.querySelector('[data-due-input]').value='2027-01-20T18:00';card.querySelector('[data-due-save]').click();})()`);
  await evaluate(`waitFor(()=>webCheck.assignmentDue['assignment-a']==='2027-01-20T18:00:00+08:00')`);
  await evaluate(`waitFor(()=>document.querySelector('[data-assignment="assignment-a"]')?.innerText.includes('调整时间'))`);
  assert.equal(await evaluate(`document.querySelector('[data-assignment="assignment-a"]').innerText.includes('时间待定')`),false,'A saved deadline replaces the tentative label');

  await evaluate(`document.querySelector('[data-assignment="assignment-a"] [data-move="down"]').click();waitFor(()=>document.querySelector('[data-order-status]').textContent==='顺序已保存')`);
  assert.deepEqual(await evaluate(`webCheck.assignmentOrder.pending`),['assignment-b','assignment-a']);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-assignment]')].map(item=>item.dataset.assignment)`),['assignment-b','assignment-a']);
  await evaluate(`(()=>{const card=document.querySelector('[data-assignment="assignment-b"]');card.focus();card.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));})()`);
  await evaluate(`waitFor(()=>webCheck.assignmentOrder.pending[0]==='assignment-a')`);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-assignment]')].map(item=>item.dataset.assignment)`),['assignment-a','assignment-b']);
  await evaluate(`location.hash='settings';waitFor(()=>document.querySelector('[data-module-toggle=timetable]'))`);
  assert.equal(await evaluate(`document.querySelector('link[href*="/timetable/"]')===null`),true,'Timetable styles are removed');
  await evaluate(`window.toggleModule=async(id)=>{document.querySelector('[data-settings-tab=modules]').click();const input=document.querySelector('[data-module-toggle="'+id+'"]');input.checked=!input.checked;input.dispatchEvent(new Event('change'));await waitFor(()=>document.querySelector('[data-module-toggle="'+id+'"]')!==input);};toggleModule('timetable')`);
  assert.equal(await evaluate(`!!document.querySelector('[data-nav=timetable]')`),false);
  await evaluate(`toggleModule('blackboard')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),true);
  await evaluate(`toggleModule('gradescope')`); assert.equal(await evaluate(`!!document.querySelector('[data-nav=courses]')`),false);
  await evaluate(`toggleModule('assistant')`); await evaluate(`toggleModule('assignments')`); assert.deepEqual(await evaluate(`[...document.querySelectorAll('[data-nav]')].map(a=>a.dataset.nav)`),['settings']);
  await evaluate(`location.hash='timetable';waitFor(()=>location.hash.split('?')[0]==='#settings' && document.querySelector('[data-module-toggle=timetable]'))`);
  assert.deepEqual(await evaluate(`webCheck.unexpected`),[]);
  console.log('PASS: pinned assignment schedule, school-calendar zoom, inline default deadlines, saved drag order, module-driven navigation, password login/retry, saved-password reuse, IMAP priority and two-page guide, MFA/browser flow, device polling, preserved drafts, mobile layout and cleanup');
} finally {
  socket?.close();
  browser('close');
}
