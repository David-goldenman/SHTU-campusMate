import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {readFile, stat, writeFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

const [executable] = process.argv.slice(2);
const root = path.dirname(executable);
const data = path.join(root, '.private');
try {await stat(path.join(data,'settings.sqlite3'));throw new Error('Use a fresh installation for verification');}
catch(error){if(error.code!=='ENOENT')throw error;}
const requests=[];
const items=[{id:'late',title:'late',due_at:'2026-10-22T12:00:00+08:00'},
  {id:'early',title:'early',due_at:'2026-10-20T12:00:00+08:00'}];
const model=createServer(async (req,res)=>{
  let text='';
  for await (const part of req)text+=part;
  const body=JSON.parse(text);
  requests.push(body);
  const called=body.messages.some(message=>message.role==='tool');
  const hasPlanner=body.tools?.some(tool=>tool.function?.name==='order_deadlines');
  const delta=!called&&hasPlanner ? {tool_calls:[{index:0,id:'synthetic-call',type:'function',
    function:{name:'order_deadlines',arguments:JSON.stringify({items})}}]} : {content:'安装包验收完成'};
  const finish=!called&&hasPlanner?'tool_calls':'stop';
  res.writeHead(200,{'content-type':'text/event-stream'});
  for(const [change,reason] of [[delta,null],[{},finish]]){
    res.write('data: '+JSON.stringify({id:'synthetic',object:'chat.completion.chunk',model:body.model,
      choices:[{index:0,delta:change,finish_reason:reason}]})+'\n\n');
  }
  res.end('data: [DONE]\n\n');
});
await new Promise(resolve=>model.listen(0,'127.0.0.1',resolve));
const windows=process.env.SystemRoot;
const env={...process.env,PATH:[path.join(windows,'System32'),path.join(windows,'System32','WindowsPowerShell','v1.0'),windows].join(path.delimiter)};
delete env.PYTHONPATH; delete env.PYTHONHOME; delete env.ELECTRON_RUN_AS_NODE;
const child=spawn(executable,['--campus-smoke','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0'],{
  cwd:root,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
let errors='';
child.stderr.on('data',part=>errors+=part.toString());
let state;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(route,method='GET',body){
  const headers=body?{'content-type':'application/json','X-Framework-Token':state.csrf}:{};
  const response=await fetch(state.origin+route,{method,headers,body:body?JSON.stringify(body):undefined,
    signal:AbortSignal.timeout(180000)});
  const text=await response.text();
  assert(response.ok,route+': '+text);
  return JSON.parse(text);
}
async function closeApp(){
  const task=spawn(path.join(root,'resources','runtime','node','node.exe'),[path.join(root,'resources','backend','scripts','browser.mjs')],{
    env:{...env,CAMPUS_AUTH_ELECTRON:executable},windowsHide:true,stdio:['pipe','pipe','pipe']});
  let error='';
  task.stderr.on('data',part=>error+=part.toString());
  task.stdin.end(JSON.stringify({action:'close',profile:path.join(data,'electron')}));
  assert.equal(await new Promise(resolve=>task.once('exit',resolve)),0,error);
  for(let n=0;n<200&&child.exitCode===null;n++)await delay(100);
  assert.equal(child.exitCode,0,'Desktop did not exit normally: '+errors);
}
try{
  for(let n=0;n<240;n++){
    if(child.exitCode!==null)throw new Error('Desktop exited: '+errors);
    try{
      const value=JSON.parse(await readFile(path.join(data,'desktop.json'),'utf8'));
      if(value.pid===child.pid){state=value;break;}
    }catch{}
    await delay(250);
  }
  assert(state,'Desktop startup timed out: '+errors);
  state.origin='http://127.0.0.1:'+state.port;
  const bootstrap=await api('/api/v1/bootstrap');
  state.csrf=bootstrap.csrf_token;
  assert.equal(bootstrap.modules.length,19);
  assert(bootstrap.modules.every(module=>module.status==='ready'),JSON.stringify(bootstrap.modules.map(m=>({id:m.id,status:m.status}))));
  for(const name of ['dataDirectory','userData','sessionData','logs','temp']){
    const relative=path.relative(root,state[name]);
    assert(!relative.startsWith('..')&&!path.isAbsolute(relative),name+' escaped the installation');
  }
  await api('/api/v1/ai/settings','PUT',{enabled:true,provider:'release-check',display_name:'Synthetic release check',
    custom:true,model:'synthetic',protocol:'openai-completions',base_url:'http://127.0.0.1:'+model.address().port+'/v1',api_key:'synthetic-only'});
  const result=await api('/api/v1/ai/run','POST',{prompt:'整理合成作业',context:JSON.stringify(items),plugins:['deadlines']});
  assert.equal(result.content,'安装包验收完成');
  assert(result.tools.length>=1&&result.tools.every(tool=>!tool.is_error),JSON.stringify(result));
  const output=requests.flatMap(request=>request.messages).find(message=>message.role==='tool')?.content;
  assert(output&&output.indexOf('early')<output.indexOf('late'),'Planner tool did not sort the synthetic records');
  await api('/api/v1/ai/providers/release-check','DELETE',{});
  delete state.csrf;
  await writeFile(path.join(data,'logs','verification.json'),JSON.stringify({
    application:'CampusMate',sourceCommit:JSON.parse((await readFile(path.join(root,'resources','release.json'),'utf8')).replace(/^\uFEFF/,'' )).source_commit,
    modules:bootstrap.modules.length,modelRequests:requests.length,tools:result.tools,
    source:'local synthetic model',globalDeveloperToolsOnPath:false,paths:state},null,2));
  await closeApp();
  try{await fetch(state.origin+'/api/v1/health',{signal:AbortSignal.timeout(1000)});assert.fail('Backend is still listening');}catch(error){if(error.code==='ERR_ASSERTION')throw error;}
  console.log('PASS: packaged desktop, 19 modules, isolated paths, offline local plugin installation, synthetic Harness tool and normal shutdown');
}finally{
  model.close();
  if(child.exitCode===null)spawnSync(path.join(windows,'System32','taskkill.exe'),['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
}

