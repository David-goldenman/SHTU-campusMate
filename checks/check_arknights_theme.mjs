import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:16666';
const bootstrap = await (await fetch(base + '/api/v1/bootstrap')).json();
const catalog = await (await fetch(base + '/api/v1/themes')).json();
assert(catalog.items.some(item => item.id === 'arknights'));
assert.deepEqual(catalog.errors, []);
const modules = bootstrap.modules.filter(item => item.has_frontend && item.enabled);
const output = resolve('.codex/arknights');
const profile = resolve(output, 'browser-' + process.pid);
await mkdir(profile, {recursive:true});
function browser(action) {
  const result = spawnSync(process.execPath, [resolve('scripts/browser.mjs')], {
    input:JSON.stringify({action, profile, url:'about:blank', headless:true}), encoding:'utf8', windowsHide:true,
  });
  assert.equal(result.status, 0, result.stderr);
}

function fixture(modules, categories, catalog) {
  if (!localStorage.getItem('campus.appearance.v1')) localStorage.setItem('campus.appearance.v1', JSON.stringify({theme:'arknights'}));
  const original = window.fetch.bind(window);
  const state = window.arkCheck = {modules, unexpected:[]};
  const json = value => new Response(JSON.stringify(value), {headers:{'Content-Type':'application/json'}});
  const due = hours => new Date(Date.now() + hours * 3600000).toISOString();
  const pending = [
    {id:'task:1', title:'Lab 03 · 实现流水线处理器', course_title:'计算机组成原理', due_at:due(6)},
    {id:'task:2', title:'Problem Set 04 · 向量空间与线性映射', course_title:'线性代数', due_at:due(28)},
    {id:'task:3', title:'Project 02 · 数据分析报告', course_title:'数据结构与算法', due_at:due(72)},
  ].map(item => ({...item, source:'blackboard', category:'pending', submission_status:'not_submitted', submitted:false, actionable:true, current:true, availability:'open', url:'https://example.invalid/task'}));
  window.fetch = async (url, options = {}) => {
    const target = new URL(url, location.origin);
    if (!target.pathname.startsWith('/api/v1/')) return original(url, options);
    const path = target.pathname.replace('/api/v1', '');
    if (path === '/bootstrap') return json({version:'synthetic',csrf_token:'synthetic',modules:state.modules,categories});
    if (path === '/themes') return json(catalog);
    if (path === '/ai/settings') return json({model:'deepseek-flash',enabled:false,key_saved:false});
    if (path === '/modules/academic-assistant/chat') return json({messages:[],owner:'synthetic'});
    if (path === '/modules/academic-assistant/conversations') return json({items:[],active_id:null});
    if (path === '/modules/academic-assistant/profile') return json({profile:{},academic:{}});
    if (path === '/modules/academic-assistant/presets') return json({items:[{label:'安排本周作业',prompt:'帮我安排本周作业。'},{label:'理解课程知识',prompt:'一起复习今天的课程。'},{label:'制定复习计划',prompt:'制定期中复习计划。'}]});
    if (path === '/modules/dashboard/sync') return json({status:'ready'});
    if (path === '/modules/assignments/snapshot') return json({status:'ready',data:{assignments:pending,issues:[]},pending});
    if (path === '/modules/dashboard/snapshot') {
      const date = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
      return json({status:'ready',updated_at:null,stats:{courses:8,pending:3,materials:42,ready_sources:6},pending,
        data:{metadata:{source_metadata:Object.fromEntries(['timetable','blackboard','gradescope','piazza','elrc','mail'].map(id => [id,{status:'ready'}]))},issues:[]},
        notifications:[],agenda:[{date,events:[{title:'计算机组成原理',event_type:'class',at:date+'T14:00:00+08:00',location:'教学中心 301'},{title:'线性代数 · 习题课',event_type:'class',at:date+'T16:00:00+08:00',location:'教学中心 201'}]}]});
    }
    state.unexpected.push(path);
    return new Response(JSON.stringify({detail:'Unexpected synthetic API: '+path}), {status:400});
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
  const pending = new Map(), errors = [];
  socket.addEventListener('message', ({data}) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
    const task = pending.get(message.id);
    if (!task) return;
    clearTimeout(task.timer);pending.delete(message.id);
    message.error ? task.reject(new Error(JSON.stringify(message.error))) : task.resolve(message.result);
  });
  const command = (method,params = {}) => new Promise((resolve,reject) => {
    const id = ++serial, timer = setTimeout(() => {pending.delete(id);reject(new Error('Timed out: '+method));},20000);
    pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate = expression => command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result => {
    assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
  });
  const wait = expression => evaluate(`(async()=>{for(let n=0;n<160;n++){if(${expression})return;await new Promise(resolve=>setTimeout(resolve,50));}throw new Error(${JSON.stringify('UI timeout: '+expression)});})()`);
  const capture = async (name,width,height) => {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<850});
    await evaluate('window.scrollTo(0,0);new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Viewport overflow at '+width);
    await writeFile(resolve(output,name+'.png'),Buffer.from((await command('Page.captureScreenshot')).data,'base64'));
  };
  await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
  await command('Network.setBlockedURLs',{urls:[base+'/api/v1/*']});
  const setup = await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules)},${JSON.stringify(bootstrap.categories)},${JSON.stringify(catalog)})`});
  await command('Page.navigate',{url:base+'/#dashboard'});
  await wait("document.querySelector('.ark-portrait')?.naturalWidth>0 && document.querySelector('.overview-attention') && document.querySelector('.study-messages')");
  assert.equal(await evaluate('document.documentElement.dataset.theme'),'arknights');
  assert.equal(await evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()"),'184px');
  assert.equal(await evaluate("document.querySelectorAll('h1').length"),1);
  assert.equal(await evaluate("document.querySelectorAll('.ark-tile').length"),6);
  assert(await evaluate("document.querySelector('.ark-overview').textContent.includes('Lab 03')"),'Original deadlines remain available');
  assert(await evaluate("document.querySelector('.overview-agenda').textContent.includes('教学中心 301')"),'Original agenda remains available');
  await capture('home-desktop',1440,1080);
  const clip = await evaluate("(()=>{const {x,y,width,height}=document.querySelector('.ark-terminal').getBoundingClientRect();return {x,y,width,height,scale:.6};})()");
  await writeFile(resolve(output,'theme-preview.jpg'),Buffer.from((await command('Page.captureScreenshot',{format:'jpeg',quality:85,clip})).data,'base64'));
  await capture('home-wide',1680,1050);
  await capture('home-tablet',768,1024);
  await capture('home-mobile',375,812);
  await capture('home-landscape',812,375);
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate("document.querySelector('.ark-tile-assistant').click()");
  await wait("document.querySelector('.study-chat-card.module-focused') && document.activeElement.matches('[name=message]')");
  assert.equal(await evaluate('location.hash'),'#dashboard','Reopening Home returns to the daily overview');
  assert(await evaluate("getComputedStyle(document.querySelector('.overview-card')).display==='none'"),'Focused conversation uses the full workspace');
  await capture('assistant-desktop',1440,1000);
  await capture('assistant-mobile',375,812);
  await evaluate("document.querySelector('[data-home]').click()");
  assert(await evaluate("getComputedStyle(document.querySelector('.overview-card')).display!=='none'"));
  await evaluate("location.hash='assignments'");await wait("document.querySelector('.assignment-board')");
  assert(await evaluate("!document.querySelector('.ark-terminal') && !document.querySelector('link[href*=\"/dashboard/\"]')"),'The composed overview releases its resources');
  await capture('assignments-mobile',375,812);
  await capture('assignments-desktop',1440,1000);
  await evaluate("location.hash='dashboard'");await wait("document.querySelector('.ark-terminal') && document.querySelector('.study-messages')");
  assert.equal(await evaluate("document.querySelectorAll('.ark-terminal').length"),1);
  await command('Page.removeScriptToEvaluateOnNewDocument',{identifier:setup.identifier});
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})(${JSON.stringify(modules.filter(item=>item.id!=='academic-assistant'))},${JSON.stringify(bootstrap.categories)},${JSON.stringify(catalog)})`});
  await command('Page.reload');await wait("document.querySelector('.ark-terminal') && document.querySelector('.overview-attention')");
  assert(await evaluate("!document.querySelector('.ark-tile-assistant')"),'A disabled assistant has no shortcut');
  assert.equal(await evaluate("JSON.parse(localStorage.getItem('campus.appearance.v1')).theme"),'arknights');
  await evaluate("import('/assets/themes/appearance.js').then(module=>module.themeContext().select('default'))");
  await wait("document.documentElement.dataset.theme==='default' && document.querySelector('.overview-attention')");
  assert(await evaluate("!document.querySelector('.ark-terminal') && !document.querySelector('link[href*=\"arknights/terminal.css\"]')"));
  await evaluate("import('/assets/themes/appearance.js').then(module=>module.themeContext().select('arknights'))");
  await wait("document.documentElement.dataset.theme==='arknights' && document.querySelector('.ark-terminal')");
  assert.deepEqual(await evaluate('arkCheck.unexpected'),[]);
  assert.deepEqual(errors,[]);
  console.log('PASS PRTS theme: complete overview, installed shortcuts, focused chat, remount cleanup, disabled assistant, saved selection, desktop/tablet/mobile/landscape');
} finally {
  socket?.close();browser('close');
}
