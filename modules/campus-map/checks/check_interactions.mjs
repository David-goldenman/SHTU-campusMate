import assert from 'node:assert/strict';
import {bindMapGestures,zoomView} from '../web/interactions.js';

const initial={x:100,y:200,w:1000,h:800},projection={width:1000,height:800};
const close=(a,b)=>assert(Math.abs(a-b)<1e-9,`${a} != ${b}`);
const anchor={x:350,y:760};
for(const factor of [.5,2,.001,100]) {
  const next=zoomView(initial,projection,factor,anchor);
  close((anchor.x-initial.x)/initial.w,(anchor.x-next.x)/next.w);
  close((anchor.y-initial.y)/initial.h,(anchor.y-next.y)/next.h);
  assert(next.w>=200&&next.w<=1200);close(next.h/next.w,.8);
}
assert.deepEqual(zoomView(initial,projection,.5),{x:350,y:400,w:500,h:400});
const minimum=zoomView(initial,projection,.001,anchor);
assert.deepEqual(zoomView(minimum,projection,.1,anchor),minimum);

// A small EventTarget SVG fixture exercises event sequences without a browser/account.
function fixture() {
  const svg=new EventTarget(),window=new EventTarget(),controller=new AbortController();
  let view={...initial};const updates=[],taps=[],zooms=[],classes=new Set(),captured=new Set();
  svg.classList={add:name=>classes.add(name),remove:name=>classes.delete(name)};
  svg.ownerDocument={defaultView:window};svg.focus=()=>{};
  svg.setPointerCapture=id=>captured.add(id);svg.hasPointerCapture=id=>captured.has(id);
  svg.releasePointerCapture=id=>captured.delete(id);
  svg.getBoundingClientRect=()=>({width:1000,height:400}); // SVG meet: two map units per px.
  svg.getScreenCTM=()=>({inverse:()=>({})});
  svg.createSVGPoint=()=>({x:0,y:0,matrixTransform(){return {x:this.x*2+view.x-500,y:this.y*2+view.y};}});
  let building='building-a',road='road-a';
  svg.closest=selector=>({dataset:selector==='[data-building]'?{building}:{maintRoad:road}});
  const cancel=bindMapGestures(svg,{signal:controller.signal,getView:()=>view,
    setView:next=>{view=next;updates.push(next);},onTap:tap=>taps.push(tap),
    onZoom:(factor,point)=>{zooms.push({factor,point});view=zoomView(view,projection,factor,point);}});
  const send=(type,options={})=>{
    const event=new Event(type,{cancelable:true});
    Object.assign(event,{pointerId:1,button:0,buttons:1,isPrimary:true,pointerType:'mouse',clientX:400,clientY:100,deltaMode:0,deltaY:0,...options});
    svg.dispatchEvent(event);return event;
  };
  return {svg,window,controller,updates,taps,zooms,classes,captured,cancel,send,get view(){return view;},
    changeTarget(){building='building-b';road='road-b';}};
}
{
  const f=fixture();f.send('pointerdown');f.send('pointermove',{clientX:402});f.changeTarget();
  f.send('pointerup',{clientX:402});
  assert.deepEqual(f.view,initial);assert.equal(f.updates.length,0);assert.equal(f.taps.length,1);
  assert.equal(f.taps[0].building,'building-a');assert.equal(f.taps[0].road,'road-a');assert.equal(f.captured.size,0);
  f.controller.abort();
}
{
  const f=fixture();f.send('pointerdown');f.send('pointermove',{clientX:450,clientY:120});
  assert.deepEqual(f.view,{...initial,x:0,y:160});assert(f.classes.has('is-dragging'));
  f.send('pointermove');f.send('pointerup'); // Moving back to the origin is still a drag.
  assert.equal(f.taps.length,0);assert.equal(f.classes.size,0);
  f.send('pointerdown');f.send('pointerup');assert.equal(f.taps.length,1);
  f.controller.abort();
}
{
  const f=fixture();f.send('pointerdown');f.send('pointerup',{clientX:1500,clientY:900});
  assert.equal(f.taps.length,0);assert.equal(f.captured.size,0);assert(f.view.x<initial.x);
  f.controller.abort();
}
for(const end of ['pointercancel','lostpointercapture','blur','abort','cancel','missing-buttons']) {
  const f=fixture();f.send('pointerdown');f.send('pointermove',{clientX:450});
  if(end==='blur')f.window.dispatchEvent(new Event('blur'));
  else if(end==='abort')f.controller.abort();
  else if(end==='cancel')f.cancel();
  else if(end==='missing-buttons')f.send('pointermove',{buttons:0});
  else f.send(end);
  const stopped={...f.view};f.send('pointermove',{clientX:490});f.send('pointerup');
  assert.deepEqual(f.view,stopped,end);assert.equal(f.taps.length,0,end);assert.equal(f.classes.size,0,end);assert.equal(f.captured.size,0,end);
  if(end!=='abort'){f.send('pointerdown');f.send('pointerup');assert.equal(f.taps.length,1,end);}
  else {f.send('wheel',{deltaY:100});assert.equal(f.zooms.length,0);}
  f.controller.abort();
}
{
  const f=fixture();
  f.send('pointerdown',{button:2});f.send('pointerup');
  f.send('pointerdown',{isPrimary:false,pointerId:2});f.send('pointerup',{pointerId:2});
  assert.equal(f.taps.length,0);
  f.send('pointerdown',{pointerType:'touch'});
  f.send('pointerdown',{pointerId:2});f.send('pointermove',{pointerId:2,clientX:600});
  f.send('pointercancel',{pointerId:2});f.send('pointerup',{pointerType:'touch'});
  assert.deepEqual(f.view,initial);assert.equal(f.taps.length,1);f.controller.abort();
}
for(const [deltaMode,deltaY,pixels] of [[0,16,16],[1,1,16],[2,.04,16],[0,-1000,-240]]) {
  const f=fixture();const event=f.send('wheel',{deltaMode,deltaY});
  assert(event.defaultPrevented);close(f.zooms[0].factor,Math.exp(pixels*.002));
  const {point}=f.zooms[0];close((point.x-initial.x)/initial.w,(point.x-f.view.x)/f.view.w);
  close((point.y-initial.y)/initial.h,(point.y-f.view.y)/f.view.h);f.controller.abort();
}
{
  const f=fixture();assert.equal(f.send('wheel',{deltaY:0,deltaX:10}).defaultPrevented,false);
  f.send('pointerdown');f.send('wheel',{deltaY:-100});const zoomed={...f.view};
  f.send('pointermove',{clientX:450});f.send('pointerup');
  assert.deepEqual(f.view,zoomed);assert.equal(f.taps.length,0);f.controller.abort();
}
console.log('campus-map: click jitter, drag/cancel/capture cleanup, primary pointers, zoom limits and wheel anchors passed');
