import assert from 'node:assert/strict';
import {useStyle, escape, api, moduleApi, setToken, confirmDialog} from '../web/shared.js';
import {renderMarkdown} from '../web/markdown.js';
import {sendOnEnter, fitComposer} from '../modules/academic-assistant/web/composer.js';
import {cleanupAll} from '../web/lifecycle.js';
import {navigationChanged} from '../web/navigation.js';
import {renderNetwork} from '../web/network.js';
import {submissionLabel} from '../web/campus.js';
import {bindSyncNetwork, syncNetworkReports} from '../web/sync-network.js';
import {schoolServices} from '../web/school-login.js';

const navigationState={csrf_token:'synthetic',categories:[{id:'courses',label:'Courses'}],modules:[{id:'courses',enabled:true,status:'ready',revision:'one',frontend_url:'/module-assets/courses/one/web/index.js',runtime:{active_requests:0}}]};
const countersChanged=structuredClone(navigationState);countersChanged.modules[0].runtime={active_requests:3,last_request:{duration_ms:900}};
assert.equal(navigationChanged(navigationState,countersChanged),false,'Background request activity must not remount a page');
for(const change of [
  value=>{value.csrf_token='restarted';},
  value=>{value.modules[0].enabled=false;},
  value=>{value.modules[0].status='error';},
  value=>{value.modules[0].frontend_url='/module-assets/courses/two/web/index.js';},
  value=>{value.modules[0].background_url='/module-assets/courses/one/web/background.js';},
  value=>{value.categories[0].label='Updated courses';},
  value=>{value.modules=[];},
]) {
  const updated=structuredClone(navigationState);change(updated);
  assert(navigationChanged(navigationState,updated),'Changed navigation or service identity must be reconciled');
}
console.log('navigation: ignore runtime counters; reconcile module changes, categories and restarted service identity');

const schoolMarkup = schoolServices({connection:{status:'complete'},services:[
  {id:'blackboard',status:'ready'}, {id:'elrc',status:'verification_required',message:'<script>synthetic</script>'}
]});
assert(schoolMarkup.includes('已连接 1 / 4') && schoolMarkup.includes('data-school-verify="elrc"'));
assert(!schoolMarkup.includes('<script>') && schoolMarkup.includes('&lt;script&gt;'));
assert(schoolServices({connection:{status:'waiting_for_login'}}).includes('完成后自动连接'));

assert.equal(submissionLabel({submitted:null}), '提交状态待核实');
assert.equal(submissionLabel({submitted:false,exempt:true}), '已豁免');
assert.equal(submissionLabel({submitted:true,submission_status:'needs_grading'}), '已提交，待评分');
assert.match(submissionLabel({submitted:true,submission_stale:true}), /已提交.*缓存.*待核实/);
assert.equal(submissionLabel({submitted:null,submission_status:'__proto__'}), '提交状态待核实');

const inlineReport={name:'<img onerror=x>',checked_at:'2026-10-17T09:30:00Z',diagnosis:{code:'campus_route',confidence:'suspected',title:'校园路径',message:'无法确定 VPN 状态',actions:['<script>']}};
assert(syncNetworkReports([inlineReport]).includes('&lt;img'));
assert(!syncNetworkReports([inlineReport]).includes('<script>'));
const inlineHost={hidden:true,innerHTML:'',addEventListener(){},replaceChildren(){this.innerHTML='';}};
const inlineLife=new AbortController(), pending=[];
const inline=bindSyncNetwork(inlineHost,{signal:inlineLife.signal,services:{auth:{explainNetwork:failures=>new Promise(resolve=>pending.push({failures,resolve}))}}});
inline.update([{id:'first'}]);inline.update([{id:'first'}]);assert.equal(pending.length,1);
inline.update([{id:'second'}]);assert.equal(pending.length,2);
pending[0].resolve({reports:[inlineReport]});await Promise.resolve();assert(inlineHost.innerHTML.includes('正在自动'));
pending[1].resolve({reports:[inlineReport]});await Promise.resolve();assert(inlineHost.innerHTML.includes('重新检测网络'));
inline.update([]);assert(inlineHost.hidden&&!inlineHost.innerHTML);
inline.update([{id:'third'}]);inlineLife.abort();const beforeAbort=inlineHost.innerHTML;
pending[2].resolve({reports:[inlineReport]});await Promise.resolve();assert.equal(inlineHost.innerHTML,beforeAbort);
console.log('sync diagnostics UI: automatic single request, escaped evidence, stale replies, successful recovery and unmount cancellation passed');

const networkMarkup=renderNetwork({summary:'0 / 1 个入口响应',scope:'仅检测入口',proxy_configured:true,services:[{
  name:'<script>untrusted</script>',host:'school.example',port:443,dns:{status:'ok',addresses:['10.15.1.1']},
  direct:{reachable:false,status:'timeout',elapsed_ms:12},proxy:null,
  diagnosis:{code:'campus_route',confidence:'suspected',title:'疑似校园网络或 VPN 路径问题',message:'无法确认 VPN 状态',actions:['校外先连接校园 VPN']},
}]});
assert(!networkMarkup.includes('<script>') && networkMarkup.includes('&lt;script&gt;'));
assert(networkMarkup.includes('暂不可达')&&networkMarkup.includes('可能原因依据')&&networkMarkup.includes('无法确认 VPN 状态'));

for (const [keys, sends, prevents] of [
  [{},1,1], [{ctrlKey:true},1,1], [{metaKey:true},1,1],
  [{shiftKey:true},0,0], [{isComposing:true},0,0], [{keyCode:229},0,0],
  [{repeat:true},0,1], [{key:'a'},0,0],
]) {
  let submitted = 0, prevented = 0;
  const event = {key:'Enter', ...keys, preventDefault() {prevented++;}};
  sendOnEnter(event, {requestSubmit() {submitted++;}});
  assert.equal(submitted, sends, JSON.stringify(keys));
  assert.equal(prevented, prevents, JSON.stringify(keys));
}
console.log('chat composer: Enter/Ctrl/Meta sends once; Shift, IME and held keys do not submit');
const composer = {style:{}, scrollHeight:0};
for (const [contentHeight, expected] of [[20,'52px'],[110,'110px'],[600,'200px'],[30,'52px']]) {
  composer.scrollHeight=contentHeight;fitComposer(composer);assert.equal(composer.style.height,expected);
}
console.log('chat composer: grows with multiline input, caps long drafts and shrinks after clearing');

const mounted = new Set();
globalThis.document = {
  createElement:() => ({remove() { mounted.delete(this); }}),
  head:{append(node) { mounted.add(node); }},
};
const first = new AbortController(), sibling = new AbortController();
const cleanup = useStyle('/first.css',first.signal);
useStyle('/sibling.css',sibling.signal);
assert.equal(mounted.size,2);
first.abort();
assert.equal(mounted.size,1);
cleanup(); cleanup();
assert.equal(mounted.size,1);
sibling.abort();
assert.equal(mounted.size,0);
useStyle('/already-aborted.css',first.signal);
assert.equal(mounted.size,0);
assert.equal(escape('<img src=x onerror="alert(1)">'),'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
console.log('frontend: independent abort cleanup, idempotent style removal, pre-aborted mounts and untrusted navigation text passed');

const priorDocument = globalThis.document, priorNode = globalThis.Node;
let currentDialog;
class DialogNode extends EventTarget {
  open = false;
  children = [];
  querySelector() {return new DialogNode();}
  get lastElementChild() {return this.children.at(-1) || this;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children = nodes;}
  replaceWith(node) {currentDialog = node;}
  setAttribute() {}
  showModal() {this.open = true;}
  close(value = '') {
    if (!this.open) return;
    this.open = false;this.returnValue = value;
    setTimeout(()=>this.dispatchEvent(new Event('close')),0);
  }
}
try {
  currentDialog = new DialogNode();
  globalThis.Node = DialogNode;
  globalThis.document = {querySelector:()=>currentDialog,createElement:()=>new DialogNode()};
  for (const value of ['cancel','confirm']) {
    currentDialog.showModal();
    let settled = false;
    const confirmation = confirmDialog('删除安排','删除合成日程？').then(value=>{settled=true;return value;});
    await new Promise(resolve=>setTimeout(resolve,10));
    assert(currentDialog.open && !settled,'Replacing an open dialog must not settle its new confirmation');
    currentDialog.close(value);
    assert.equal(await confirmation,value === 'confirm');
  }
} finally {
  globalThis.document = priorDocument;
  if (priorNode === undefined) delete globalThis.Node;else globalThis.Node = priorNode;
}
console.log('confirmation: queued close events preserve explicit cancel and confirm decisions');

const markdown = renderMarkdown('## 复习计划\n\n**重点**\n\n- 读课件\n\n| 时间 | 内容 |\n| --- | --- |\n| 周一 | 向量 |\n\n```js\nconst n = 1;\n```\n\n<script>bad()</script>\n\n[bad](javascript:alert(1)) ![remote](https://example.edu/tracker.png)');
for (const tag of ['<h2>','<strong>','<ul>','<table>','<pre>']) assert(markdown.includes(tag));
assert(!markdown.includes('<script>') && !markdown.includes('href="javascript:') && !markdown.includes('<img'));
assert.match(renderMarkdown('[资料](https://example.edu)'),/rel="noopener noreferrer"/);

globalThis.location = {origin:'http://127.0.0.1:16666'};
const events = [{type:'delta',text:'中文边界 🌲'},{type:'complete',message:{text:'完成'}}];
const bytes = new TextEncoder().encode(events.map(value=>JSON.stringify(value)).join('\n'));
setToken('synthetic-csrf');
let aborted = false;
globalThis.fetch = async (url,options) => {
  assert.equal(url.origin,location.origin);assert.equal(options.headers.get('X-Framework-Token'),'synthetic-csrf');
  options.signal?.addEventListener('abort',()=>{aborted=true;},{once:true});
  return new Response(new ReadableStream({start(controller) {
    for (let index=0;index<bytes.length;index+=3) controller.enqueue(bytes.slice(index,index+3));
    controller.close();
  }}),{headers:{'Content-Type':'application/x-ndjson'}});
};
const chunks = [], life = new AbortController(), request = new AbortController();
await moduleApi('study',life.signal)('/chat/stream',{method:'POST',body:{message:'合成'},signal:request.signal,onEvent:value=>chunks.push(value)});
assert.deepEqual(chunks,events);request.abort();assert(aborted);
await assert.rejects(()=>api('/test',{onEvent:()=>{throw new Error('synthetic stream error');}}),/synthetic stream error/);
console.log('frontend: safe Markdown, tables/code, UTF-8 streamed boundaries, CSRF and composed cancellation passed');

let cleaned=false;
const cleanupResults=await cleanupAll([()=>{throw new Error('synthetic cleanup failure');},()=>new Promise(()=>{}),()=>{cleaned=true;}],10);
assert(cleaned);assert.deepEqual(cleanupResults.map(value=>value.status),['rejected','rejected','fulfilled']);
for(const [response,expected] of [[new Response('<html>private diagnostic</html>',{status:500}),/500/],[new Response('malformed'),/无法读取/]]) {
  globalThis.fetch=async()=>response;
  await assert.rejects(()=>api('/test'),error=>expected.test(error.message)&&!error.message.includes('private diagnostic'));
}
globalThis.fetch=async()=>new Response(null,{status:204});assert.equal(await api('/test'),null);
globalThis.fetch=async()=>{throw new TypeError('fetch failed');};
await assert.rejects(()=>api('/test'),/无法连接本地服务/);
globalThis.fetch=async(url,options)=>new Promise((resolve,reject)=>{
  if(options.signal.aborted)reject(options.signal.reason);
  else options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});
});
await assert.rejects(()=>api('/test',{timeoutMs:10}),error=>error.name==='TimeoutError');
const cancelled=new AbortController();cancelled.abort();
await assert.rejects(()=>api('/test',{signal:cancelled.signal}),error=>error.name==='AbortError');
globalThis.fetch=async(url,options)=>new Response(new ReadableStream({start(controller){
  options.signal.addEventListener('abort',()=>controller.error(options.signal.reason),{once:true});
}}),{headers:{'Content-Type':'application/x-ndjson'}});
await assert.rejects(()=>api('/test',{onEvent:()=>{},timeoutMs:200,idleTimeoutMs:10}),error=>error.name==='TimeoutError');
globalThis.fetch=async()=>new Response(new ReadableStream({start(controller){
  for(let index=1;index<=4;index++)setTimeout(()=>{
    controller.enqueue(new TextEncoder().encode('{"type":"activity"}\n'));
    if(index===4)controller.close();
  },index*20);
}}),{headers:{'Content-Type':'application/x-ndjson'}});
const activity=[];
await api('/test',{onEvent:event=>activity.push(event),timeoutMs:300,idleTimeoutMs:60});
assert.equal(activity.length,4,'Stream progress renews only the inactivity deadline');
console.log('frontend resilience: cleanup failures/hangs isolated, safe non-JSON errors, connection failures, deadlines, idle streams and manual abort passed');

globalThis.fetch=async()=>Response.json({detail:[{loc:['body','port'],msg:'Must be a valid port',type:'value_error'}],code:'invalid_fields',request_id:'synthetic-id',action:'检查字段后重试。'},{status:422});
await assert.rejects(()=>api('/test'),error=>error.status===422&&error.code==='invalid_fields'&&error.requestId==='synthetic-id'&&error.message.includes('port：Must be a valid port')&&error.message.includes('检查字段后重试。'));
console.log('frontend errors: field locations, action and support ID retained');
globalThis.fetch=async()=>Response.json({detail:{message:'ELRC 网络请求失败，已保留缓存。',network_failure:{id:'synthetic',target:'elrc'}}},{status:502});
await assert.rejects(()=>api('/test'),error=>error.message.includes('ELRC 网络请求失败')&&error.details.network_failure.target==='elrc');
