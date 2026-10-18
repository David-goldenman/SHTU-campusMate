import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const key='campus.appearance.v1', clone=value=>structuredClone(value);
const enabledEntry='data:text/javascript,'+encodeURIComponent('export const openingLines=true;');
const catalog={items:['default','arknights','observatory','star-notes'].map(id=>({id,name:id,styles:[],views:{},backgrounds:{},...(['observatory','star-notes'].includes(id)?{entry:enabledEntry}:{})}))};
const failure=(status,message='Synthetic failure')=>Object.assign(new Error(message),{status});
function merge(value,patch){
  const result={...(value&&typeof value==='object'&&!Array.isArray(value)?value:{})};
  for(const [key,item] of Object.entries(patch))Object.defineProperty(result,key,{value:item&&typeof item==='object'&&!Array.isArray(item)?merge(result[key],item):clone(item),enumerable:true,writable:true,configurable:true});
  return result;
}
function server(value=null,revision=value?1:0){
  const api={record:{revision,value:clone(value),resetRevision:0},calls:[],reads:0,inFlight:0,maxInFlight:0,hold:null,error:null};
  api.read=async()=>{api.reads++;return clone(api.record);};
  api.save=async body=>{
    api.calls.push(clone(body));api.inFlight++;api.maxInFlight=Math.max(api.maxInFlight,api.inFlight);
    try {
      if(api.hold)await api.hold;
      if(api.error)throw api.error;
      if(body.revision!==api.record.revision)throw failure(409);
      api.record={revision:api.record.revision+1,value:merge(api.record.value,body.patch),resetRevision:api.record.resetRevision};return clone(api.record);
    } finally {api.inFlight--;}
  };
  api.reset=()=>{const revision=api.record.revision+1;api.record={revision,resetRevision:revision,value:{theme:'default',companions:{},reduceMotion:false,options:{}}};};
  return api;
}
let serial=0;
async function browser(saved,{blocked=false}={}){
  const data=new Map(saved!==undefined?[[key,typeof saved==='string'?saved:JSON.stringify(saved)]]:[]),events=new EventTarget(),doc={documentElement:{dataset:{}},querySelector:()=>null,querySelectorAll:()=>[]};
  let reloads=0;
  const activate=()=>{
    globalThis.localStorage={getItem:name=>{if(blocked)throw Error('Synthetic blocked read');return data.get(name)||null;},setItem:(name,value)=>{if(blocked)throw Error('Synthetic blocked write');data.set(name,value);}};
    globalThis.window=events;globalThis.document=doc;globalThis.location={reload:()=>reloads++};
  };
  activate();
  const ui=await import('../web/themes/appearance.js?persistence='+serial++);
  return {ui,data,events,doc,activate,reloads:()=>reloads,init:async(api,record=clone(api.record))=>{activate();return ui.initializeThemes(catalog,{record,save:api.save,read:api.read});}};
}
const existing={theme:'observatory',companions:{observatory:'male','future-theme':'robot'},reduceMotion:false,options:{arknights:{density:'compact',custom:{keep:true}},observatory:{rotation:{autoplay:true,seconds:20,custom:{keep:7}},moments:{dashboard:true,timetable:true,extra:{keep:8}}},'future-theme':{layout:['one','two'],nested:{keep:42}}}};
// Server authority applies to empty, stale and storage-disabled browser profiles.
const authoritative=server(existing);
const empty=await browser();await empty.init(authoritative);
assert.equal(empty.doc.documentElement.dataset.theme,'observatory');assert.equal(empty.doc.documentElement.dataset.openingLines,'enabled');assert.equal(authoritative.calls.length,0);
assert.equal(JSON.parse(empty.data.get(key)).theme,'observatory');assert.deepEqual(empty.ui.getAppearance().options['future-theme'],existing.options['future-theme']);assert.equal(empty.ui.getAppearance().companions['future-theme'],'robot');
const stale=await browser({theme:'default',options:{arknights:{density:'old'}}});await stale.init(authoritative);
assert.equal(stale.ui.getAppearance().theme,'observatory');assert.equal(authoritative.calls.length,0,'A stale browser must never write its whole snapshot on startup');
const blocked=await browser(undefined,{blocked:true});await blocked.init(authoritative);
assert.equal(await blocked.ui.setAppearance({reduceMotion:true}),true,'Disabled storage must not make a confirmed server save fail');
assert.equal(authoritative.record.value.reduceMotion,true);assert.deepEqual(authoritative.calls.at(-1).patch,{reduceMotion:true});
const reopened=await browser(undefined,{blocked:true});await reopened.init(authoritative);assert.equal(reopened.ui.getAppearance().reduceMotion,true);assert.equal(reopened.ui.getAppearance().theme,'observatory');

const untouched=server();for(const saved of [undefined,'null','{}','{bad',JSON.stringify({theme:'../bad'})]){
  const fresh=await browser(saved);await fresh.init(untouched);assert.equal(untouched.calls.length,0,'Empty or invalid local storage must never upload normalized Default');
}
const legacy=await browser({theme:'star-notes',moments:{dashboard:false,extra:{legacy:true}},rotation:{custom:['preserve']},options:{'future-theme':{keep:'legacy'}}});await legacy.init(untouched);
assert.equal(untouched.calls.length,1);assert.equal(untouched.record.value.theme,'star-notes');assert.equal(untouched.record.value.options.observatory.moments.dashboard,false);assert.equal(untouched.record.value.options['future-theme'].keep,'legacy');
for(const id of ['observatory','star-notes']){assert.deepEqual(untouched.record.value.options[id].moments.extra,{legacy:true});assert.deepEqual(untouched.record.value.options[id].rotation.custom,['preserve']);}
assert.deepEqual(empty.ui.getCampusPreferences('observatory').moments.extra,{keep:8});assert.deepEqual(empty.ui.getCampusPreferences('observatory').rotation.custom,{keep:7});
// A migration race adopts the server choice instead of replaying the old local snapshot.
const migrationRace=server({theme:'arknights',options:{arknights:{newest:true}}});
const migrating=await browser({theme:'observatory'});await migrating.init(migrationRace,{revision:0,value:null});
assert.equal(migrationRace.calls.length,1);assert.equal(migrationRace.reads,1);assert.equal(migrating.ui.getAppearance().theme,'arknights');assert.equal(migrating.doc.documentElement.dataset.openingLines,'hidden');assert.equal(migrationRace.record.value.options.arknights.newest,true);

// Two independent browser modules rebase only explicit patches after CAS conflicts.
const shared=server(existing),oldRecord=clone(shared.record);
const a=await browser(),b=await browser();await a.init(shared,oldRecord);await b.init(shared,oldRecord);
a.activate();assert.equal(await a.ui.setAppearance({options:{observatory:{moments:{dashboard:false}}}}),true);
b.activate();const originalPatch={options:{observatory:{rotation:{seconds:60}}}};assert.equal(await b.ui.setAppearance(originalPatch),true);
assert.deepEqual(shared.calls.at(-1).patch,originalPatch,'A retry sends only the original change');assert.equal(shared.reads,1);
assert.equal(shared.record.value.options.observatory.moments.dashboard,false);assert.equal(shared.record.value.options.observatory.rotation.seconds,60);assert.deepEqual(shared.record.value.options.arknights,existing.options.arknights);
assert.deepEqual(shared.record.value.options['future-theme'],existing.options['future-theme']);assert.equal(shared.record.value.companions['future-theme'],'robot');

const customServer=server({...existing,theme:'arknights'}),custom=await browser();await custom.init(customServer);
const preferences=custom.ui.themeContext().preferences();preferences.density='cozy';assert.equal(await custom.ui.themeContext().savePreferences(preferences),true);
assert.deepEqual(customServer.calls.at(-1).patch,{options:{arknights:{density:'cozy'}}},'Custom themes send changed fields rather than all installed theme options');assert.equal(customServer.record.value.options.arknights.custom.keep,true);

const serialServer=server(existing),serialBrowser=await browser();await serialBrowser.init(serialServer);
let release;serialServer.hold=new Promise(resolve=>{release=resolve;});
const first=serialBrowser.ui.setAppearance({options:{observatory:{rotation:{seconds:10}}}});
const second=serialBrowser.ui.setAppearance({options:{observatory:{rotation:{seconds:30}}}});
await Promise.resolve();assert.equal(serialServer.calls.length,1,'Pending requests must run serially');assert.equal(JSON.parse(serialBrowser.data.get(key)).options.observatory.rotation.seconds,20,'The local cache must not announce an uncommitted theme/preferences change');
release();assert.equal(await first,true);assert.equal(await second,true);assert.equal(serialServer.maxInFlight,1);assert.equal(serialServer.record.value.options.observatory.rotation.seconds,30);

const selectionServer=server(existing),selection=await browser();await selection.init(selectionServer);
let unlock;selectionServer.hold=new Promise(resolve=>{unlock=resolve;});const selecting=selection.ui.themeContext().select('star-notes');
await Promise.resolve();assert.equal(selection.reloads(),0,'Reload must wait for server confirmation');assert.equal(JSON.parse(selection.data.get(key)).theme,'observatory');
unlock();await selecting;assert.equal(selection.reloads(),1);assert.equal(selectionServer.record.value.theme,'star-notes');
selectionServer.hold=null;selectionServer.error=failure(503,'Synthetic offline');
assert.equal(await selection.ui.setAppearance({reduceMotion:true}),false);assert.equal(selection.ui.getAppearance().reduceMotion,false,'A failed save must not replace the confirmed setting');
await assert.rejects(selection.ui.themeContext().select('arknights'),/Synthetic offline/);assert.equal(selection.reloads(),1,'Failed saves must never claim success by reloading');

const unavailableServer=server({...existing,theme:'future-theme'}),unavailable=await browser();const message=await unavailable.init(unavailableServer);
assert.ok(message);assert.equal(unavailable.doc.documentElement.dataset.theme,'default');assert.equal(unavailable.doc.documentElement.dataset.openingLines,'hidden');assert.equal(unavailable.ui.getAppearance().theme,'future-theme');assert.equal(unavailableServer.calls.length,0,'Fallback must not save Default over an unavailable theme');

const cleared=await browser();await cleared.init(authoritative);const event=new Event('storage');Object.assign(event,{key:null,newValue:null});cleared.events.dispatchEvent(event);
await new Promise(resolve=>setImmediate(resolve));assert.equal(cleared.ui.getAppearance().theme,'observatory','Clearing browser cache must re-read the server, not reset it');
// A full reset is a CAS barrier: never replay active or queued writes from an earlier reset generation.
const resetQueueServer=server(existing),oldPage=await browser();await oldPage.init(resetQueueServer);
let finishOld;resetQueueServer.hold=new Promise(resolve=>{finishOld=resolve;});
const pendingTheme=oldPage.ui.setAppearance({theme:'star-notes'});
const pendingOptions=oldPage.ui.setAppearance({options:{observatory:{rotation:{seconds:60}},'future-theme':{oldWrite:true}}});
await Promise.resolve();assert.equal(resetQueueServer.calls.length,1);
resetQueueServer.reset();const resetRevision=resetQueueServer.record.resetRevision;finishOld();
assert.equal(await pendingTheme,false);assert.equal(await pendingOptions,false);
assert.equal(resetQueueServer.calls.length,1,'After observing reset, neither the failed active write nor queued old writes may be replayed');
assert.equal(resetQueueServer.reads,1);assert.equal(resetQueueServer.record.value.theme,'default');assert.deepEqual(resetQueueServer.record.value.options,{});
assert.equal(oldPage.ui.getAppearance().theme,'default');assert.equal(JSON.parse(oldPage.data.get(key)).theme,'default');
await new Promise(resolve=>setImmediate(resolve));assert.equal(oldPage.reloads(),1,'An old page observing reset reopens the default layout after dropping its old queue');
resetQueueServer.hold=null;assert.equal(await oldPage.ui.setAppearance({theme:'observatory'}),true,'A fresh explicit action after observing reset is valid');
assert.equal(resetQueueServer.record.value.theme,'observatory');assert.equal(resetQueueServer.record.resetRevision,resetRevision);assert.deepEqual(resetQueueServer.calls.at(-1).patch,{theme:'observatory'});
const afterResetBrowser=await browser(existing);await afterResetBrowser.init(resetQueueServer);assert.equal(afterResetBrowser.ui.getAppearance().theme,'observatory');assert.equal(resetQueueServer.calls.length,2,'Stale local cache still must not remigrate after a reset');

// A completed all-clear reloads the document; partial clears and failures keep the old refresh path.
const settingsSource=await readFile(new URL('../web/settings.js',import.meta.url),'utf8');
const start=settingsSource.indexOf('  async function dataAction('),end=settingsSource.indexOf('  async function loadBackups()',start);
assert.ok(start>=0&&end>start);
const calls=[];let clearFails=false;
const dataAction=new Function('context','api','toast','location',settingsSource.slice(start,end)+';return dataAction;')(
  {beforeClear:async()=>calls.push('before'),refresh:async()=>calls.push('refresh')},
  async()=>{calls.push('api');if(clearFails)throw Error('Synthetic clear failure');},()=>calls.push('toast'),{reload:()=>calls.push('reload')});
await dataAction('/data/clear',{},'cleared',true);assert.deepEqual(calls,['before','api','toast','reload']);
calls.length=0;await dataAction('/data/clear',{},'cleared',false);assert.deepEqual(calls,['before','api','toast','refresh']);
calls.length=0;clearFails=true;await assert.rejects(dataAction('/data/clear',{},'cleared',true),/Synthetic clear failure/);assert.deepEqual(calls,['before','api','refresh']);
assert.match(settingsSource,/scope === 'all'\);/,'Only an explicit all-clear requests a document reload');
const resetServer=server({theme:'default',companions:{},reduceMotion:false,options:{}},100),afterReset=await browser(existing);await afterReset.init(resetServer);
assert.equal(afterReset.ui.getAppearance().theme,'default');assert.equal(afterReset.doc.documentElement.dataset.openingLines,'hidden');assert.equal(resetServer.calls.length,0,'A default reset record blocks re-migrating stale browser cache');
console.log('appearance persistence: server authority, blocked storage, migration races, custom preferences, serialized CAS patches, confirmed reloads, reset-generation barriers, failures and unavailable-theme fallback passed');
