import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {mkdir, readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import path from 'node:path';
import {randomUUID} from 'node:crypto';

const [mode, executable, project] = process.argv.slice(2);
const install = mode === 'packaged' ? path.dirname(executable) : project;
const profile = path.join(install, '.private', 'runtime', 'auth', 'synthetic-' + randomUUID());
const temp = path.join(profile, 'temp');
await mkdir(temp, {recursive:true});
const server = createServer((_request,response) => {
  response.writeHead(200, {'content-type':'text/html; charset=utf-8','set-cookie':'campus_synthetic=ok; SameSite=Lax'});
  response.end('<!doctype html><html><title>CampusMate synthetic login</title><body>Local login verification</body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url = 'http://127.0.0.1:' + server.address().port + '/';
const args = [...(mode === 'packaged' ? [] : [path.join(project,'packaging','electron')]),
  '--campus-auth','--campus-smoke','--user-data-dir=' + profile,
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--disable-gpu'];
const child = spawn(executable,args,{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,TEMP:temp,TMP:temp}});
let errors='';
child.stderr.on('data',data=>errors+=data.toString());
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function invoke(action) {
  const task=spawn(process.execPath,[path.join(project,'scripts','browser.mjs')],{cwd:project,
    windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,CAMPUS_AUTH_ELECTRON:executable}});
  let output='',error='';
  task.stdout.on('data',data=>output+=data.toString());
  task.stderr.on('data',data=>error+=data.toString());
  task.stdin.end(JSON.stringify({action,profile,url,headless:true}));
  const code=await new Promise(resolve=>task.once('exit',resolve));
  assert.equal(code,0,error);
  return JSON.parse(output);
}
try {
  let ready=false;
  for(let i=0;i<120;i++){
    if(child.exitCode!==null)throw new Error('Login shell exited: '+errors);
    try{await readFile(path.join(profile,'DevToolsActivePort'));ready=true;break;}catch{}
    await delay(250);
  }
  assert(ready,'No DevToolsActivePort: '+errors);
  assert.equal((await invoke('open')).opened,true);
  let state;
  for(let i=0;i<30;i++){
    state=await invoke('state');
    if(state.cookies.some(cookie=>cookie.name==='campus_synthetic'))break;
    await delay(100);
  }
  assert(state.cookies.some(cookie=>cookie.name==='campus_synthetic'&&cookie.value==='ok'));
  assert.equal((await invoke('close')).closed,true);
  for(let i=0;i<80&&child.exitCode===null;i++)await delay(100);
  assert.equal(child.exitCode,0,'Login shell remained running: '+errors);
  console.log('PASS: Electron login opened a local fixture, read its synthetic cookie, and exited normally');
}finally{
  server.close();
  if(child.exitCode===null)spawnSync(path.join(process.env.SystemRoot,'System32','taskkill.exe'),
    ['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
}

