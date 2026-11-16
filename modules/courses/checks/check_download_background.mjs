import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {courseDownloader} from '../web/download-panel.js';
import {downloadKey} from '../web/download-store.js';
import {acquireDownloader} from '../web/download-service.js';
import {directoryAt,installLocks,memoryStore} from './download-fixture.mjs';

const scheduler=await import('../web/download-schedule.js').catch(()=>null);
assert.equal(typeof scheduler?.downloadSchedule,'function','Course downloads need a persistent background schedule');
const temporary=path.resolve('.codex/tmp');await fs.mkdir(temporary,{recursive:true});
const base=await fs.mkdtemp(path.join(temporary,'download-background-'));
const revision='background-owner',records=new Map(),roots=new Map(),storage=memoryStore(records,roots);
const life=new AbortController(),context={signal:life.signal,ui:{toast:()=>{}}};
const course=id=>({id,code:id,title:id,term:'2026-fall',course_ids:['piazza:'+id]});
const material=id=>({id,title:id+'.pdf',updated_at:'v1',source:'piazza',course_id:'piazza:'+id,resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id='+id});
let time=1e12,owner=revision,syncs=0,reads=0,files=0,polls=0,offline=false,blockedState,onSync=async()=>{};
let courses=[course('A')],materials=[material('A')],permission='granted',scheduled;
context.api=async endpoint=>{
  if(endpoint==='/view-state')return {account_revision:'school-owner'};
  assert.equal(endpoint,'/snapshot');return {data:{courses}};
};
const source=async()=>{reads++;return {account_revision:owner,status:blockedState || (polls-->0?'syncing':'ready'),message:blockedState?'synthetic authentication needs attention':'',data:{materials}};};
const syncSource=async()=>{syncs++;await onSync();if(offline)throw Error('synthetic offline');polls=1;};
const request=async url=>{
  if(url==='/api/v1/modules/piazza/snapshot')return Response.json(await source());
  files++;return new Response('synthetic v'+syncs,{headers:{'content-type':'application/pdf'}});
};
const options={storage,source,syncSource,now:()=>time,pause:async()=>{time+=2000;},
  schedule:fn=>{scheduled=fn;return 1;},cancel:()=>{scheduled=null;}};
installLocks();
try{
  const directory=directoryAt(base);directory.queryPermission=async()=>permission;
  directory.requestPermission=()=>{throw Error('Background must never prompt for folder access');};
  roots.set(revision,{revision,directory,token:'root',auto:false});
  const downloader=courseDownloader(context,{storage,request});
  const background=scheduler.downloadSchedule(context,downloader,options);
  await background.check();assert.equal(syncs,0);assert.equal(reads,0,'Master off performs no source requests');
  roots.set(revision,{...roots.get(revision),auto:true});
  await background.check();assert.equal(syncs,1,JSON.stringify(roots.get(revision)));assert.equal(files,1,JSON.stringify(roots.get(revision)));
  assert.equal(roots.get(revision).lastAutoState,'ready');assert.equal(records.get(downloadKey(revision,'A')).auto,null);
  const previousReads=reads;time+=14*60000;await background.check();assert.equal(reads,previousReads,'Not due checks stay local');
  time+=60000;await scheduled();assert.equal(syncs,2);assert.equal(files,1,'The scheduled tick refreshes the source but never re-fetches unchanged files');
  courses.push(course('B'),course('C'));materials.push(material('B'),material('C'));
  const bKey=downloadKey(revision,'B');records.set(bKey,{key:bKey,revision,courseId:'B',directory,auto:false,token:'B',files:{}});
  roots.set(revision,{...roots.get(revision),checkIntervalMinutes:5});
  time+=5*60000;await background.check();assert.equal(syncs,3);assert.equal(files,2,'New courses inherit while excluded courses stay off');
  assert.ok(records.get(downloadKey(revision,'C')).files.C);
  // Two background tabs and overlapping ticks share one source sync and download round.
  time+=5*60000;let enter,release;const entered=new Promise(resolve=>{enter=resolve;}),gate=new Promise(resolve=>{release=resolve;});
  onSync=async()=>{enter();await gate;};
  const running=background.check();await entered;
  const other=scheduler.downloadSchedule(context,downloader,options);await other.check();
  assert.equal(syncs,4,'A second tab never starts a duplicate source sync');
  roots.set(revision,{...roots.get(revision),auto:false});release();await running;
  assert.equal(files,2,'Turning off the master during source sync prevents file downloads');other.dispose();onSync=async()=>{};
  roots.set(revision,{...roots.get(revision),auto:true});time+=5*60000;
  owner='other-account';await background.check();assert.equal(syncs,4,'Other accounts never inherit the root');owner=revision;
  permission='prompt';await background.check();assert.equal(syncs,4);assert.equal(roots.get(revision).lastAutoState,'permission');
  permission='granted';time+=5*60000;offline=true;await background.check();assert.equal(roots.get(revision).lastAutoState,'error');
  const failedSyncs=syncs;await background.check();assert.equal(syncs,failedSyncs,'Outages wait for the configured interval');
  offline=false;time+=5*60000;await background.check();assert.equal(roots.get(revision).lastAutoState,'ready');
  const originalApi=context.api;
  for(const status of ['login_required','verification_required']) {
    blockedState=status;time+=5*60000;
    context.api=async endpoint=>{assert.notEqual(endpoint,'/snapshot','An auth-blocked source must not refresh or download cached files');return originalApi(endpoint);};
    await background.check();
    assert.equal(roots.get(revision).lastAutoState,'error','Authentication failures must not report a completed check');
    assert.match(roots.get(revision).lastAutoMessage,/synthetic authentication needs attention/);
  }
  blockedState=undefined;context.api=originalApi;
  life.abort();assert.equal(scheduled,null);const stoppedSyncs=syncs;time+=600000;await background.check();assert.equal(syncs,stoppedSyncs);
  const pageLife=new AbortController(),backgroundLife=new AbortController();
  let enterFile,finishFile,fileSignal;
  const fileEntered=new Promise(resolve=>{enterFile=resolve;}),fileGate=new Promise(resolve=>{finishFile=resolve;});
  const page=acquireDownloader({...context,signal:pageLife.signal},{storage,request:async(url,options)=>{
    if(url==='/api/v1/modules/piazza/snapshot')return Response.json({account_revision:revision,status:'ready',data:{materials:[{...material('A'),updated_at:'v2'}]}});
    fileSignal=options.signal;enterFile();await fileGate;return new Response('later PDF',{headers:{'content-type':'application/pdf'}});
  }});
  const resident=acquireDownloader({...context,signal:backgroundLife.signal});
  assert.equal(page.downloads,resident.downloads,'Foreground and background share one controller and queue');
  const downloading=page.downloads.refresh(courses);await fileEntered;pageLife.abort();
  assert.equal(fileSignal.aborted,false,'Leaving the course page keeps background downloads alive');
  backgroundLife.abort();assert.equal(fileSignal.aborted,true,'Unloading the module cancels the last shared download');
  finishFile();await downloading;
  console.log('PASS: persistent periodic downloads, default/custom intervals, local idle checks, fresh source sync, no duplicate files/rounds, future courses, individual/master controls, account/permission guards, offline retry and lifecycle cleanup');
}finally{life.abort();assert.ok(base.startsWith(temporary+path.sep));await fs.rm(base,{recursive:true});}
