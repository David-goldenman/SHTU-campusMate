// Theme regressions; functional UI checks remain in check_web.mjs.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base=process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap=await (await fetch(base+'/api/v1/bootstrap')).json();
const modules=bootstrap.modules.filter(item=>['dashboard','academic-assistant','assignments'].includes(item.id));
assert.equal(modules.length,3);
const profile=resolve('.codex/tmp/theme-check-'+process.pid);
await mkdir(profile,{recursive:true});
function browser(action) {
  const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stderr);
}
function fixture(modules,categories) {
  const original=window.fetch.bind(window);
  const state=window.themeCheck={modules,categories,empty:false,tabs:false,unexpected:[]};
  const due=hours=>new Date(Date.now()+hours*3600000).toISOString();
  const assignment=(id,title,hours,course)=>({id,title,course_title:course,group_id:course,source:'blackboard',category:hours<0?'late':'pending',submission_status:'not_submitted',availability:'open',actionable:true,submitted:false,current:true,due_at:hours==null?null:due(hours),url:'https://example.invalid/assignment'});
  const pending=[assignment('overdue','概率论习题 03',-27,'概率论与数理统计'),assignment('urgent','线性代数作业 04',2,'线性代数'),assignment('long','数据科学与金融科技概论：案例分析报告与课堂展示材料',20,'数据科学与金融科技概论'),assignment('later','程序设计 Project 2',96,'程序设计'),assignment('undated','实验报告：测量误差分析',null,'大学物理实验')];
  const submitted={...assignment('submitted','已提交的历史作业',-96,'线性代数'),submitted:true,category:'completed',submission_status:'submitted'};
  const response=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname.replace('/api/v1','');
    if(!new URL(url,location.origin).pathname.startsWith('/api/v1/')) return original(url,options);
    const categories=state.categories.map(item=>item.id==='dashboard'&&state.tabs?{...item,layout:'tabs'}:item);
    if(path==='/bootstrap')return response({version:'synthetic',csrf_token:'synthetic',modules:state.modules,categories});
    if(path==='/modules/reload')return response({modules:state.modules,categories});
    if(path==='/settings')return response({port:16666,active_port:16666,storage:{directory:'.codex/synthetic',encryption:'synthetic'}});
    if(path==='/data/backups')return response({backups:[]});
    if(path==='/auth/providers')return response({providers:[]});
    if(path==='/ai/settings')return response({model:'deepseek-flash',enabled:false,key_saved:false});
    if(path==='/data/backups')return response({backups:[]});
    if(path==='/auth/network'||path==='/auth/network/check')return response({checked_at:new Date().toISOString(),services:[],summary:'合成网络可达',scope:'合成网络检测',proxy_configured:false});
    if(path==='/modules/academic-assistant/chat')return response({messages:[]});
    if(path==='/modules/academic-assistant/conversations')return response({items:[],active_id:null});
    if(path==='/modules/academic-assistant/profile')return response({profile:{},academic:{}});
    if(path==='/modules/academic-assistant/presets')return response({items:[{label:'本周作业',message:'合成问题'}]});
    if(path==='/modules/dashboard/sync')return response({status:'ready'});
    if(path==='/modules/assignments/snapshot')return response({status:'ready',data:{assignments:[...pending,submitted],issues:[]},pending});
    if(path==='/modules/assignments/detail')return response({assignment:{title:'合成作业题目',body_text:'这是一份用于检查详情入口的合成题干。'},materials:[]});
    if(path==='/modules/dashboard/snapshot') {
      const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      const source_metadata=Object.fromEntries(['timetable','blackboard','gradescope','piazza','elrc','mail'].map(id=>[id,{status:state.empty?'not_connected':'ready'}]));
      return response({status:'ready',updated_at:null,message:state.empty?'应保留的独立服务提示':'',
        stats:{courses:12,pending:5,materials:27,ready_sources:6},
        data:{courses:[],metadata:{source_metadata},issues:state.empty?['piazza：未连接','blackboard: 未连接','独立模块故障必须保留']:[]},
        pending:state.empty?[]:pending,upcoming:state.empty?[]:pending.filter(item=>item.due_at),
        notifications:[],agenda:state.empty?[]:[{date:today,events:[{title:'合成课程日程',event_type:'class',at:today+'T17:00:00+08:00',location:'教学中心 201'},{title:'已取消课程不应占据今日安排',event_type:'class',status:'cancel',at:today+'T18:00:00+08:00'}]}]});
    }
    state.unexpected.push(path);return new Response(JSON.stringify({detail:'Unexpected synthetic API: '+path}),{status:400,headers:{'Content-Type':'application/json'}});
  };
}
let socket;
browser('open');
try {
  const port=(await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0];
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let serial=0;const pending=new Map();
  socket.addEventListener('message',({data})=>{const message=JSON.parse(data),task=pending.get(message.id);if(!task)return;clearTimeout(task.timer);pending.delete(message.id);message.error?task.reject(new Error(JSON.stringify(message.error))):task.resolve(message.result);});
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>{pending.delete(id);reject(new Error('Timed out: '+method));},20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result=>{assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;});
  const wait=condition=>evaluate(`(async()=>{for(let i=0;i<150;i++){if(${condition})return true;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error('UI condition timed out: '+${JSON.stringify(condition)}+' | '+JSON.stringify(window.themeCheck?.unexpected));})()`);
  const capture=async(name,width,height)=>{
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<850});
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    await wait("innerWidth>850 || document.querySelector('.sidebar').getBoundingClientRect().right<=0");
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Viewport overflow at '+width);
    await writeFile(resolve('.codex/tmp/'+name+'.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  };
  await command('Page.enable');
  await command('Page.navigate',{url:base+'/#dashboard'});
  await wait("document.querySelector('.overview-stats strong') && document.querySelector('.study-messages')");
  assert.equal(await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()"),'208px');
  for(const [name,width,height] of [['ui-overview-desktop',1440,1060],['ui-overview-tablet',768,1024],['ui-overview-mobile',375,812],['ui-overview-landscape',812,375]]) {
    await evaluate('window.scrollTo(0,0)');await capture(name,width,height);
  }
  await command('Network.enable');
  await command('Network.setBlockedURLs',{urls:[base+'/api/v1/*']});
  await command('Page.navigate',{url:'about:blank'});
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)})`});
  await command('Page.navigate',{url:base+'/#dashboard'});
  await wait("document.querySelector('.overview-stats strong')?.textContent==='12' && document.querySelector('.study-messages')");
  assert(await evaluate("document.querySelector('.overview-columns').textContent.includes('合成课程日程')"),'Upstream agenda is preserved');
  assert(await evaluate("!document.querySelector('.overview-card').closest('.module-zone').classList.contains('module-focus')"),'Homepage defaults to visible priorities');
  assert(await evaluate("!document.querySelector('.overview-task').closest('details')"),'Deadlines never start collapsed');
  assert(await evaluate("!document.querySelector('.overview-agenda').textContent.includes('已取消课程不应')"),'Inactive lessons stay out of the actionable agenda');
  await capture('ui-local-populated',1440,1060);
  assert(await evaluate("document.querySelector('.overview-task').getBoundingClientRect().bottom<innerHeight"),'First deadline is visible without scrolling on desktop');
  await capture('ui-priorities-mobile',375,812);
  assert(await evaluate("document.querySelector('.overview-task .deadline-stamp').getBoundingClientRect().bottom<innerHeight"),'First deadline remains visible on mobile');
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1060,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('.overview-attention [data-tone=urgent]').click()");
  await wait("document.querySelector('.assignment-board [data-view=urgent][aria-pressed=true]')");
  assert.equal(await evaluate("document.querySelectorAll('[data-pending] .assignment-card').length"),2,'Homepage urgency links apply the filter');
  assert(await evaluate("[...document.querySelectorAll('[data-pending] .assignment-card')].every(item=>item.dataset.priority==='urgent')"));
  assert(await evaluate("document.querySelector('[data-pending] .deadline-date') && document.querySelector('[data-pending] .deadline-relative') && document.querySelector('[data-pending] .assignment-card').getBoundingClientRect().height<120"),'Compact rows retain the date, time and remaining duration');
  await capture('ui-assignments-desktop',1440,1060);
  await capture('ui-assignments-mobile',375,812);
  assert(await evaluate("document.querySelector('[data-pending] .deadline-stamp').getBoundingClientRect().bottom<innerHeight"),'First assignment deadline is visible on mobile without scrolling');
  await evaluate("document.querySelector('.assignment-board [data-view=overdue]').click()");
  assert.equal(await evaluate("document.querySelectorAll('[data-pending] .assignment-card').length"),1);
  assert(await evaluate("!document.querySelector('[data-pending]').textContent.includes('已提交的历史作业')"),'Submitted work never becomes urgent or overdue');
  await evaluate("document.querySelector('.assignment-board [data-view=undated]').click()");
  assert(await evaluate("document.querySelector('[data-pending] time').textContent==='待定'"),'Unknown deadlines stay explicit');
  await evaluate("document.querySelector('.assignment-board [data-view=all]').click();const search=document.querySelector('[data-search]');search.value='线性代数';search.dispatchEvent(new Event('input'))");
  assert.equal(await evaluate("document.querySelectorAll('[data-pending] .assignment-card').length"),1,'Search keeps the pending scope');
  await evaluate("document.querySelector('[data-pending] [data-detail]').click()");
  await wait("document.querySelector('dialog[open]')?.textContent.includes('合成题干')");
  await evaluate("document.querySelector('dialog[open] [aria-label=关闭]').click();location.hash='dashboard'");
  await wait("document.querySelector('.overview-attention')");
  assert(await evaluate("!document.querySelector('link[href*=\"/assignments/\"]')"),'Assignment styles release on navigation');
  await capture('ui-priorities-return',1440,1060);
  assert(await evaluate("document.querySelectorAll('.overview-stats a').length===4 && !document.querySelector('.overview-sources').open"),'Secondary statistics stay available in a disclosure');
  await evaluate("document.documentElement.removeAttribute('data-ui-theme');document.documentElement.removeAttribute('data-art-theme')");
  assert.equal(await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()"),'216px','Team style is available without theme override');
  await evaluate("document.documentElement.dataset.uiTheme='nord-refined';document.documentElement.dataset.artTheme='observatory'");
  await evaluate("document.querySelector('.skip-link').click()");
  assert.equal(await evaluate("location.hash==='#dashboard' && document.activeElement===document.querySelector('main')"),true,'Skip link preserves the category route');
  assert(await evaluate("document.querySelectorAll('h1').length===1 && !document.querySelector('.module-shortcuts')"),'The page has one title and its own contextual actions');
  await evaluate("themeCheck.empty=true;document.querySelector('[data-module-id=dashboard] [data-sync]').click()");
  await wait("document.querySelector('.overview-stats strong')?.textContent==='—'");
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.overview-stats strong')].map(item=>item.textContent)"),['—','—','—','—']);
  const issues=await evaluate("document.querySelector('[data-module-id=dashboard] [data-issues]').textContent");
  assert.match(issues,/独立模块故障必须保留/);assert.match(issues,/应保留的独立服务提示/);assert(!issues.includes('piazza：未连接')&&!issues.includes('blackboard: 未连接'));
  await capture('ui-local-empty',375,812);
  assert(await evaluate("!!document.querySelector('.source-state [data-issues]') && !document.querySelector('.source-state').open"),'Source diagnostics remain available without expanding the page');
  await evaluate("location.hash='settings'");await wait("document.querySelector('[data-settings-tab=accounts]')");
  assert(await evaluate("!document.querySelector('link[href*=\"/dashboard/\"]') && !document.querySelector('link[href*=\"/academic-assistant/\"]')"),'Module style cleanup preserved');
  await evaluate("document.querySelector('[data-settings-tab=ai]').click();document.querySelector('#ai-form [name=api_key]').value='synthetic-draft';document.querySelector('[data-settings-tab=local]').click();document.querySelector('[data-settings-tab=ai]').click()");
  assert.equal(await evaluate("document.querySelector('#ai-form [name=api_key]').value"),'synthetic-draft','Settings tabs keep drafts');
  await evaluate("document.querySelector('[data-settings-tab=accounts]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))");
  assert.equal(await evaluate("document.activeElement.dataset.settingsTab"),'network');
  await command('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.sidebar')).transitionDuration"),'0s');
  await evaluate("themeCheck.tabs=true;document.querySelector('[data-settings-tab=modules]').click();document.querySelector('#settings-reload').click()");
  await wait("document.querySelector('#settings-reload') && !document.querySelector('#settings-reload').disabled");
  await evaluate("location.hash='dashboard'");await wait("document.querySelector('.module-tabs') && document.querySelector('.overview-stats')");
  assert.equal(await evaluate("document.querySelector('.module-shortcuts')===null"),true,'Tabbed categories use upstream tabs');
  await evaluate("document.querySelector('[data-view=academic-assistant]').click()");
  await wait("document.querySelector('.study-messages') && document.querySelector('[data-view=academic-assistant]').getAttribute('aria-selected')==='true'");
  assert.equal(await evaluate("document.querySelector('link[href*=\"/dashboard/\"]')===null"),true);
  await evaluate("document.querySelector('[data-view=academic-assistant]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))");
  await wait("document.querySelector('.overview-stats')");
  assert.deepEqual(await evaluate('themeCheck.unexpected'),[]);
  console.log('PASS: real and synthetic dashboards, agenda, empty/error feedback, 4 viewports, theme isolation, skip link and contextual actions, settings drafts/tabs, generic module tabs and style cleanup');
} finally {socket?.close();browser('close');}
