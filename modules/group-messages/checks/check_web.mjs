import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base=process.argv[2]||'http://127.0.0.1:16666';
const output=resolve('.codex/tmp/group-messages-ui'),profile=resolve(output,'browser-'+process.pid);
await mkdir(profile,{recursive:true});
function browser(action){
  const result=spawnSync(process.execPath,[resolve('scripts/browser.mjs')],{
    input:JSON.stringify({action,profile,url:'about:blank',headless:true}),encoding:'utf8',windowsHide:true,
  });assert.equal(result.status,0,result.stderr);
}
function fixture(){
  const original=fetch.bind(window),json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
  const groups=[{id:'g1',name:'2026秋-电磁学',message_count:28},{id:'g2',name:'EE130P 2026秋',message_count:5},
    ...['课程讨论','作业通知','习题课','实验答疑'].map((name,index)=>({id:'g'+(index+3),name:'2026秋-电磁学 · '+name})),
    {id:'old',name:'2025秋-电磁学'},{id:'unmatched',name:'合成未匹配群'}];
  const selected={id:'g1',name:groups[0].name,course_id:'c1',trusted_senders:[],auto_extract:false,auto_apply:false};
  const state=window.groupCheck={calls:[],owner:'owner1',items:[],sources:{wechat:{connected:true,connection:'conn',revision:'r1',enabled:false,groups,selected:[selected],interval_seconds:300,history_days:7,allow_ai:false,coverage:{},account_label:'合成微信'},qq:{connected:false}}};
  window.fetch=async(url,options={})=>{
    const path=new URL(url,location.origin).pathname,method=options.method||'GET',body=options.body?JSON.parse(options.body):null;
    if(path==='/api/v1/bootstrap'){const value=await(await original(url,options)).json();delete value.settings.appearance;value.modules=value.modules.filter(row=>row.id==='group-messages');return json(value);}
    if(path.startsWith('/api/v1/modules/group-messages/')){
      const route=path.replace('/api/v1/modules/group-messages','');state.calls.push({route,method,body});
      if(route==='/status')return json({sources:state.sources,account_revision:state.owner,ai:{enabled:true,model:'合成模型'},running:null,queued:false});
      if(route==='/items')return json({items:state.items,account_revision:state.owner});
      if(route==='/courses'){
        const matches={};
        for(const [source,config] of Object.entries(state.sources))matches[source]=Object.fromEntries((config.groups||[]).map(group=>{
          const saved=(config.selected||[]).find(row=>row.id===group.id),status=saved?'saved':group.id==='old'?'other_term':group.id==='unmatched'?'unmatched':'automatic';
          return [group.id,{status,course_id:saved?.course_id||(status==='automatic'?(group.id==='g2'?'c2':'c1'):''),reason:saved?'沿用已保存的关联，可自行修改':status==='automatic'?'课程名称或代码一致':'需手动核对',candidates:[]}];
        }));
        return json({items:[{id:'c1',title:'电磁学',code:'EE130',term:'2026-fall',current:true},{id:'c2',title:'电磁学课程设计',code:'EE130P',term:'2026-fall',current:true}],matches,account_revision:state.owner,current_semester:'2026-fall'});
      }
      if(route==='/senders')return json({items:[{id:'teacher',name:'合成老师'},{id:'student',name:'合成同学'}]});
      if(route==='/messages')return json({items:[{sender_id:'teacher',sender_name:'合成老师',text:'作业1延期到2026年10月22日23:59截止',sent_at:'2026-10-18T12:00:00+08:00'}],total:1});
      if(route==='/sources/wechat'&&method==='PUT'){
        if(state.failSave){state.failSave=false;return json({detail:'合成保存失败，请重试。'},503);}
        if(state.delaySave)await new Promise(resolve=>setTimeout(resolve,350));
        Object.assign(state.sources.wechat,body,{selected:body.groups.map(row=>({...row,name:groups.find(g=>g.id===row.id).name})),revision:'r'+state.calls.length});return json({saved:true});
      }
      if(route==='/sources/wechat/pause'){state.sources.wechat.enabled=false;state.sources.wechat.revision='paused';return json({});}
      if(route.endsWith('/sync'))return json({queued:true});
      if(route==='/qq/connect'){state.sources.qq={...structuredClone(state.sources.wechat),connected:true,groups:[{id:'q1',name:'合成QQ课程群'}],selected:[],revision:'qr1',interval_seconds:20,account_label:'QQ · 0123'};return json({queued:true});}
      if(route==='/extract'){
        state.items=[{id:'item1',revision:'i1',content_revision:'ic1',source:'wechat',group_name:'合成计算机课程群',kind:'assignment',action:'change',title:'作业1延期',summary:'作业1延期到10月22日23:59，请核对课程平台。',status:'pending',course:{title:'合成计算机'},due_at:'2026-10-22T23:59:00+08:00',time_verified:true,citations:[{message_id:'m1',quote:'作业1延期到2026年10月22日23:59截止',sender_name:'合成老师',sent_at:'2026-10-18T12:00:00+08:00'}]}];return json({queued:true});
      }
      if(route==='/items/item1/decision'){const item=state.items[0];item.status=body.action==='apply'?'applied':body.action==='undo'?'dismissed':'accepted';item.revision+='a';item.receipt=body.action==='apply'?{synthetic:true}:null;return json(item);}
      throw new Error('Unexpected group request: '+route);
    }
    if(method!=='GET')throw new Error('Unexpected real write: '+path);
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
  const ready=()=>wait("document.querySelector('[data-source=wechat] [data-selection]')");
  await command('Page.enable');await command('Runtime.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})()`});
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1050,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:base+'/#group-messages'});await ready();
  assert.equal(await evaluate("document.querySelectorAll('[data-gid]').length"),6);
  assert.equal(await evaluate("document.querySelector('[data-gid=g2] [data-course]').value"),'c2');
  assert(await evaluate("!document.querySelector('[data-gid=old]') && !document.querySelector('[data-gid=unmatched]')"));
  await evaluate("document.querySelector('[data-source=wechat] [data-show-all]').click()");
  assert.equal(await evaluate("document.querySelectorAll('[data-gid]').length"),8);
  await evaluate("document.querySelector('[data-source=wechat] [data-show-all]').click();document.querySelector('[data-select-matched]').click();var changed=document.querySelector('[data-gid=g2] [data-course]');changed.value='c1';changed.dispatchEvent(new Event('change',{bubbles:true}))");
  assert(await evaluate("document.querySelector('[data-gid=g2] [data-selected]').checked"));
  assert(await evaluate("document.querySelector('[data-save-status]').textContent.includes('未保存') && !document.querySelector('[data-save-selection]').disabled"));
  assert.equal(await evaluate("groupCheck.calls.filter(row=>row.method==='PUT').length"),0,'Selecting groups never saves silently');
  await evaluate("groupCheck.failSave=true;document.querySelector('[data-save-selection]').click()");
  await wait("document.querySelector('[data-save-status]').textContent.includes('保存未完成')");
  assert.equal(await evaluate('groupCheck.sources.wechat.selected.length'),1);
  assert.equal(await evaluate("document.querySelector('[data-gid=g2] [data-course]').value"),'c1','Failure preserves course edits');
  await evaluate("groupCheck.delaySave=true;document.querySelector('[data-save-selection]').click()");
  await wait("document.querySelector('[data-save-selection]').disabled && document.querySelector('[data-selection-fields]').disabled");
  await wait("groupCheck.sources.wechat.selected.length===6 && document.querySelector('[data-save-status]').textContent.includes('已保存 6') && !document.querySelector('[data-selection-fields]').disabled");
  assert(await evaluate("document.querySelector('[data-save-selection]').disabled && document.querySelector('[data-reset-selection]').hidden"));
  // Invalid associations stay editable and never reach the server.
  const savedWrites=await evaluate("groupCheck.calls.filter(row=>row.method==='PUT').length");
  await evaluate("var field=document.querySelector('[data-gid=g2] [data-course]');field.value='';field.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('[data-save-selection]').click()");
  assert(await evaluate("document.querySelector('[data-save-status]').textContent.includes('未关联本学期课程')"));
  assert.equal(await evaluate("groupCheck.calls.filter(row=>row.method==='PUT').length"),savedWrites);
  await evaluate("document.querySelector('[data-refresh]').click()");
  await wait("document.querySelector('[data-gid=g2] [data-course]').value===''");
  await evaluate("document.querySelector('[data-reset-selection]').click()");
  assert.equal(await evaluate("document.querySelector('[data-gid=g2] [data-course]').value"),'c1');
  await evaluate("document.querySelector('[data-gid=g1] details').open=true;document.querySelector('[data-gid=g1] [data-messages]').click()");await wait("document.querySelector('dialog[open] .gm-message-list')");
  assert(await evaluate("document.querySelector('dialog').textContent.includes('作业1延期')"));
  await evaluate("document.querySelector('[data-close]').click();document.querySelector('[data-gid=g1] [data-senders]').click()");await wait("document.querySelector('[data-trust-form]')");
  await evaluate("document.querySelector('[name=sender][value=teacher]').checked=true;document.querySelector('[data-trust-form]').requestSubmit()");
  await evaluate("var root=document.querySelector('[data-gid=g1]');for(var attr of ['data-auto-extract','data-auto-apply']){var input=root.querySelector('['+attr+']');input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));}document.querySelector('[data-save-selection]').click()");
  assert(await evaluate("document.querySelector('[data-save-status]').textContent.includes('确认正文发送范围') && document.querySelector('.gm-sync-settings').open"));
  await evaluate("var allow=document.querySelector('[data-source=wechat] [name=allow_ai]');allow.checked=true;allow.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('[data-save-selection]').click()");
  await wait("groupCheck.sources.wechat.enabled && groupCheck.sources.wechat.selected[0].auto_apply");
  assert.deepEqual(await evaluate('groupCheck.sources.wechat.selected[0].trusted_senders'),['teacher']);
  assert.equal(await evaluate("groupCheck.calls.find(row=>row.method==='PUT').body.expected_revision"),'r1');
  await evaluate("document.querySelector('[data-refresh]').click()");await wait("document.querySelector('[data-gid=g2] [data-course]').value==='c1'");
  assert.equal(await evaluate("groupCheck.sources.wechat.selected.find(row=>row.id==='g2').course_id"),'c1','Manual course correction survives refresh');
  await evaluate("document.querySelector('[data-gid=g1] details').open=true;document.querySelector('[data-gid=g1] [data-extract]').click()");await wait("document.querySelector('[data-confirm-extract]')");
  assert(await evaluate("document.querySelector('dialog').textContent.includes('发送至当前 AI 服务')"));
  await evaluate("document.querySelector('[data-confirm-extract]').click()");await wait("document.querySelector('[data-item=item1]')");
  await evaluate("document.querySelector('[data-filter=all]').click();document.querySelector('[data-item=item1] details').open=true;document.querySelector('[data-decision=apply]').click()");
  await wait("document.querySelector('[data-decision=undo]')");assert.equal(await evaluate('groupCheck.items[0].status'),'applied');
  await evaluate("document.querySelector('[data-decision=undo]').click()");await wait("groupCheck.items[0].status==='dismissed'");
  await evaluate("var form=document.querySelector('[data-source=qq] [data-connect]');form.elements.access_token.value='synthetic-token';form.elements.consent.checked=true;form.requestSubmit()");
  await wait("document.querySelector('[data-source=qq] [data-selection]')");
  assert.equal(await evaluate("document.querySelector('[data-source=qq] [name=access_token]').value"),'');
  await evaluate("groupCheck.sources.qq.coverage={q1:{possible_gap:true}};");
  await wait("document.querySelector('[data-gid=q1] .gm-warning')?.textContent.includes('历史可能有缺口')");
  await evaluate("document.querySelector('[data-source=wechat] [data-pause]').click()");await wait("document.querySelector('[data-source=wechat] [data-source-state]').textContent==='已暂停'");
  for(const theme of ['default','observatory','star-notes','arknights']){
    await evaluate(`(async()=>{const appearance=await import('/assets/themes/appearance.js');await appearance.themeContext().select(${JSON.stringify(theme)});})()`);await ready();
    await evaluate("document.querySelector('[data-gid=g1] details').open=true;document.querySelector('[data-gid=g1] [data-extract]').click()");await wait("document.querySelector('[data-confirm-extract]')");
    assert.equal(await evaluate("document.querySelector('dialog[open]').getAttribute('aria-label')"),'整理所选群');
    await evaluate("document.querySelector('[data-confirm-extract]').click()");await wait("document.querySelector('[data-item=item1]')");
    const contrast=await evaluate(`(()=>{const button=document.querySelector('[data-decision=apply]'),style=getComputedStyle(button),ctx=document.createElement('canvas').getContext('2d');
      const light=color=>{ctx.fillStyle=color;ctx.fillRect(0,0,1,1);const c=[...ctx.getImageData(0,0,1,1).data].slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
      const a=light(style.color),b=light(style.backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);})()`);
    assert(contrast>=4.5,theme+' main-action contrast '+contrast);
    if(theme==='arknights')assert.equal(await evaluate("getComputedStyle(document.querySelector('.gm-overview')).borderTopLeftRadius"),'0px');
    await evaluate("document.querySelector('[data-filter=all]').click();document.querySelector('[data-item=item1] details').open=true");
    for(const [width,height,label] of [[1440,1050,'desktop'],[390,844,'mobile']]){
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<800});
      await evaluate('scrollTo(0,0);new Promise(r=>setTimeout(r,350))');
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),theme+' '+label+' overflow');
      await writeFile(resolve(output,theme+'-'+label+'.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
      await evaluate("for(const details of document.querySelectorAll('[data-gid] details'))details.open=false;document.querySelector('[data-gid=g2] [data-selected]').click();document.querySelector('.gm-save-bar').scrollIntoView({block:'start'});new Promise(r=>setTimeout(r,350))");
      const layout=await evaluate(`(()=>{const list=document.querySelector('[data-groups]'),bounds=list.getBoundingClientRect(),button=document.querySelector('[data-save-selection]').getBoundingClientRect();return {visible:[...list.querySelectorAll('[data-gid]')].filter(row=>{const box=row.getBoundingClientRect();return box.top>=bounds.top&&box.bottom<=Math.min(bounds.bottom,innerHeight);}).length,saveVisible:button.top>=0&&button.bottom<=innerHeight};})()`);
      assert(layout.visible>=(width>800?3:2),theme+' '+label+' shows multiple groups: '+layout.visible);
      assert(layout.saveVisible,theme+' '+label+' save action remains visible');
      await writeFile(resolve(output,theme+'-'+label+'-selection.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
      await evaluate("document.querySelector('.gm-sync-settings').scrollIntoView({block:'center'});new Promise(r=>setTimeout(r,100))");
      const sticky=await evaluate("(()=>{const button=document.querySelector('[data-save-selection]'),box=button.getBoundingClientRect(),hit=document.elementFromPoint(box.x+box.width/2,box.y+box.height/2);return {top:box.top,bottom:box.bottom,visible:box.top>=0&&box.bottom<=innerHeight,hit:hit?.className,clickable:hit?.closest('[data-save-selection]')===button,ancestors:[...function*(node){while(node){yield node;node=node.parentElement;}}(button)].map(node=>({tag:node.tagName,cls:node.className,overflow:getComputedStyle(node).overflow,position:getComputedStyle(node).position}))};})()");
      assert(sticky.visible&&sticky.clickable,theme+' '+label+' sticky save button stays clickable: '+JSON.stringify(sticky));
      await evaluate("document.querySelector('[data-reset-selection]').click()");
      await evaluate("document.querySelector('[data-items]').scrollIntoView({block:'center'});new Promise(r=>setTimeout(r,100))");
      await writeFile(resolve(output,theme+'-'+label+'-items.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
    }
  }
  await evaluate("document.querySelector('[data-gid=g1] [data-messages]').click()");await wait("document.querySelector('dialog[open]')");
  await evaluate("window.oldGroup=document.querySelector('.group-messages');location.hash='settings'");
  await wait("!document.querySelector('.group-messages')");
  const count=await evaluate('groupCheck.calls.length');await evaluate('new Promise(r=>setTimeout(r,5500))');
  assert.equal(await evaluate('groupCheck.calls.length'),count,'No polling after unmount');
  assert(await evaluate("!document.querySelector('dialog[open]') && !oldGroup.classList.contains('group-messages') && ![...document.querySelectorAll('link[rel=stylesheet]')].some(link=>link.href.includes('/group-messages/'))"));
  assert.deepEqual(errors,[]);
  console.log('PASS: compact multi-group selection, explicit save/retry/reset, draft retention, course/AI validation, trust, evidence/apply/undo, QQ token clearing, four desktop/mobile themes and lifecycle cleanup');
}finally{socket?.close();browser('close');}
