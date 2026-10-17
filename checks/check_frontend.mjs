import assert from 'node:assert/strict';
import {useStyle, escape, api, moduleApi, setToken} from '../web/shared.js';
import {renderMarkdown} from '../web/markdown.js';
import {sendOnEnter} from '../modules/academic-assistant/web/composer.js';

for (const keys of [{}, {ctrlKey:true}, {metaKey:true}, {shiftKey:true}, {isComposing:true}, {keyCode:229}, {repeat:true}, {key:'a'}]) {
  let submitted = 0, prevented = 0;
  const event = {key:'Enter', ...keys, preventDefault() {prevented++;}};
  sendOnEnter(event, {requestSubmit() {submitted++;}});
  const enter = event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229;
  assert.equal(submitted, enter && !event.repeat ? 1 : 0, JSON.stringify(keys));
  assert.equal(prevented, enter ? 1 : 0, JSON.stringify(keys));
}
console.log('chat composer: Enter/Ctrl/Meta sends once; Shift, IME and held keys do not submit');

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
