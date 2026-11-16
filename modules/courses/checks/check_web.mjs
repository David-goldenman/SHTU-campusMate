import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.argv[2]||'http://127.0.0.1:16666';
const output=resolve('.codex/tmp/courses-ui');
await mkdir(output,{recursive:true});
const profile=await mkdtemp(resolve(output,'browser-'));
function browser(action){
  const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{
    input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true,
  });assert.equal(result.status,0,result.stderr);
}
function fixture(){
  const original=window.fetch.bind(window);
  const source=(id,kind,title,extra={})=>({id,source:kind,title,code:'CS100',term:'2026-fall',url:'https://example.invalid/'+id,...extra});
  const sources=[source('bb:1','blackboard','合成计算机课程',{grades:[{title:'合成考试',score:88,max_score:100}]}),
    source('elrc:1','elrc','合成计算机课程'),source('ecourse:1','ecourse','合成计算机课程'),source('piazza:1','piazza','合成计算机课程')];
  const courses=[{id:'merged',title:'合成计算机课程',aliases:['Synthetic Computer Science'],title_source:'timetable',code:'CS100',term:'2026-fall',current:true,
    course_ids:sources.map(item=>item.id),sources,department:'信息学院',
    appearance:{key:'sist',label:'信息',accent:'#5e81ac',tint:'#eaf3fb',ink:'#264b73'}},
    {id:'empty',title:'合成数学课程',code:'MATH100',term:'2026-fall',current:true,course_ids:['elrc:2'],sources:[source('elrc:2','elrc','合成数学课程')]},
    {id:'unknown',title:'合成待确认课程',code:'HUM100',term:'2026-fall',current:true,course_ids:['bb:3'],sources:[source('bb:3','blackboard','合成待确认课程')]},
    {id:'history',title:'合成历史课程',code:'CS099',term:'2025-fall',current:false,course_ids:['elrc:4'],sources:[source('elrc:4','elrc','合成历史课程')]}];
  const state=window.courseCheck={calls:[],groups:[],sourceStatus:'ready',groupsDelay:0,playerDelay:0,downloadVersion:'v1',downloadBody:'synthetic PDF v1',fileCalls:0,extraFiles:[],autoSyncs:0};
  state.pickerCalls=0;
  window.showDirectoryPicker=()=>{state.pickerCalls++;return navigator.storage.getDirectory();};
  const courseFile={id:'piazza:file',course_id:'piazza:1',source:'piazza',title:'Lecture1.pdf',resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id=piazza%3Afile'};
  const data={courses,metadata:{current_semester:'2026-fall',source_metadata:{elrc:{status:'ready'}}},issues:[],
    assignments:[{id:'ecourse:pending',course_id:'ecourse:1',source:'ecourse',title:'合成待办',submitted:false,actionable:true,submission_status:'draft',due_at:'2026-11-01T23:59:00+08:00'},
      {id:'ecourse:exempt',course_id:'ecourse:1',source:'ecourse',title:'合成豁免',submitted:false,actionable:true,submission_status:'exempt'},
      {id:'bb:uncertain',course_id:'bb:1',source:'blackboard',title:'合成待核实',submitted:false,actionable:true,submission_status:'unknown'}],
    lessons:[{id:'lesson:1',course_id:'elrc:1',source:'elrc',title:'合成课堂录播',url:'https://example.invalid/video',body_text:'合成课堂转写',summary_text:'合成摘要'}],
    materials:[{id:'material:1',course_id:'bb:1',source:'blackboard',title:'合成讲义.pdf',url:'https://example.invalid/slides'},courseFile],announcements:[],posts:[],timetable:[]};
  state.data=data;
  const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname,method=options.method||'GET';
    if(path==='/api/v1/bootstrap'){
      const value=await(await original(url,options)).json();
      // Keep synthetic theme checks in browser-only mode; never save real workspace preferences.
      delete value.settings.appearance;
      value.modules=value.modules.filter(module=>module.id==='courses');
      return json(value);
    }
    if(path.startsWith('/api/v1/modules/courses/')){
      state.calls.push({path,method});
      if(path.endsWith('/view-state'))return json({account_revision:'synthetic-school-owner'});
      if(path.endsWith('/snapshot')){data.metadata.source_metadata.elrc.status=state.sourceStatus;return json({status:'ready',data,account_revision:'synthetic-school-owner'});}
      if(path.endsWith('/sync'))return json({queued:true});
      if(path.endsWith('/groups')){
        if(state.groupsDelay)await new Promise(resolve=>setTimeout(resolve,state.groupsDelay));
        const owner=state.groupsOwner || 'synthetic-school-owner';
        if(method==='PUT'){
          const body=state.lastGroupWrite=JSON.parse(options.body);
          if(body.account_revision!==owner)return json({detail:'账号已更新，请重新打开课程分组。'},409);
          state.groups=body.groups;
        }
        return json({groups:state.groups,account_revision:owner});
      }
      throw new Error('Unexpected course request: '+path);
    }
    if(path==='/api/v1/modules/piazza/snapshot')return json({status:'ready',account_revision:'synthetic-download-owner',data:{materials:[{...courseFile,updated_at:state.downloadVersion},...state.extraFiles]}});
    if(path==='/api/v1/modules/piazza/sync'){state.autoSyncs++;return json({status:'syncing'});}
    if(path==='/api/v1/modules/piazza/file'){state.fileCalls++;return new Response(state.downloadBody,{headers:{'content-type':'application/pdf','content-disposition':'attachment; filename="Lecture1.pdf"'}});}
    if(path==='/api/v1/modules/elrc/playback'){
      if(state.playerDelay)await new Promise(resolve=>setTimeout(resolve,state.playerDelay));
      return json({token:'synthetic',selected:'0',lessons:[{id:'0',title:'第 1 周 · 合成课堂'}]});
    }
    if(path==='/api/v1/modules/elrc/playback/synthetic/sources')return json({sources:[{id:'one',label:'教师画面',url:'/api/v1/modules/elrc/playback/synthetic/media/one'},{id:'two',label:'屏幕画面',url:'/api/v1/modules/elrc/playback/synthetic/media/two'}]});
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
  assert(await evaluate("document.querySelector('.course-detail-header').textContent.includes('名称来源：教务课表')"));
  await evaluate("var aliasSearch=document.querySelector('[data-search]');aliasSearch.value='Synthetic Computer Science';aliasSearch.dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await evaluate("document.querySelectorAll('[data-course]').length"),1);
  await evaluate("aliasSearch.value='';aliasSearch.dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await evaluate("document.querySelector('[data-course=merged] .course-pending').textContent"),'1 项待办');
  assert(await evaluate("document.querySelector('[data-kind=assignments]').getAttribute('aria-selected')==='true' && document.querySelector('.course-department').textContent==='信息'"));
  await evaluate("document.querySelector('[data-kind=materials]').click()");
  assert(await evaluate("document.querySelector('.course-download-toolbar').textContent.includes('每门课自动建立独立文件夹')"));
  await evaluate("document.querySelector('[data-choose]').click()");await wait("document.querySelector('[data-check]')");
  assert.equal(await evaluate('courseCheck.fileCalls'),0,'Remembering a root with auto off does not download');
  await evaluate("document.querySelector('[data-check-all]').click()");
  await wait("document.querySelector('.course-download-status').textContent.includes('新增或更新 1 个')");
  await evaluate("(async()=>{const root=await navigator.storage.getDirectory();const semester=await root.getDirectoryHandle('2026 年秋季');courseCheck.downloadDirectory=await semester.getDirectoryHandle('CS100 · 合成计算机课程');courseCheck.mathDirectory=await semester.getDirectoryHandle('MATH100 · 合成数学课程');const history=await root.getDirectoryHandle('2025 年秋季');await history.getDirectoryHandle('CS099 · 合成历史课程');})()");
  assert.equal(await evaluate("(async()=>{const handle=await courseCheck.downloadDirectory.getFileHandle('Lecture1.pdf');return (await handle.getFile()).text();})()"),'synthetic PDF v1');
  await evaluate("courseCheck.downloadVersion='v2';courseCheck.downloadBody='synthetic PDF v2';document.querySelector('[data-check]').click()");
  await wait("courseCheck.fileCalls===2 && document.querySelector('.course-download-status').textContent.includes('新增或更新 1 个')");
  assert.equal(await evaluate("(async()=>{const handle=await courseCheck.downloadDirectory.getFileHandle('Lecture1.pdf');return (await handle.getFile()).text();})()"),'synthetic PDF v2');
  assert.equal(await evaluate("(async()=>{const entries=[];for await(const [name] of courseCheck.downloadDirectory.entries())entries.push(name);return entries.join(',');})()"),'Lecture1.pdf');
  await evaluate("(async()=>{const handle=await courseCheck.downloadDirectory.getFileHandle('Lecture1.pdf');const writer=await handle.createWritable();await writer.write('my annotations');await writer.close();courseCheck.downloadVersion='v3';document.querySelector('[data-check]').click();})()");
  await wait("document.querySelector('.course-download-status').textContent.includes('保留本地文件 1 个')");
  assert.equal(await evaluate('courseCheck.fileCalls'),2);
  assert.equal(await evaluate("(async()=>{const handle=await courseCheck.downloadDirectory.getFileHandle('Lecture1.pdf');return (await handle.getFile()).text();})()"),'my annotations');
  await evaluate("document.querySelector('[data-view-recordings]').click()");
  assert(await evaluate("document.querySelector('[data-course-content]').textContent.includes('含课堂转写 · 含内容摘要') && document.querySelector('.course-recording-open a').href==='https://example.invalid/video'"));
  await evaluate("document.querySelector('[data-play-recording]').click()");
  await wait("document.querySelector('dialog[open] video') && document.querySelectorAll('.recording-angles button').length===2");
  assert(await evaluate("document.querySelector('[data-lesson]').value==='0' && document.querySelector('[data-original]').href==='https://example.invalid/video'"));
  await evaluate("window.closedVideo=document.querySelector('video');document.querySelector('dialog[open]').close()");
  await wait("!document.querySelector('video') && !document.querySelector('dialog[open]')");
  assert(await evaluate("closedVideo.paused && !closedVideo.getAttribute('src')"));
  await evaluate("courseCheck.playerDelay=200;document.querySelector('[data-play-recording]').click()");
  await wait("document.querySelector('dialog[open].recording-dialog')");
  await evaluate("document.querySelector('dialog[open]').close();new Promise(r=>setTimeout(r,300))");
  assert(await evaluate("!document.querySelector('dialog[open]') && !document.querySelector('video')"));
  await evaluate("courseCheck.playerDelay=0");
  await evaluate("document.querySelector('[data-filter=empty]').click()");
  assert(await evaluate("document.querySelectorAll('[data-course]').length===1 && document.querySelector('[data-course=empty]') && document.querySelector('[data-course-content]').textContent.includes('暂无录播')"));
  await evaluate("document.querySelector('[data-filter=unknown]').click()");
  assert(await evaluate("document.querySelector('[data-course=unknown]') && document.querySelector('[data-course-content]').textContent.includes('尚未关联')"));
  await evaluate("document.querySelector('[data-filter=all]').click();document.querySelector('[data-current]').click();var input=document.querySelector('[data-search]');input.value='CS099';input.dispatchEvent(new Event('input',{bubbles:true}))");
  assert(await evaluate("document.querySelectorAll('[data-course]').length===1 && document.querySelector('[data-course=history]') && document.querySelector('.course-detail-header').textContent.includes('2025 年秋季')"));
  await evaluate("var input=document.querySelector('[data-search]');input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-current]').click();document.querySelector('[data-course=merged]').click();document.querySelector('[data-kind=materials]').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true,cancelable:true}))");
  assert(await evaluate("document.activeElement.matches('[data-kind=grades]') && document.querySelector('[data-course-content]').textContent.includes('88 / 100')"));
  assert.deepEqual(await evaluate('courseCheck.calls'),[{path:'/api/v1/modules/courses/snapshot',method:'GET'}],'Browsing uses one snapshot and no per-course/group requests');
  await evaluate("courseCheck.data.courses.push({id:'new-course',title:'新增课程',code:'NEW200',term:'2027-spring',current:true,course_ids:['piazza:new'],sources:[{id:'piazza:new',source:'piazza',title:'新增课程'}]});document.querySelector('[data-sync]').click()");
  await wait("document.querySelector('[data-root-status]').textContent.includes('5 门课程')");
  await evaluate("(async()=>{const root=await navigator.storage.getDirectory();const semester=await root.getDirectoryHandle('2027 年春季');await semester.getDirectoryHandle('NEW200 · 新增课程');})()");
  assert.equal(await evaluate('courseCheck.pickerCalls'),1,'New courses and semesters use the saved root without another picker');
  assert.equal(await evaluate('courseCheck.fileCalls'),2,'New courses do not silently enable automatic downloads');
  await evaluate("(async()=>{const source=performance.getEntriesByType('resource').find(item=>item.name.includes('/module-assets/courses/')&&item.name.endsWith('/web/download-store.js')).name;window.downloadSettings=(await import(source)).folderStore();})()");
  await evaluate("document.querySelector('[data-course=new-course]').click();document.querySelector('[data-kind=materials]').click()");
  assert(await evaluate("document.querySelector('[data-auto]').checked && document.querySelector('.course-download-toolbar').textContent.includes('跟随总设置（已暂停）')"));
  await evaluate("document.querySelector('[data-auto]').click()");
  await wait("(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','new-course']))).auto===false");
  await evaluate("document.querySelector('[data-auto-all]').click()");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).auto===true");
  assert(await evaluate("!document.querySelector('[data-auto]').checked"),'The master switch preserves an individual exclusion');
  await evaluate("courseCheck.extraFiles=[{id:'new-file',course_id:'piazza:new',source:'piazza',title:'Lecture1.pdf',updated_at:'v1',resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id=new-file'},{id:'future-file',course_id:'piazza:future',source:'piazza',title:'Lecture1.pdf',updated_at:'v1',resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id=future-file'}];courseCheck.data.courses.push({id:'future-course',title:'跟随总设置课程',code:'FUT300',term:'2027-fall',current:true,course_ids:['piazza:future'],sources:[{id:'piazza:future',source:'piazza',title:'跟随总设置课程'}]});document.querySelector('[data-sync]').click()");
  await wait("(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','future-course'])))?.files['future-file']");
  assert.equal(await evaluate('courseCheck.fileCalls'),3,'A future course inherits global on while the excluded course stays off');
  await evaluate("document.querySelector('[data-auto-all]').click()");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).auto===false");
  await evaluate("document.querySelector('[data-auto]').click()");
  await wait("(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','new-course']))).auto===null");
  assert.equal(await evaluate('courseCheck.fileCalls'),3,'Following a disabled master does not start a download');
  await evaluate("document.querySelector('[data-check]').click()");
  await wait("(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','new-course']))).files['new-file']");
  assert.equal(await evaluate('courseCheck.fileCalls'),4,'Manual download works with the global switch off');
  await evaluate("document.querySelector('[data-auto]').click()");
  await wait("(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','new-course']))).auto===false");
  await evaluate("document.querySelector('[data-auto-all]').click()");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).auto===true");
  await evaluate("document.querySelector('[data-choose]').click()");
  await wait("courseCheck.pickerCalls===2 && document.querySelector('[data-root-status]').textContent.includes('6 门课程')");
  assert(await evaluate("(async()=> (await downloadSettings.getRoot('synthetic-download-owner')).auto && (await downloadSettings.get(JSON.stringify(['synthetic-download-owner','new-course']))).auto===false)()"),'Selecting a root again retains both master and course preferences');
  assert.equal(await evaluate("document.querySelector('[data-auto-interval]').value"),'15');
  await evaluate("var intervalSelect=document.querySelector('[data-auto-interval]');intervalSelect.value='30';intervalSelect.dispatchEvent(new Event('change'))");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).checkIntervalMinutes===30");
  // Finish an already-running settings-triggered check before advancing the fixture's clock.
  // Otherwise that older check may correctly refresh lastAutoCheckAt after our synthetic backdate.
  await evaluate("navigator.locks.request('campusmate-course-auto-check',async()=>{})");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).lastAutoState!=='checking'");
  await evaluate("(async()=>{const root=await downloadSettings.getRoot('synthetic-download-owner');await downloadSettings.updateRoot(root.revision,latest=>({...latest,lastAutoState:'ready',lastAutoCheckAt:Date.now()-31*60000}));courseCheck.extraFiles.find(item=>item.id==='future-file').updated_at='v2';courseCheck.downloadBody='synthetic background PDF';courseCheck.beforeBackgroundSync=courseCheck.autoSyncs;location.hash='settings';})()");
  await wait("!document.querySelector('.course-hub')");
  await evaluate("window.dispatchEvent(new Event('campus:courses-download-settings'))");
  try {await wait("courseCheck.autoSyncs>courseCheck.beforeBackgroundSync && courseCheck.fileCalls===5");}
  catch(error) {
    console.log('Background diagnostics',await evaluate("(async()=>({syncs:courseCheck.autoSyncs,before:courseCheck.beforeBackgroundSync,files:courseCheck.fileCalls,calls:courseCheck.calls,root:{...(await downloadSettings.getRoot('synthetic-download-owner')),directory:undefined},binding:{...(await downloadSettings.get(JSON.stringify(['synthetic-download-owner','future-course']))),directory:undefined,parentDirectory:undefined,semesterDirectory:undefined,legacyDirectory:undefined},backgroundScripts:performance.getEntriesByType('resource').filter(item=>item.name.includes('/courses/')&&item.name.includes('background')).map(item=>item.name)}))()"));
    throw error;
  }
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).lastAutoState==='ready'");
  assert.equal(await evaluate("(async()=>{const root=await navigator.storage.getDirectory(),term=await root.getDirectoryHandle('2027 年秋季'),directory=await term.getDirectoryHandle('FUT300 · 跟随总设置课程');return (await(await directory.getFileHandle('Lecture1.pdf')).getFile()).text();})()"),'synthetic background PDF','The resident background updates files while a different page is open');
  await evaluate("location.hash='courses'");await ready();
  await wait("document.querySelector('[data-auto-interval]').value==='30'");
  assert(await evaluate("document.querySelector('[data-auto-status]').textContent.includes('后台检查完成')"));
  await evaluate("(async()=>{await downloadSettings.updateRoot('synthetic-download-owner',latest=>({...latest,lastAutoState:'permission',lastAutoMessage:'需要重新允许访问总目录。'}));location.hash='settings';})()");
  await wait("!document.querySelector('.course-hub')");await evaluate("location.hash='courses'");await ready();
  await wait("document.querySelector('[data-check-all]').textContent==='允许访问并继续'");
  await evaluate("document.querySelector('[data-check-all]').click()");
  await wait("(await downloadSettings.getRoot('synthetic-download-owner')).lastAutoState!=='permission' && document.querySelector('[data-check-all]').textContent==='检查全部课程'");
  await evaluate('scrollTo(0,0)');await writeFile(resolve(output,'shared-download-root.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  await evaluate("document.querySelector('[data-forget]').click()");await wait("!document.querySelector('[data-check-all]')");
  assert.equal(await evaluate("(async()=>{const handle=await courseCheck.downloadDirectory.getFileHandle('Lecture1.pdf');return (await handle.getFile()).text();})()"),'my annotations','Forgetting the shared root keeps user files');
  await evaluate("document.querySelector('[data-group]').click()");await wait("document.querySelector('dialog[open] [name=title]')");
  await evaluate("var form=document.querySelector('dialog[open] form');form.elements.title.value='合成关联课程';for(const input of [...form.querySelectorAll('[name=member]')].slice(0,2))input.checked=true;form.requestSubmit()");
  await wait('courseCheck.lastGroupWrite');
  assert.equal(await evaluate('courseCheck.lastGroupWrite.account_revision'),'synthetic-school-owner','Grouping writes carry the account that opened the form');
  await wait("courseCheck.groups.length===1 && !document.querySelector('dialog[open]')");
  assert.equal(await evaluate('courseCheck.groups[0].title'),'合成关联课程');
  await evaluate("courseCheck.groupsOwner='another-account';document.querySelector('[data-group]').click()");
  await wait("document.querySelector('#toast').textContent.includes('账号')");
  assert.equal(await evaluate("!!document.querySelector('dialog[open] [name=title]')"),false,'A changed account cannot open a group form against an old course list');
  await evaluate("courseCheck.groupsOwner='synthetic-school-owner'");
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
  const upgraded=await evaluate(`(async()=>{
    await new Promise((resolve,reject)=>{const request=indexedDB.deleteDatabase('campusmate-course-downloads');request.onsuccess=resolve;request.onerror=()=>reject(request.error);});
    const owner='legacy-synthetic-owner',key=JSON.stringify([owner,'legacy-course']);
    const originRoot=await navigator.storage.getDirectory(),semester=await originRoot.getDirectoryHandle('2026 年秋季');
    const directory=await semester.getDirectoryHandle('CS100 · 合成计算机课程'),file=await(await directory.getFileHandle('Lecture1.pdf')).getFile();
    const db=await new Promise((resolve,reject)=>{const request=indexedDB.open('campusmate-course-downloads',1);request.onupgradeneeded=()=>request.result.createObjectStore('folders',{keyPath:'key'});request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
    await new Promise((resolve,reject)=>{const tx=db.transaction('folders','readwrite');tx.objectStore('folders').put({key,revision:owner,courseId:'legacy-course',directory,token:'legacy-token',auto:true,files:{notes:{name:'Lecture1.pdf',version:'old',managed:false,size:file.size,lastModified:file.lastModified}}});tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});db.close();
    const source=performance.getEntriesByType('resource').find(item=>item.name.includes('/module-assets/courses/')&&item.name.endsWith('/web/download-store.js')).name;
    const storage=(await import(source)).folderStore();const rows=await storage.all();
    const folders=await import(new URL('./download-folders.js',source));
    const root=await folders.withDownloadLock(new AbortController().signal,()=>folders.savedRoot(owner,storage,new AbortController().signal));
    const restored=await storage.getRoot(owner),saved=await storage.get(key);
    return {retained:rows.length===1&&saved.auto===true&&saved.token==='legacy-token'&&saved.files.notes.managed===false,rootRestored:await restored.directory.isSameEntry(directory),sameRootToken:root.token===restored.token,file:await(await(await directory.getFileHandle('Lecture1.pdf')).getFile()).text()};
  })()`);
  assert.deepEqual(upgraded,{retained:true,rootRestored:true,sameRootToken:true,file:'my annotations'},'IndexedDB v1 upgrade retains handles, manifests, local notes and preferences and promotes a single root');
  assert.deepEqual(errors,[]);
  console.log('PASS: periodic background source sync/downloads across page navigation, interval persistence, permission recovery, one root selection, future-course folders, global/course controls, native handles, IndexedDB migration, latest versions, local edits, recording/player races, grouping, four desktop/mobile themes and lifecycle cleanup');
}finally{socket?.close();browser('close');}
