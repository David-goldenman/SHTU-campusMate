import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.argv[2]||'http://127.0.0.1:16666';
const bootstrap=await(await fetch(base+'/api/v1/bootstrap')).json();
const modules=bootstrap.modules.filter(item=>['courses','blackboard','gradescope','mail','notifications','campus-agent'].includes(item.id));
const profile=resolve('.codex/tmp/campus-workspace-'+process.pid);await mkdir(profile,{recursive:true});
function browser(action){const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true});assert.equal(result.status,0,result.stderr);}
function fixture(modules,categories){
 const original=window.fetch.bind(window),state=window.workspaceCheck={unexpected:[],notices:[],prefs:{degree:'bachelor',year:null,major:'',courses:[],shape:'unknown',mental:'unknown',interests:{},requirements:''},proposals:[{id:'p1',state:'pending',event:{title:'合成科研讲座',starts_at:'2030-10-18T14:00:00+08:00',location:'教学楼'},quote:'讲座时间：2030年10月18日 14:00。'}]};
 const sources=[{id:'bb:1',source:'blackboard',title:'合成课程',code:'CS100',term:'2026-fall',url:'https://example.edu/bb'},{id:'gs:1',source:'gradescope',title:'Synthetic Course',code:'CS100',term:'2026-fall',url:'https://example.edu/gs'}];
 sources[0].grades=[{title:'合成测试',score:88,max_score:100}];
 const course={id:'course:1',title:'合成课程',code:'CS100',term:'2026-fall',current:true,course_ids:['bb:1','gs:1'],sources};
 const data={courses:[course],assignments:[{id:'a:1',course_id:'gs:1',title:'合成作业',source:'gradescope',submitted:false,due_at:'2030-10-18T23:59:00+08:00',url:'https://example.edu/assignment'}],materials:[{id:'m:1',course_id:'bb:1',title:'合成讲义.pdf',source:'blackboard',body_text:'复习向量与矩阵。',url:'https://example.edu/slides'}],announcements:[],posts:[],lessons:[],timetable:[],issues:[],metadata:{current_semester:'2026-fall'}};
 const messages=[{id:'mail:1',source:'mail',title:'合成活动通知',sender:'教学服务',received_at:'2026-10-17T10:00:00+08:00',unread:true,url:'https://example.edu/mail',classification:{bucket:'recommend',category:'科研讲座',by:'agent',summary:'活动时间与研究主题摘要。',reason:'符合已保存的兴趣。',evidence:[{source:'body_text',quote:'合成正文第一段'}]}}];
 const agent=()=>({available:true,owner:'synthetic',enabled:true,running:false,last_checked:'2026-10-17T10:00:00Z',summary:'合成检查完成',notices:state.notices,proposals:state.proposals});
 const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
 window.fetch=async(url,options={})=>{
  const target=new URL(url,location.origin);if(!target.pathname.startsWith('/api/v1/'))return original(url,options);
  const path=target.pathname.replace('/api/v1',''),method=options.method||'GET';
  if(path==='/bootstrap')return json({csrf_token:'synthetic',modules,categories});
  if(path==='/modules')return json({modules,categories});
  if(path==='/modules/campus-agent/status'||path==='/modules/notifications/agent/status')return json(agent());
  if(path==='/modules/mail/snapshot')return json({status:'ready',data:{messages,issues:[]}});
  if(path==='/modules/mail/intelligence')return json({messages,preferences:state.prefs,buckets:{focus:'重点关注',recommend:'兴趣推荐',digest:'摘要',filter:'已筛选'},interests:{research:'科研讲座',clubs:'社团活动'}});
  if(path==='/modules/mail/message')return json({body_html:'<p>合成正文第一段<br>补充说明。</p><p>第二段单独说明活动安排。</p><ul><li>准备材料</li><li>阅读讲义</li></ul><table><tr><th>时间</th><th>地点</th></tr><tr><td>14:00</td><td>教学楼</td></tr></table>'});
  if(path==='/modules/mail/preferences'){state.prefs=JSON.parse(options.body);return json({saved:true});}
  if(path==='/modules/mail/labels'){const value=JSON.parse(options.body);Object.assign(messages[0].classification,{category:value.label,bucket:value.bucket,by:'manual'});return json({saved:true});}
  if(path==='/modules/courses/snapshot')return json({status:'ready',data});
  if(path==='/modules/courses/groups')return json({groups:[]});
  if(path==='/modules/courses/course')return json({course,...data});
  if(path==='/modules/notifications/snapshot')return json({items:state.notices,configured:true,auto_generate:false});
  if(path==='/modules/notifications/proposals/p1/accept'){state.proposals[0].state='accepted';return json(state.proposals[0]);}
  if(path.endsWith('/read')&&path.startsWith('/modules/notifications/')){state.notices[0].read=JSON.parse(options.body).read;return json({saved:true});}
  state.unexpected.push(method+' '+path);return json({detail:'Unexpected synthetic route'},400);
 };
}
let socket;browser('open');
try{
 const port=(await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0],tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 socket=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);await new Promise((ok,no)=>{socket.addEventListener('open',ok,{once:true});socket.addEventListener('error',no,{once:true});});
 const pending=new Map(),errors=[];let serial=0;
 socket.addEventListener('message',({data})=>{const message=JSON.parse(data);if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text);const task=pending.get(message.id);if(task){pending.delete(message.id);clearTimeout(task.timer);message.error?task.no(new Error(JSON.stringify(message.error))):task.ok(message.result);}});
 const command=(method,params={})=>new Promise((ok,no)=>{const id=++serial,timer=setTimeout(()=>no(new Error(method)),20000);pending.set(id,{ok,no,timer});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result=>{assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;});
 await command('Page.enable');await command('Runtime.enable');await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)});`});
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url:base+'/#mail'});
 await evaluate(`window.waitFor=async condition=>{for(let i=0;i<180;i++){if(condition())return;await new Promise(r=>setTimeout(r,60));}throw new Error('Workspace UI timed out');};waitFor(()=>document.querySelector('[data-message]'))`);
 await evaluate(`document.querySelector('[data-message]').click();waitFor(()=>document.querySelector('.mail-body p'))`);
 assert.equal(await evaluate(`document.querySelectorAll('.mail-body p').length`),2);
 assert(await evaluate(`parseFloat(getComputedStyle(document.querySelector('.mail-body p')).marginBottom)>=14`),'Readable paragraph spacing');
 assert(await evaluate(`parseFloat(getComputedStyle(document.querySelector('.mail-body')).lineHeight)>26`));
 await writeFile(resolve('.codex/tmp/workspace-mail-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 await evaluate(`document.querySelector('[data-preferences]').click();document.querySelector('[name=requirements]').value='关注集成电路相关讲座，保留完整的筛选要求。';document.querySelector('.mail-preferences').requestSubmit();waitFor(()=>!document.querySelector('dialog[open]'))`);
 assert.equal(await evaluate(`workspaceCheck.prefs.requirements`),'关注集成电路相关讲座，保留完整的筛选要求。');
 await evaluate(`document.querySelector('[data-label]').click();document.querySelector('dialog [name=bucket]').value='focus';document.querySelector('dialog form').requestSubmit();waitFor(()=>!document.querySelector('dialog[open]'))`);
 assert(await evaluate(`document.querySelector('.mail-tag').textContent.includes('手动')`));
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 assert(await evaluate(`document.documentElement.scrollWidth<=innerWidth`));
 await writeFile(resolve('.codex/tmp/workspace-mail-mobile.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await evaluate(`location.hash='courses';waitFor(()=>document.querySelector('.course-platforms'))`);
 assert.equal(await evaluate(`document.querySelectorAll('.module-tabs').length`),0,'Courses have one integrated page');
 assert.equal(await evaluate(`document.querySelectorAll('.course-platforms a').length`),2,'Course links combine platforms');
 await evaluate(`document.querySelector('[data-kind=materials]').click()`);
 assert(await evaluate(`document.querySelector('[data-content]').textContent.includes('合成讲义.pdf')`));
 await evaluate(`document.querySelector('[data-kind=grades]').click()`);
 assert(await evaluate(`document.querySelector('[data-content]').textContent.includes('88 / 100')`),'Available platform marks remain visible');
 assert.equal(await evaluate(`!!document.querySelector('link[href*="/mail/"]')`),false,'Mail styles release after leaving');
 await writeFile(resolve('.codex/tmp/workspace-courses-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 await evaluate(`workspaceCheck.notices.push({id:'notice:1',title:'合成科研讲座',summary:'**有新的活动建议**，请确认是否参加。',why:'依据通知中的时间。',importance:'important',citations:[],source_revision:'r1',proposal_id:'p1',read:false});waitFor(()=>!document.querySelector('.campus-agent-peek').hidden)`);
 assert.equal(await evaluate(`document.querySelectorAll('.campus-agent-widget').length`),1,'Background entry survives navigation once');
 await evaluate(`location.hash='notifications';waitFor(()=>document.querySelector('[data-attend]'))`);
 assert.equal(await evaluate(`document.querySelectorAll('.notice-summary strong').length`),1);
 await evaluate(`document.querySelector('[data-attend]').click();waitFor(()=>workspaceCheck.proposals[0].state==='accepted'&&!document.querySelector('[data-attend]'))`);
 assert(await evaluate(`document.querySelector('.notice-event').textContent.includes('已加入时间表')`));
 await writeFile(resolve('.codex/tmp/workspace-notifications-desktop.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
 assert.deepEqual(await evaluate(`workspaceCheck.unexpected`),[]);assert.deepEqual(errors,[]);
 console.log('PASS campus workspace UI: email reading/preferences/manual priority, course-first integration, background alerts, consent actions, Markdown, mobile and style cleanup');
}finally{socket?.close();browser('close');}
