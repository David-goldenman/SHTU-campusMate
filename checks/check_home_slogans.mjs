import assert from 'node:assert/strict';
import {escape} from '../web/shared.js';
import {copyCatalog,quoteFor} from '../web/themes/campus-copy.js';

const originalStorage=Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');
const random=Math.random,data=new Map();
const storage={getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value)};
let serial=0;
const load=async(value,target=storage)=>{
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:target});
  Math.random=()=>value;
  return import('../web/themes/home-slogans.js?check='+serial++);
};
try {
  // Pair the hero with a general greeting that also exists in the slogan pool.
  Math.random=()=> (copyCatalog.general.findIndex(item=>item.en==='Too many portals. Not enough patience.')+.1)/copyCatalog.general.length;
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:storage});
  const greeting=quoteFor();
  assert.equal(greeting.en,'Too many portals. Not enough patience.');
  const first=await load(0);
  assert.equal(first.homeSlogans.length,6);
  assert.equal(new Set(first.homeSlogans.map(item=>item.lead+' '+item.accent)).size,6,'Screenshot slogans are unique');
  for(const item of first.homeSlogans)assert.ok(item.id&&item.lead&&item.accent&&item.zh);
  assert.ok(Object.isFrozen(first.homeSlogans)&&first.homeSlogans.every(Object.isFrozen));
  const initial=first.homeSlogan();
  assert.equal(first.homeSlogan(),initial,'Homepage and empty chat keep the same heading');
  assert.notEqual(initial.lead+' '+initial.accent,greeting.en,'The large and small copy cannot repeat');
  const next=await load(0);
  assert.notEqual(next.homeSlogan().id,initial.id,'A refresh avoids the previous heading even with the same random draw');
  for(const value of [0,.2,.4,.6,.8,.999]) {
    data.delete('campus.home-slogan.v1');
    const page=await load(value),item=page.homeSlogan(),html=page.renderHomeSlogan();
    assert.notEqual(item.lead+' '+item.accent,greeting.en);
    assert.ok(html.includes(escape(item.lead))&&html.includes(escape(item.accent))&&html.includes(escape(item.zh)));
    assert.ok(html.includes('lang="en"')&&html.includes('lang="zh-CN"'));
    assert.ok(!html.includes('aria-live'),'Decorative copy does not announce itself');
    assert.equal(page.renderHomeSlogan(),html,'Navigation does not change the visible wording');
  }
  const blocked={getItem:()=>{throw Error('blocked');},setItem:()=>{throw Error('blocked');}};
  const fallback=await load(.5,blocked),selected=fallback.homeSlogan();
  Math.random=()=>0;
  assert.equal(fallback.homeSlogan(),selected,'Blocked storage keeps the current page stable');
  console.log('Home slogans: six bilingual choices, refresh variation, stable page, paired-copy exclusion and blocked-storage fallback passed.');
} finally {
  Math.random=random;
  if(originalStorage)Object.defineProperty(globalThis,'sessionStorage',originalStorage);else delete globalThis.sessionStorage;
}
