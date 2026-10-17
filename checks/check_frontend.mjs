import assert from 'node:assert/strict';
import {useStyle, escape, api, moduleApi, setToken} from '../web/shared.js';
import {renderMarkdown} from '../web/markdown.js';
import {sendOnEnter, fitComposer} from '../modules/academic-assistant/web/composer.js';
import {cleanupAll} from '../web/lifecycle.js';
import {renderNetwork} from '../web/network.js';

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
