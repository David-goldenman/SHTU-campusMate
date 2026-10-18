import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.argv[2]||'http://127.0.0.1:16666';
const output=resolve('.codex/tmp/courses-ui'),profile=resolve(output,'browser-'+process.pid);
await mkdir(profile,{recursive:true});
function browser(action){
  const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{
    input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true,
  });assert.equal(result.status,0,result.stderr);
}
function fixture(){
  const original=window.fetch.bind(window);
  const source=(id,kind,title,extra={})=>({id,source:kind,title,code:'CS100',term:'2026-fall',url:'https://example.invalid/'+id,...extra});
  const sources=[source('bb:1','blackboard','合成计算机课程',{grades:[{title:'合成考试',score:88,max_score:100}]}),
    source('elrc:1','elrc','合成计算机课程'),source('ecourse:1','ecourse','合成计算机课程')];
  const courses=[{id:'merged',title:'合成计算机课程',code:'CS100',term:'2026-fall',current:true,
    course_ids:sources.map(item=>item.id),sources,department:'信息学院',
    appearance:{key:'sist',label:'信息',accent:'#5e81ac',tint:'#eaf3fb',ink:'#264b73'}},
    {id:'empty',title:'合成数学课程',code:'MATH100',term:'2026-fall',current:true,course_ids:['elrc:2'],sources:[source('elrc:2','elrc','合成数学课程')]},
    {id:'unknown',title:'合成待确认课程',code:'HUM100',term:'2026-fall',current:true,course_ids:['bb:3'],sources:[source('bb:3','blackboard','合成待确认课程')]},
    {id:'history',title:'合成历史课程',code:'CS099',term:'2025-fall',current:false,course_ids:['elrc:4'],sources:[source('elrc:4','elrc','合成历史课程')]}];
  const state=window.courseCheck={calls:[],groups:[],sourceStatus:'ready',groupsDelay:0};
  const data={courses,metadata:{current_semester:'2026-fall',source_metadata:{elrc:{status:'ready'}}},issues:[],
    assignments:[{id:'ecourse:pending',course_id:'ecourse:1',source:'ecourse',title:'合成待办',submitted:false,actionable:true,submission_status:'draft',due_at:'2026-11-01T23:59:00+08:00'},
      {id:'ecourse:exempt',course_id:'ecourse:1',source:'ecourse',title:'合成豁免',submitted:false,actionable:true,submission_status:'exempt'},
      {id:'bb:uncertain',course_id:'bb:1',source:'blackboard',title:'合成待核实',submitted:false,actionable:true,submission_status:'unknown'}],
    lessons:[{id:'lesson:1',course_id:'elrc:1',source:'elrc',title:'合成课堂录播',url:'https://example.invalid/video',body_text:'合成课堂转写',summary_text:'合成摘要'}],
    materials:[{id:'material:1',course_id:'bb:1',source:'blackboard',title:'合成讲义.pdf',url:'https://example.invalid/slides'}],announcements:[],posts:[],timetable:[]};
  const json=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname,method=options.method||'GET';
    if(path==='/api/v1/bootstrap'){
      const value=await(await original(url,options)).json();
      // Keep synthetic theme checks in browser-only mode; never save real workspace preferences.
      delete value.settings.appearance;
      value.modules=value.modules.filter(module=>module.id==='courses');return json(value);
    }
    if(path.startsWith('/api/v1/modules/courses/')){
      state.calls.push({path,method});
      if(path.endsWith('/snapshot')){data.metadata.source_metadata.elrc.status=state.sourceStatus;return json({status:'ready',data});}
      if(path.endsWith('/sync'))return json({queued:true});
      if(path.endsWith('/groups')){
        if(state.groupsDelay)await new Promise(resolve=>setTimeout(resolve,state.groupsDelay));
        if(method==='PUT')state.groups=JSON.parse(options.body).groups;
        return json({groups:state.groups});
      }
      throw new Error('Unexpected course request: '+path);
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
  let serial=0;const pending=new Map(),errors=[];
  socket.addEventListener('message',({data})=>{
    const message=JSON.parse(data);if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
    const task=pending.get(message.id);if(!task)return;clearTimeout(task.timer);pending.delete(message.id);
    message.error?task.reject(new Error(JSON.stringify(message.error))):task.resolve(message.result);
  });
  const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++serial,timer=setTimeout(()=>reject(new Error(method)),20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=expression=>command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result=>{assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;});
  const wait=expression=>evaluate(`(async()=>{for(let i=0;i<160;i++){if(${expression})return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timed out: '+${JSON.stringify(expression)});})()`);
  const ready=()=>wait("document.querySelector('.course-recording-summary') && document.querySelector('[data-course-content]')");
  await command('Page.enable');await command('Runtime.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})()`});
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:base+'/#courses'});await ready();
  assert.equal(await evaluate("document.querySelectorAll('[data-course]').length"),3);
  assert.equal(await evaluate("document.querySelector('[data-course=merged] .course-pending').textContent"),'1 项待办');
  assert(await evaluate("document.querySelector('[data-kind=assignments]').getAttribute('aria-selected')==='true' && document.querySelector('.course-department').textContent==='信息'"));
  await evaluate("document.querySelector('[data-view-recordings]').click()");
  assert(await evaluate("document.querySelector('[data-course-content]').textContent.includes('含课堂转写 · 含内容摘要') && document.querySelector('.course-recording-open a').href==='https://example.invalid/video'"));
  await evaluate("document.querySelector('[data-filter=empty]').click()");
  assert(await evaluate("document.querySelectorAll('[data-course]').length===1 && document.querySelector('[data-course=empty]') && document.querySelector('[data-course-content]').textContent.includes('暂无录播')"));
  await evaluate("document.querySelector('[data-filter=unknown]').click()");
  assert(await evaluate("document.querySelector('[data-course=unknown]') && document.querySelector('[data-course-content]').textContent.includes('尚未关联')"));
  await evaluate("document.querySelector('[data-filter=all]').click();document.querySelector('[data-current]').click();var input=document.querySelector('[data-search]');input.value='CS099';input.dispatchEvent(new Event('input',{bubbles:true}))");
  assert(await evaluate("document.querySelectorAll('[data-course]').length===1 && document.querySelector('[data-course=history]') && document.querySelector('.course-detail-header').textContent.includes('2025 年秋季')"));
  await evaluate("var input=document.querySelector('[data-search]');input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-current]').click();document.querySelector('[data-course=merged]').click();document.querySelector('[data-kind=materials]').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true,cancelable:true}))");
  assert(await evaluate("document.activeElement.matches('[data-kind=grades]') && document.querySelector('[data-course-content]').textContent.includes('88 / 100')"));
  assert.deepEqual(await evaluate('courseCheck.calls'),[{path:'/api/v1/modules/courses/snapshot',method:'GET'}],'Browsing uses one snapshot and no per-course/group requests');
  await evaluate("document.querySelector('[data-group]').click()");await wait("document.querySelector('dialog[open] [name=title]')");
  await evaluate("var form=document.querySelector('dialog[open] form');form.elements.title.value='合成关联课程';for(const input of [...form.querySelectorAll('[name=member]')].slice(0,2))input.checked=true;form.requestSubmit()");
  await wait("courseCheck.groups.length===1 && !document.querySelector('dialog[open]')");
  assert.equal(await evaluate('courseCheck.groups[0].title'),'合成关联课程');
  await evaluate("courseCheck.sourceStatus='error';document.querySelector('[data-sync]').click()");
  await wait("document.querySelector('[data-course=empty] .course-recording-badge').textContent==='录播待确认'");
  assert(await evaluate("document.querySelector('[data-course=merged] .course-recording-badge').textContent.includes('有录播')"));

  for(const theme of ['default','observatory','star-notes','arknights']){
    await evaluate(`(async()=>{courseCheck.sourceStatus='ready';const appearance=await import('/assets/themes/appearance.js');await appearance.themeContext().select(${JSON.stringify(theme)});})()`);await ready();
    for(const [width,height,label] of [[1440,1050,'desktop'],[390,844,'mobile']]){
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<800});
      await evaluate("scrollTo(0,0);new Promise(r=>setTimeout(r,350))");
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),theme+' '+label+' overflow');
      assert(await evaluate("document.querySelector('.course-recording-summary>div').getBoundingClientRect().width>=150"),theme+' '+label+' recording text stays readable');
      await writeFile(resolve(output,theme+'-'+label+'.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
      await evaluate("document.querySelector('[data-view-recordings]').click();document.querySelector('.course-detail').scrollIntoView({block:'start'});new Promise(r=>setTimeout(r,80))");
      await writeFile(resolve(output,theme+'-'+label+'-detail.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
    }
  }
  await evaluate("courseCheck.groupsDelay=300;document.querySelector('[data-group]').click();window.oldCourses=document.querySelector('.course-hub');location.hash='settings'");
  await wait("!document.querySelector('.course-hub') && !oldCourses.isConnected");
  await evaluate('new Promise(resolve=>setTimeout(resolve,500))');
  assert(await evaluate("!document.querySelector('dialog[open]') && !oldCourses.classList.contains('course-hub') && ![...document.querySelectorAll('link[rel=stylesheet]')].some(link=>link.href.includes('/courses/'))"));
  assert.deepEqual(errors,[]);
  console.log('PASS: recording filters/evidence, Ecourse pending states, snapshot-only browsing, grouping, keyboard navigation, four desktop/mobile themes and lifecycle cleanup');
}finally{socket?.close();browser('close');}
