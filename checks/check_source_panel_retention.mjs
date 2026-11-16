import assert from 'node:assert/strict';
import {sourcePanel} from '../web/campus.js';

class Element extends EventTarget {
  constructor(){super();this.dataset={};this.innerHTML='';this.textContent='';this.disabled=false;}
  querySelector(){return null;}
  replaceChildren(){this.innerHTML='';this.textContent='';}
}
const selectors=['[data-sync]','[data-network]','[data-connect]','.source-state','[data-status]','[data-updated]','[data-issues]','[data-content]'];
const nodes=Object.fromEntries(selectors.map(key=>[key,new Element()]));
const container=new Element();container.querySelector=key=>nodes[key];
const life=new AbortController();let failure,renderFailure,refresh,retain=true,cleanupChecks=0,rendered=0;
const snapshot={status:'ready',account_revision:'one',data:{issues:[]},updated_at:null};
const context={signal:life.signal,ui:{toast(){}},api:async()=>{if(failure)throw failure;return snapshot;}};
const dispose=await sourcePanel(container,context,(body,_,__,reload)=>{
  if(renderFailure)throw renderFailure;
  rendered++;refresh=reload;body.textContent='unsaved preference and current reader';
},{retainContentOnError:async()=>{cleanupChecks++;if(retain instanceof Error)throw retain;return retain;}});

failure=Object.assign(new Error('Snapshot temporarily unavailable'),{status:503});
await assert.rejects(refresh,error=>error===failure);
assert.equal(nodes['[data-content]'].textContent,'unsaved preference and current reader','Confirmed ownership must preserve the existing mailbox DOM and drafts');
assert.equal(rendered,1,'Retaining content must not rebuild dialog or reader closures');
assert.match(nodes['[data-status]'].textContent,/待核实/);
assert.equal(nodes['.source-state'].open,true);
failure=undefined;await refresh();assert.equal(rendered,2,'A later successful snapshot must recover normally');

for(const status of [401,403,409]){
  const checks=cleanupChecks;retain=true;failure=Object.assign(new Error('Owner/permission changed'),{status});
  await assert.rejects(refresh,error=>error===failure);
  assert.equal(cleanupChecks,checks+1,'The module must have a chance to close old account dialogs');
  assert.equal(nodes['[data-content]'].textContent,'','An auth/owner error cannot retain private content even when a callback returns true');
  failure=undefined;await refresh();
}
for(const decision of [false,new Error('Owner cannot be confirmed')]){
  retain=decision;failure=Object.assign(new Error('Snapshot failed'),{status:502});
  await assert.rejects(refresh,error=>error===failure);
  assert.equal(nodes['[data-content]'].textContent,'','Unconfirmed ownership must clear old content');
  failure=undefined;await refresh();
}
for(const status of [503,409]){
  retain=true;const checks=cleanupChecks;
  renderFailure=Object.assign(new Error('Mailbox intelligence failed after successful snapshot'),{status});
  await assert.rejects(refresh,error=>error===renderFailure);
  assert.equal(cleanupChecks,checks+1,'Render/data failures must use the same ownership cleanup as snapshot failures');
  if(status===503){
    assert.equal(nodes['[data-content]'].textContent,'unsaved preference and current reader');
    assert.match(nodes['[data-status]'].textContent,/待核实/);
  }else assert.equal(nodes['[data-content]'].textContent,'','A render owner conflict must remove the old account content');
  renderFailure=undefined;await refresh();
}
life.abort();dispose();
console.log('source panel retention: verified-owner drafts, visible failures, recovery, auth cleanup and failed identity probes passed');
