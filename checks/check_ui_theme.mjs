// Theme regressions; functional UI checks remain in check_web.mjs.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const base=process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap=await (await fetch(base+'/api/v1/bootstrap')).json();
const themeCatalog=await(await fetch(base+'/api/v1/themes')).json();
const modules=bootstrap.modules.filter(item=>['dashboard','academic-assistant','assignments'].includes(item.id));
assert.equal(modules.length,3);
const profile=resolve('.codex/tmp/theme-check-'+process.pid);
await mkdir(profile,{recursive:true});
function browser(action) {
  const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});
  assert.equal(result.status,0,result.stderr);
}
function fixture(modules,categories, themeCatalog) {
  const original=window.fetch.bind(window);
  const state=window.themeCheck={modules,categories,empty:false,tabs:false,unexpected:[],coverage:'ready',dues:{},deadlineWrites:[],handling:{},handlingWrites:[]};
  const due=hours=>new Date(Date.now()+hours*3600000).toISOString();
  const assignment=(id,title,hours,course)=>({id,title,course_title:course,group_id:course,source:'blackboard',category:hours<0?'late':'pending',submission_status:'not_submitted',availability:'open',actionable:true,submitted:false,current:true,due_at:hours==null?null:due(hours),url:'https://example.invalid/assignment'});
  const pending=[assignment('overdue','概率论习题 03',-27,'概率论与数理统计'),assignment('urgent','线性代数作业 04',2,'线性代数'),assignment('long','数据科学与金融科技概论：案例分析报告与课堂展示材料',20,'数据科学与金融科技概论'),assignment('later','程序设计 Project 2',96,'程序设计'),assignment('undated','实验报告：测量误差分析',null,'大学物理实验')];
  pending.push(...[2,-2].map((hours,index)=>({...assignment('estimate-'+index,'只有估计时间的作业 '+index,hours,'合成课程'),category:'pending',due_default:true,due_source:'default'})));
  const items=()=>pending.map(item=>state.dues[item.id] ? {...item,due_at:state.dues[item.id],due_source:'manual',due_default:false} : {...item,needs_review:state.coverage==='partial'}).map(item=>({...item,handling:state.handling[item.id]||{},reminder_suppressed:state.handling[item.id]?.status==='waived',category:state.handling[item.id]?.status==='waived'?'waived':item.category}));
  const coverage=()=>({status:state.coverage,sources:[{id:'blackboard',status:state.coverage==='partial'?'cached':'ready',updated_at:'2026-10-20T00:00:00Z'},{id:'gradescope',status:'not_connected',updated_at:null},{id:'ecourse',status:'disabled',updated_at:null}]});
  const submitted={...assignment('submitted','已提交的历史作业',-96,'线性代数'),submitted:true,category:'completed',submission_status:'submitted'};
  const response=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname.replace('/api/v1','');
    if(!new URL(url,location.origin).pathname.startsWith('/api/v1/')) return original(url,options);
    if(path==='/themes')return response(themeCatalog);
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
    if(path==='/modules/assignments/sync')return response({status:'ready'});
    if(path==='/modules/assignments/deadline') {
      const body=JSON.parse(options.body);state.deadlineWrites.push(body);
      if(body.due_at===null)delete state.dues[body.assignment_id];else state.dues[body.assignment_id]=body.due_at;
      return response({account_revision:'synthetic-account',due_overrides:state.dues});
    }
    if(path==='/modules/assignments/handling') {
      const body=JSON.parse(options.body);state.handlingWrites.push(body);
      state.handling[body.assignment_id]={status:body.status,reason:body.reason,note:body.note,revision:String(state.handlingWrites.length)};
      return response({handling:state.handling[body.assignment_id],account_revision:'synthetic-account'});
    }
    if(path==='/modules/assignments/snapshot')return response({status:'ready',data:{assignments:[...items(),submitted],issues:[]},pending:items().filter(item=>!item.reminder_suppressed),account_revision:'synthetic-account',coverage:coverage()});
    if(path==='/modules/assignments/detail')return response({assignment:{title:'合成作业题目',body_text:'这是一份用于检查详情入口的合成题干。'},materials:[]});
    if(path==='/modules/dashboard/snapshot'||path==='/modules/dashboard/summary') {
      const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      const source_metadata=Object.fromEntries(['timetable','blackboard','gradescope','piazza','elrc','mail'].map(id=>[id,{status:state.empty?'not_connected':'ready'}]));
      return response({status:'ready',updated_at:null,message:state.empty?'应保留的独立服务提示':'',
        stats:{courses:12,pending:state.coverage==='unavailable'?null:pending.length,materials:27,ready_sources:6},assignment_coverage:coverage(),
        data:{courses:[],metadata:{source_metadata},issues:state.empty?['piazza：未连接','blackboard: 未连接','独立模块故障必须保留']:[]},
        pending:state.empty||state.coverage==='unavailable'?[]:items(),upcoming:state.empty?[]:items().filter(item=>item.due_at&&!item.due_default),
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
  socket.addEventListener('message',({data})=>{
    const message=JSON.parse(data);
    if(message.method==='Fetch.requestPaused') {
      const source=`export async function mount(container,context){
        const id=context.module?.id||'settings';
        context.signal.addEventListener('abort',()=>{(window.themeContractUnmounts||=[]).push(id);},{once:true});
        const cleanup=await context.defaultView(container);
        const marker=document.createElement('p');marker.dataset.themeView=id;marker.textContent=context.theme.id;container.prepend(marker);
        return cleanup;
      }`;
      void command('Fetch.fulfillRequest',{requestId:message.params.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/javascript'}],body:Buffer.from(source).toString('base64')});return;
    }
    const task=pending.get(message.id);if(!task)return;clearTimeout(task.timer);pending.delete(message.id);message.error?task.reject(new Error(JSON.stringify(message.error))):task.resolve(message.result);
  });
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
  const fixtureScript=await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)},${JSON.stringify(themeCatalog)})`});
  await command('Page.navigate',{url:base+'/#dashboard'});
  await wait("document.querySelector('.overview-stats strong')?.textContent==='12' && document.querySelector('.study-messages')");
  assert(await evaluate("document.querySelector('.overview-columns').textContent.includes('合成课程日程')"),'Upstream agenda is preserved');
  assert(await evaluate("!document.querySelector('.overview-card').closest('.module-zone').classList.contains('module-focus')"),'Homepage defaults to visible priorities');
  assert(await evaluate("!document.querySelector('.overview-task').closest('details')"),'Deadlines never start collapsed');
  assert(await evaluate("!document.querySelector('.overview-agenda').textContent.includes('已取消课程不应')"),'Inactive lessons stay out of the actionable agenda');
  assert(await evaluate("document.querySelector('.overview-undated').textContent.includes('3 项') && !document.querySelector('.overview-task-list').textContent.includes('只有估计时间')"),'Estimated dates remain undated on the homepage');
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
  assert.equal(await evaluate("document.querySelectorAll('[data-pending] .assignment-card').length"),3,'Unknown and estimated deadlines share the undated filter');
  assert(await evaluate("document.querySelector('[data-assignment=undated] time').textContent==='待定'"),'Unknown deadlines stay explicit');
  await evaluate("document.querySelector('[data-assignment=undated] [data-due-toggle]').click();document.querySelector('[data-assignment=undated] [data-due-input]').value='2030-10-21T20:15';document.querySelector('[data-assignment=undated] [data-due-save]').click()");
  await wait("themeCheck.deadlineWrites.length===1 && !document.querySelector('[data-assignment=undated]')");
  assert.deepEqual(await evaluate("themeCheck.deadlineWrites[0]"),{assignment_id:'undated',due_at:'2030-10-21T20:15:00+08:00',account_revision:'synthetic-account'});
  await evaluate("document.querySelector('.assignment-board [data-view=all]').click();document.querySelector('[data-assignment=undated] [data-due-toggle]').click();document.querySelector('[data-assignment=undated] [data-due-reset]').click()");
  await wait("themeCheck.deadlineWrites.length===2 && document.querySelector('[data-assignment=undated] time')?.textContent==='待定'");
  await evaluate("document.querySelector('[data-assignment=urgent] [data-handling-open]').click()");
  await wait("document.querySelector('.assignment-handling-form')");
  await evaluate("document.querySelector('[data-handling-cancel]').click()");
  assert.equal(await evaluate('themeCheck.handlingWrites.length'),0,'Cancelling makes no change');
  await evaluate("document.querySelector('[data-assignment=urgent] [data-handling-open]').click();document.querySelector('.assignment-handling-form [name=note]').value='<script>合成队友已交</script>'");
  await capture('ui-handling-dialog-mobile',375,812);
  await evaluate("document.querySelector('[data-handling-save]').click()");
  await wait("themeCheck.handlingWrites.length===1 && document.querySelector('[data-section=waived] [data-handling-restore]')");
  assert.deepEqual(await evaluate('themeCheck.handlingWrites[0]'),{assignment_id:'urgent',status:'waived',reason:'team_submitted',note:'<script>合成队友已交</script>',expected_revision:'',account_revision:'synthetic-account'});
  assert(await evaluate("document.querySelector('[data-section=waived]').textContent.includes('原站：未提交') && document.querySelector('.assignment-handling-note').textContent.includes('<script>') && !document.querySelector('.assignment-handling-note script')"),'Local reasons are escaped and never change source submission status');
  await capture('ui-handling-saved-mobile',375,812);
  await evaluate("document.querySelector('[data-section-filter=pending]').click()");
  assert(await evaluate("!document.querySelector('[data-assignment=urgent]')"),'Waived work leaves the pending view');
  await evaluate("location.hash='dashboard'");await wait("document.querySelector('.overview-stats')");
  await evaluate("location.hash='assignments'");await wait("document.querySelector('[data-section-filter=waived]')");
  await evaluate("document.querySelector('[data-section-filter=waived]').click();document.querySelector('[data-handling-restore]').click()");
  await wait("themeCheck.handlingWrites.length===2 && !document.querySelector('[data-section=waived] [data-assignment]')");
  assert.equal(await evaluate('themeCheck.handlingWrites[1].expected_revision'),'1');
  await evaluate("document.querySelector('[data-section-filter=pending]').click()");
  assert(await evaluate("document.querySelector('[data-assignment=urgent] [data-handling-open]')"),'Restoration returns the original pending card');
  await evaluate("document.querySelector('.assignment-board [data-view=all]').click();const search=document.querySelector('[data-search]');search.value='线性代数';search.dispatchEvent(new Event('input'))");
  assert.equal(await evaluate("document.querySelectorAll('[data-pending] .assignment-card').length"),1,'Search keeps the pending scope');
  await evaluate("document.querySelector('[data-pending] [data-detail]').click()");
  await wait("document.querySelector('dialog[open]')?.textContent.includes('合成题干')");
  await evaluate("document.querySelector('dialog[open] [aria-label=关闭]').click();location.hash='dashboard'");
  await wait("document.querySelector('.overview-attention')");
  assert(await evaluate("!document.querySelector('link[href*=\"/assignments/\"]')"),'Assignment styles release on navigation');
  await capture('ui-priorities-return',1440,1060);
  assert(await evaluate("document.querySelectorAll('.overview-stats a').length===4 && !document.querySelector('.overview-sources').open"),'Secondary statistics stay available in a disclosure');
  await evaluate("themeCheck.coverage='unavailable';document.querySelector('[data-module-id=dashboard] [data-sync]').click()");
  await wait("document.querySelector('.overview-data-note')?.textContent.includes('暂不可用')");
  assert.deepEqual(await evaluate("[...document.querySelectorAll('.overview-attention strong')].map(item=>item.firstChild.textContent)"),['—','—','—'],'Unavailable assignments never look like zero work');
  await capture('ui-assignments-unavailable',375,812);
  await evaluate("themeCheck.coverage='partial';document.querySelector('[data-module-id=dashboard] [data-sync]').click()");
  await wait("document.querySelector('.overview-data-note')?.textContent.includes('已知待办')");
  assert(await evaluate("document.querySelector('.overview-task').textContent.includes('状态待核实')"),'Cached work remains visible with its uncertainty');
  await capture('ui-assignments-cached',1440,1060);
  await evaluate("themeCheck.coverage='ready';document.querySelector('[data-module-id=dashboard] [data-sync]').click()");
  await wait("!document.querySelector('.overview-data-note')");
  await evaluate("document.documentElement.removeAttribute('data-ui-theme');document.documentElement.removeAttribute('data-art-theme')");
  assert.equal(await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()"),'216px','Team style is available without theme override');
  await evaluate("document.documentElement.dataset.uiTheme='nord-refined'");
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
  await evaluate("location.hash='settings?tab=appearance'");
  await wait("document.querySelectorAll('[name=art-theme]').length>=3");
  for(const id of ['observatory','star-notes','arknights','default']) {
    await evaluate(`document.querySelector('[name="art-theme"][value="${id}"]').click()`);
    await wait(`document.documentElement?.dataset.theme==='${id}' && document.querySelector('[name="art-theme"][value="${id}"]')?.checked`);
    await command('Page.reload');
    await wait(`document.documentElement?.dataset.theme==='${id}' && document.querySelector('[name="art-theme"][value="${id}"]')?.checked`);
    assert(await evaluate("document.documentElement.scrollWidth<=innerWidth"),'Theme selection fits the viewport');
    await capture('ui-theme-'+id,1440,1060);
    await capture('ui-theme-'+id+'-mobile',375,812);
    await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1060,deviceScaleFactor:1,mobile:false});
    await evaluate("location.hash='dashboard'");
    await wait("document.querySelector('.study-welcome')");
    assert.equal(await evaluate("!!document.querySelector('.study-welcome-illustration')"),['observatory','star-notes'].includes(id),'Theme owns the welcome presentation');
    await evaluate("themeCheck.coverage='unavailable';document.querySelector('[data-module-id=dashboard] [data-sync]').click()");
    await wait("document.querySelector('.overview-data-note')?.textContent.includes('暂不可用')");
    assert.equal(await evaluate("document.querySelector('.overview-attention a:last-child strong').firstChild.textContent"),'—','Every theme preserves unknown counts');
    if(id==='arknights')assert.equal(await evaluate("document.querySelector('[data-ark-metric=pending]').textContent"),'—','PRTS summary preserves unknown counts');
    await capture('ui-reliability-'+id,375,812);
    await evaluate("themeCheck.coverage='partial';location.hash='assignments'");
    await wait("document.querySelector('.assignment-coverage[data-coverage=partial]')");
    assert(await evaluate("document.querySelector('[data-assignment=undated] [data-due-toggle]') && document.querySelector('[data-assignment=urgent] .assignment-review')"),'Every theme retains missing-date editing and stale status');
    await capture('ui-reliability-'+id+'-assignments',375,812);
    await evaluate("document.querySelector('[data-assignment=urgent] [data-handling-open]').click()");
    await capture('ui-handling-'+id,375,812);
    await evaluate("document.querySelector('[data-handling-save]').click()");
    await wait("document.querySelector('[data-section=waived] [data-handling-restore]')");
    assert(await evaluate("document.querySelector('.assignment-handling-note').textContent.includes('队友已提交') && document.querySelector('[data-section=waived]').textContent.includes('原站：未提交')"),'Every theme retains independent team handling and source truth');
    await capture('ui-handling-'+id+'-saved',375,812);
    await evaluate("document.querySelector('[data-handling-restore]').click()");
    await wait("!document.querySelector('[data-section=waived] [data-assignment]')");
    await evaluate("location.hash='settings?tab=appearance'");
    await wait("document.querySelector('[name=art-theme]')");
  }
  assert.equal(await evaluate("getComputedStyle(document.documentElement,'::-webkit-scrollbar').width"),'6px','Compact scrollbars are shared by themes');
  assert.equal(await evaluate("getComputedStyle(document.documentElement).scrollbarColor"),'auto','Native scrollbar color must not override the compact Edge styling');
  const view='/assets/themes/contract-check/view.js',custom={id:'contract-check',name:'Contract check',description:'Synthetic theme',styles:[],entry:null,views:{assignments:view,settings:view},backgrounds:{}};
  await command('Fetch.enable',{patterns:[{urlPattern:base+view}]});
  await command('Page.removeScriptToEvaluateOnNewDocument',{identifier:fixtureScript.identifier});
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)},${JSON.stringify({...themeCatalog,items:[...themeCatalog.items,custom]})})`});
  await evaluate("localStorage.setItem('campus.appearance.v1',JSON.stringify({...JSON.parse(localStorage.getItem('campus.appearance.v1')),theme:'contract-check'}))");
  await command('Page.navigate',{url:base+'/#assignments'});
  await wait("location.hash==='#assignments' && document.querySelector('.assignment-card')");
  await command('Page.reload');
  await wait("document.querySelector('[data-theme-view=assignments]')?.textContent==='contract-check' && document.querySelector('.assignment-card')");
  await evaluate("location.hash='settings?tab=appearance'");
  await wait("document.querySelector('[data-theme-view=settings]') && document.querySelector('[name=art-theme]')");
  assert.deepEqual(await evaluate('themeContractUnmounts'),['assignments'],'Theme wrappers release the original view on navigation');
  await evaluate("document.querySelector('[name=art-theme][value=default]').click()");
  await wait("document.documentElement?.dataset.theme==='default' && document.querySelector('[name=art-theme][value=default]')?.checked");
  console.log('PASS: local team submission handling/restoration, source truth, escaped notes, dashboards, source coverage, estimated/unknown/manual deadlines, four viewports, four remembered themes, module/settings view overrides, API reuse, cleanup, scrollbars, settings tabs and keyboard actions');
} finally {socket?.close();browser('close');}
