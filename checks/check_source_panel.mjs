import assert from 'node:assert/strict';
import {sourcePanel} from '../web/campus.js';
import {invalidateViews} from '../web/view-cache.js';

class Element extends EventTarget {
  constructor(){super();this.dataset={};this.innerHTML='';this.textContent='';this.disabled=false;}
  querySelector(){return null;}
  replaceChildren(){this.innerHTML='';this.textContent='';}
}
const elements=Object.fromEntries(['[data-sync]','[data-network]','[data-connect]','.source-state','[data-status]','[data-updated]','[data-issues]','[data-content]'].map(key=>[key,new Element()]));
const container=new Element();container.querySelector=key=>elements[key];
const life=new AbortController();let failure,refresh,rendered=0;
const snapshot={account_revision:'synthetic',status:'partial',updated_at:'2026-10-28T00:00:00Z',data:{issues:['Some sources unavailable'],text:'cached assignments'}};
const context={signal:life.signal,module:{id:'synthetic-panel',frontend_url:'/synthetic'},ui:{toast(){}},api:async path=>{
  if(path==='/view-state')return {account_revision:'synthetic'};
  if(failure)throw failure;
  return snapshot;
}};
invalidateViews();
const dispose=await sourcePanel(container,context,(body,value,_,reload)=>{rendered++;body.textContent=value.data.text;refresh=reload;},{cache:true});
failure=new Error('Synthetic network failure');
await refresh();
assert.match(elements['[data-status]'].textContent,/待核实/,'Preserved cache must be visibly marked after refresh failure');
assert.match(elements['[data-issues]'].textContent,/Synthetic network failure/);
assert.equal(elements['[data-content]'].textContent,'cached assignments');
assert.equal(elements['.source-state'].open,true,'Failure details must be visible without opening a hidden panel');
failure=Object.assign(new Error('Changed account'),{status:409});
await assert.rejects(refresh,error=>error.status===409);
assert.equal(elements['[data-content]'].textContent,'','An ownership failure must remove the previous account content');
life.abort();dispose();
const before=rendered;failure=undefined;
await refresh();assert.equal(rendered,before,'Disposed views never render again');
invalidateViews();
console.log('source panels: partial cache, visible refresh failure, ownership cleanup and disposal passed');
