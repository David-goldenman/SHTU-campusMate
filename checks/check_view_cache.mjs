import assert from 'node:assert/strict';
import {invalidateViews,readView} from '../web/view-cache.js';

const snapshot=(owner='one',text='saved')=>({account_revision:owner,data:{text}});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const turn=()=>new Promise(resolve=>setTimeout(resolve,0));
function fixture(owner='one',value=snapshot(owner),url='/module-assets/example/v1/web/index.js') {
  const calls=[],life=new AbortController();
  return {calls,life,context:{module:{id:'example',frontend_url:url},signal:life.signal,
    api:async path=>{calls.push(path);return path==='/view-state'?{account_revision:owner}:await value;}}};
}
invalidateViews();
const initial=fixture();
await readView(initial.context,'/snapshot',()=>assert.fail('No preview exists yet'));
assert.deepEqual(initial.calls,['/snapshot']);
const slow=deferred(),warm=fixture('one',slow.promise);let preview;
const pending=readView(warm.context,'/snapshot',value=>{preview=value;value.data.text='edited by renderer';});
await turn();assert.equal(preview.account_revision,'one','Cached content appears before the slow fresh response');
slow.resolve(snapshot());assert.equal((await pending).unchanged,true,'Identical fresh data leaves the existing DOM alone');
await readView(fixture().context,'/snapshot',value=>assert.equal(value.data.text,'saved','Renderers cannot mutate the cache'));

const changed=await readView(fixture('one',snapshot('one','updated')).context,'/snapshot',()=>{});
assert.equal(changed.unchanged,false);assert.equal(changed.value.data.text,'updated');
await readView(fixture('two').context,'/snapshot',()=>assert.fail('Another account must never see the old preview'));
await assert.rejects(readView(fixture('two',snapshot('one')).context,'/snapshot',()=>{}),error=>error.status===409);

invalidateViews();await readView(fixture().context,'/snapshot');
const delayed=deferred(),duringWrite=fixture('one',delayed.promise);
const stale=readView(duringWrite.context,'/snapshot',()=>{});await turn();invalidateViews();delayed.resolve(snapshot());
await assert.rejects(stale,error=>error.status===409,'A late response invalidated by a write cannot paint stale data');
const afterWrite=fixture();await readView(afterWrite.context,'/snapshot',()=>assert.fail('A write invalidated this preview'));
assert.deepEqual(afterWrite.calls,['/snapshot'],'An in-flight read cannot resurrect invalidated data');

const cancelledData=deferred(),cancelled=fixture('one',cancelledData.promise);
const abandoned=readView(cancelled.context,'/snapshot',()=>{});await turn();cancelled.life.abort();cancelledData.resolve(snapshot());
await assert.rejects(abandoned,error=>error.name==='AbortError');
const replaced=fixture('one',snapshot(),'/module-assets/example/v2/web/index.js');
await readView(replaced.context,'/snapshot',()=>assert.fail('A new module version needs fresh data'));
assert.deepEqual(replaced.calls,['/snapshot']);

const clock=Date.now;try {Date.now=()=>clock()+60001;const expired=fixture();await readView(expired.context,'/snapshot',()=>assert.fail('Expired previews must not appear'));assert.deepEqual(expired.calls,['/snapshot']);} finally {Date.now=clock;}
invalidateViews();
await assert.rejects(readView(fixture('one',Promise.reject(new Error('offline'))).context,'/snapshot'),/offline/);
const retry=fixture();await readView(retry.context,'/snapshot');assert.deepEqual(retry.calls,['/snapshot']);

const offline=fixture();
offline.context.api=async path=>{offline.calls.push(path);if(path==='/view-state')return {account_revision:'one'};throw new Error('Synthetic offline');};
const fallback=await readView(offline.context,'/snapshot',()=>{});
assert.equal(fallback.cached,true);assert.equal(fallback.value.data.text,'saved');
assert.match(fallback.error.message,/offline/);
assert.deepEqual(offline.calls,['/view-state','/snapshot','/view-state'],'Failed refresh rechecks cache ownership');
let ownerChecks=0;
offline.context.api=async path=>{if(path==='/view-state')return {account_revision:++ownerChecks===1?'one':'two'};throw new Error('Synthetic offline');};
await assert.rejects(readView(offline.context,'/snapshot',()=>{}),error=>error.status===409,'Account changes during a failed refresh cannot retain previous-account content');
await readView(fixture().context,'/snapshot');
offline.context.api=async path=>{if(path==='/view-state')return {account_revision:'one'};throw Object.assign(new Error('Synthetic denial'),{status:403});};
await assert.rejects(readView(offline.context,'/snapshot',()=>{}),error=>error.status===403,'Authorization failures never fall back');
invalidateViews();
console.log('view cache: early preview, unchanged DOM, account isolation/races, write invalidation, cancellation, module versions, expiry and failed reads passed');
