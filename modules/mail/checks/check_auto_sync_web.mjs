import assert from 'node:assert/strict';
import {watchAutoSync,autoSyncLabel} from '../web/auto-sync.js';

const realSet=globalThis.setTimeout, realClear=globalThis.clearTimeout;
let scheduled, delays=[], calls=0, reject=false, value={revision:'one',configured:true,enabled:true,state:'watching'};
const events=[], signal=new AbortController();
globalThis.setTimeout=(fn,delay)=>{scheduled=fn;delays.push(delay);return 1;};
globalThis.clearTimeout=()=>{scheduled=null;};
const tick=async()=>{const fn=scheduled;scheduled=null;assert.ok(fn);await fn();};
try {
  const stop=watchAutoSync(async(path,options)=>{
    calls++;assert.equal(path,'/auto-sync');assert.equal(options.signal,signal.signal);
    if(reject)throw Error('offline');return {...value};
  },signal.signal,(state,changed)=>events.push([state,changed]));
  await Promise.resolve();await Promise.resolve();
  assert.equal(events[0][1],true);assert.equal(delays[0],5000);
  await tick();assert.equal(events.at(-1)[1],false);
  value={...value,last_checked_at:'new check'};
  await tick();assert.equal(events.at(-1)[1],false,'Heartbeat must not redraw records');
  value.revision='two';await tick();assert.equal(events.at(-1)[1],true);
  reject=true;await tick();const count=events.length;
  await tick();assert.equal(events.length,count,'Repeated outages must not repeat UI errors');
  reject=false;await tick();assert.equal(events.at(-1)[1],true,'Reconnect refreshes once');
  signal.abort();assert.equal(scheduled,null);stop();
  const before=calls;
  watchAutoSync(()=>{throw Error('should not request');},signal.signal,()=>{});
  assert.equal(calls,before);
  let finish;
  const pendingSignal=new AbortController(), pending=[];
  watchAutoSync(()=>new Promise(resolve=>{finish=resolve;}),pendingSignal.signal,(...args)=>pending.push(args));
  assert.equal(scheduled,null,'No overlapping status requests');
  pendingSignal.abort();finish(value);await Promise.resolve();await Promise.resolve();
  assert.deepEqual(pending,[]);assert.equal(scheduled,null);
  assert.match(autoSyncLabel({...value,state:'retrying'}),/自动重试/);
  assert.match(autoSyncLabel({...value,enabled:false}),/暂停/);
} finally {
  globalThis.setTimeout=realSet;globalThis.clearTimeout=realClear;
}
console.log('mail status polling: local-only, version changes, outages, recovery, no overlap and abort cleanup passed');
