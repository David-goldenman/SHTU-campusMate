import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// A synthetic browser surface keeps carousel lifecycle checks offline and deterministic.
class TrackedTarget extends EventTarget {
  listeners = new Map();
  addEventListener(type, listener, options) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
    super.addEventListener(type, listener, options);
  }
  removeEventListener(type, listener, options) {
    this.listeners.get(type)?.delete(listener);
    super.removeEventListener(type, listener, options);
  }
  listenerCount() { return [...this.listeners.values()].reduce((total, set) => total + set.size, 0); }
}
const pendingLoads = [];
class Element extends TrackedTarget {
  constructor(tag) { super(); this.tagName=tag.toUpperCase(); this.children=[]; this.dataset={}; this.attributes=new Map(); this.hidden=false; this.style={setProperty(){},removeProperty(){}}; }
  className=''; textContent=''; disabled=false;
  classList = {
    add:(...names)=>{this.className=[...new Set([...this.className.split(/\s+/).filter(Boolean),...names])].join(' ');},
    remove:(...names)=>{this.className=this.className.split(/\s+/).filter(name=>!names.includes(name)).join(' ');},
    contains:name=>this.className.split(/\s+/).includes(name),
    toggle:(name,force)=>{const next=force===undefined?!this.classList.contains(name):force;this.classList[next?'add':'remove'](name);return next;}
  };
  append(...nodes) { for(const node of nodes){node.parentNode=this;this.children.push(node);} }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { for(const child of this.children)child.parentNode=null;this.children=[];this.append(...nodes); }
  remove() { if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(child=>child!==this);this.parentNode=null; }
  contains(node) { return this===node || this.children.some(child=>child.contains?.(node)); }
  setAttribute(key,value) { this.attributes.set(key,String(value));if(key==='class')this.className=String(value); }
  getAttribute(key) { return this.attributes.get(key)??null; }
  removeAttribute(key) { this.attributes.delete(key); }
  set src(value) { this.attributes.set('src',value);this.complete=false;pendingLoads.push({image:this,url:value}); }
  get src() { return this.getAttribute('src')||''; }
  matches(selector) { if(selector.startsWith('.'))return this.classList.contains(selector.slice(1));if(selector.startsWith('[')){const found=selector.match(/^\[([^=\]]+)(?:=["']?([^"'\]]+)["']?)?\]$/);return !!found&&this.attributes.has(found[1])&&(found[2]===undefined||this.getAttribute(found[1])===found[2]);}return this.tagName===selector.toUpperCase(); }
  querySelectorAll(selector) { return this.children.flatMap(child=>[...(child.matches?.(selector)?[child]:[]),...(child.querySelectorAll?.(selector)||[])]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0]||null; }
  closest(selector) { return this.matches(selector)?this:this.parentNode?.closest(selector)||null; }
  click() { if(!this.disabled)this.dispatchEvent(new Event('click')); }
  decode() { return Promise.resolve(); }
  getBoundingClientRect() { return {top:0,bottom:500,left:0,right:700,width:700,height:500}; }
}
const timers=new Map();let clock=0,nextTimer=1;
function schedule(callback,delay,repeat=false){const id=nextTimer++;timers.set(id,{callback,at:clock+Number(delay),delay:Number(delay),repeat});return id;}
function advance(ms){const end=clock+ms;let count=0;while(true){const next=[...timers.entries()].sort((a,b)=>a[1].at-b[1].at).find(([,timer])=>timer.at<=end);if(!next)break;assert.ok(++count<100,'timer should not spin');const [id,timer]=next;clock=timer.at;timers.delete(id);if(timer.repeat)timers.set(id,{...timer,at:clock+timer.delay});timer.callback();}clock=end;}
async function finishLoads(){while(pendingLoads.length){const {image,url}=pendingLoads.shift();if(image.src!==url)continue;image.complete=true;image.naturalWidth=720;image.dispatchEvent(new Event('load'));image.onload?.();await Promise.resolve();}await Promise.resolve();}
class FakeObserver {
  static instances=[];
  constructor(callback){this.callback=callback;this.targets=new Set();this.disconnected=false;FakeObserver.instances.push(this);}
  observe(target){this.targets.add(target);}
  unobserve(target){this.targets.delete(target);}
  disconnect(){this.disconnected=true;this.targets.clear();}
  emit(visible){this.callback([...this.targets].map(target=>({target,isIntersecting:visible,intersectionRatio:visible?1:0})));}
}
const media=new TrackedTarget();media.matches=false;
media.addListener=listener=>media.addEventListener('change',listener);
media.removeListener=listener=>media.removeEventListener('change',listener);
globalThis.window=new TrackedTarget();
globalThis.document=new TrackedTarget();document.createElement=tag=>new Element(tag);document.hidden=false;document.documentElement={dataset:{}};
globalThis.Image=class extends Element {constructor(){super('img');}};
globalThis.IntersectionObserver=FakeObserver;
globalThis.matchMedia=window.matchMedia=()=>media;
globalThis.setTimeout=window.setTimeout=(callback,delay)=>schedule(callback,delay);
globalThis.clearTimeout=window.clearTimeout=id=>timers.delete(id);
globalThis.setInterval=window.setInterval=(callback,delay)=>schedule(callback,delay,true);
globalThis.clearInterval=window.clearInterval=id=>timers.delete(id);
globalThis.requestAnimationFrame=callback=>{queueMicrotask(()=>callback(clock));return 0;};
globalThis.cancelAnimationFrame=()=>{};
const preferences={moments:{dashboard:true,timetable:true},rotation:{autoplay:true,seconds:20},reduceMotion:false};
globalThis.__campusMomentPreferences=preferences;
const source=await readFile(new URL('../web/themes/campus-moments.js',import.meta.url),'utf8');
const isolated=source.replace(/import\s*\{\s*getAppearance\s*\}\s*from\s*['"]\.\/appearance\.js['"];?/, 'const getAppearance=()=>globalThis.__campusMomentPreferences;');
assert.notEqual(isolated,source,'isolate only the appearance dependency');
const {mountCampusMoment,campusImages}=await import('data:text/javascript;base64,'+Buffer.from(isolated).toString('base64'));
const host=new Element('div'),controller=new AbortController();
const cleanup=mountCampusMoment(host,'timetable',controller.signal);
const figure=host.children[0],images=figure.querySelectorAll('img'),observer=FakeObserver.instances.at(-1);
const buttons=figure.querySelectorAll('button');
const previous=buttons.find(button=>button.getAttribute('aria-label')==='上一张图片');
const next=buttons.find(button=>button.getAttribute('aria-label')==='下一张图片');
const pause=buttons.find(button=>button.getAttribute('aria-label')==='暂停图片轮播');
const changed=()=>window.dispatchEvent(new Event('campus:appearance'));
assert.equal(images.length,2,'crossfading should have two image layers');
assert.equal(timers.size,0,'offscreen artwork must not schedule rotation');
assert.ok(images.every(image=>!image.src),'offscreen artwork should defer loading');
observer.emit(true);
assert.equal(timers.size,0,'wait for the first image before scheduling');
await finishLoads();
assert.equal(figure.dataset.slide,'0');
assert.equal(timers.size,1,'visible and loaded artwork should schedule one rotation');
advance(19999);assert.equal(figure.dataset.slide,'0');
advance(1);assert.equal(timers.size,0,'do not overlap rotation with an unfinished image');
await finishLoads();assert.equal(figure.dataset.slide,'1');assert.equal(timers.size,1);

figure.dispatchEvent(new Event('mouseenter'));
assert.equal(timers.size,0,'hover should pause');advance(60000);assert.equal(figure.dataset.slide,'1');
figure.dispatchEvent(new Event('mouseleave'));assert.equal(timers.size,1);
figure.dispatchEvent(new Event('focusin'));assert.equal(timers.size,0,'keyboard focus should pause');
const inside=new Event('focusout');Object.assign(inside,{relatedTarget:next});figure.dispatchEvent(inside);
assert.equal(timers.size,0,'moving focus between controls should remain paused');
const outside=new Event('focusout');Object.assign(outside,{relatedTarget:new Element('div')});figure.dispatchEvent(outside);
assert.equal(timers.size,1);
document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));assert.equal(timers.size,0,'hidden tabs should pause');
document.hidden=false;document.dispatchEvent(new Event('visibilitychange'));assert.equal(timers.size,1);
media.matches=true;media.dispatchEvent(new Event('change'));assert.equal(timers.size,0,'system reduced motion should stop autoplay');
media.matches=false;media.dispatchEvent(new Event('change'));assert.equal(timers.size,1);
preferences.reduceMotion=true;changed();assert.equal(timers.size,0,'manual reduced motion should stop autoplay');
preferences.reduceMotion=false;changed();assert.equal(timers.size,1);
preferences.rotation.autoplay=false;changed();assert.equal(timers.size,0,'autoplay preference should stop rotation');
next.click();await finishLoads();assert.equal(figure.dataset.slide,'2','manual next remains available');assert.equal(timers.size,0);
previous.click();await finishLoads();assert.equal(figure.dataset.slide,'1','manual previous remains available');
preferences.rotation.autoplay=true;changed();assert.equal(timers.size,0,'manual stepping stays paused until explicitly resumed');
pause.click();assert.equal(timers.size,1,'play control should resume');
pause.click();assert.equal(timers.size,0,'pause control should stop');
pause.click();assert.equal(timers.size,1);
preferences.moments.timetable=false;changed();assert.equal(figure.hidden,true);assert.equal(timers.size,0,'disabled artwork should stop rotation');
preferences.moments.timetable=true;changed();assert.equal(figure.hidden,false);assert.equal(timers.size,1);
observer.emit(false);assert.equal(timers.size,0,'scrolling away should stop rotation');
observer.emit(true);assert.equal(timers.size,1);

advance(20000);
const loading=images.find(image=>!image.complete&&image.onload);
assert.ok(loading,'next image should now be loading');
const lateLoad=loading.onload,beforeAbort=figure.dataset.slide;
controller.abort();
assert.equal(host.children.length,0,'unmounted artwork should be removed');
assert.equal(timers.size,0,'abort should clear rotation');
assert.equal(observer.disconnected,true,'abort should disconnect visibility observation');
for(const target of [window,document,media])assert.equal(target.listenerCount(),0,'abort should remove global listeners');
for(const image of images){assert.equal(image.onload,null);assert.equal(image.onerror,null);}
lateLoad();await finishLoads();
assert.equal(figure.dataset.slide,beforeAbort,'late image completion must not update an aborted carousel');
assert.equal(timers.size,0,'late completion must not restart autoplay');
cleanup();assert.equal(host.children.length,0,'cleanup should be idempotent');
const aborted=new AbortController();aborted.abort();
mountCampusMoment(host,'dashboard',aborted.signal);mountCampusMoment(host,'constructor',new AbortController().signal);
assert.equal(host.children.length,0,'invalid locations and already aborted mounts should be inert');
const failureController=new AbortController();
mountCampusMoment(host,'timetable',failureController.signal);
const failureFigure=host.children[0],failureImages=failureFigure.querySelectorAll('img');
FakeObserver.instances.at(-1).emit(true);await finishLoads();
const displayed=failureImages.find(image=>image.classList.contains('is-active'));
const displayedSource=displayed.src,displayedIndex=failureFigure.dataset.slide;
advance(20000);
const failedRequest=pendingLoads.shift();assert.ok(failedRequest);
failedRequest.image.onerror();
assert.equal(failureFigure.dataset.slide,displayedIndex,'failed replacement must keep the current image');
assert.equal(displayed.src,displayedSource);assert.equal(displayed.classList.contains('is-active'),true);
assert.ok(pendingLoads.length>0,'a failed replacement should try another image');
assert.notEqual(pendingLoads.at(-1).url,failedRequest.url,'skip the failed image');
await finishLoads();
assert.notEqual(failureFigure.dataset.slide,displayedIndex,'a successful fallback should become visible');
const stable=failureImages.find(image=>image.classList.contains('is-active'));
const stableSource=stable.src,stableIndex=failureFigure.dataset.slide;
advance(20000);
let attempts=0;
while(pendingLoads.length){
  assert.ok(++attempts<=campusImages.length,'all failing images must have a bounded retry count');
  const request=pendingLoads.shift();request.image.onerror();
  assert.equal(stable.classList.contains('is-active'),true,'keep the last usable frame during failures');
}
assert.equal(attempts,campusImages.length,'stop after one unsuccessful pass through the images');
assert.equal(failureFigure.dataset.slide,stableIndex);assert.equal(stable.src,stableSource);
assert.ok(timers.size<=1,'all failures must not accumulate rotation timers');
assert.ok([...timers.values()].every(timer=>timer.at>clock),'all failures must not create an immediate retry loop');
advance(1);assert.equal(pendingLoads.length,0,'no zero-delay request loop after all failures');
failureController.abort();assert.equal(timers.size,0);
for(const target of [window,document,media])assert.equal(target.listenerCount(),0);
console.log('campus moments: visibility-gated rotation, controls, pause preferences, bounded image-failure fallback and abort cleanup passed');
