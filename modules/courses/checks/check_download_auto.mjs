import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {courseDownloader} from '../web/download-panel.js';
import {downloadKey} from '../web/download-store.js';
import {directoryAt,installLocks,memoryStore} from './download-fixture.mjs';

const temporary=path.resolve('.codex/tmp');await fs.mkdir(temporary,{recursive:true});
const base=await fs.mkdtemp(path.join(temporary,'download-auto-'));
const revision='auto-owner',records=new Map(),roots=new Map(),storage=memoryStore(records,roots);
const course=id=>({id,code:id,title:'合成课程',term:'2026-fall',course_ids:['piazza:'+id]});
const material=id=>({id,title:id+'.pdf',updated_at:'v1',source:'piazza',course_id:'piazza:'+id,resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id='+id});
let materials=[material('A'),material('B')],calls=[],onRequest=async()=>{},onWrite=async()=>{};
const request=async url=>{
  if(url==='/api/v1/modules/piazza/snapshot')return Response.json({status:'ready',account_revision:revision,data:{materials}});
  const id=new URL(url,'http://synthetic').searchParams.get('material_id');calls.push(id);await onRequest();
  return new Response('synthetic '+id,{headers:{'content-type':'application/pdf','content-disposition':'attachment; filename="'+id+'.pdf"'}});
};
const context={signal:new AbortController().signal,ui:{toast:()=>{}}};
installLocks();
try{
  await storage.putRoot({revision,directory:directoryAt(base,{onWrite:()=>onWrite()}),token:'root',auto:true});
  const controller=courseDownloader(context,{storage,request});
  const courses=[course('A')];await controller.refresh(courses);
  assert.deepEqual(calls,['A'],'New courses follow the enabled global switch without per-course configuration');
  assert.equal(records.get(downloadKey(revision,'A')).auto,null,'New courses persist inheritance');
  courses.push(course('B'));await controller.refresh(courses);assert.deepEqual(calls,['A','B']);
  records.set(downloadKey(revision,'B'),{...records.get(downloadKey(revision,'B')),auto:false});
  roots.set(revision,{...roots.get(revision),auto:false});
  materials=materials.map(item=>({...item,updated_at:'v2'}));await controller.refresh(courses);
  assert.deepEqual(calls,['A','B'],'Global off pauses every automatic course');
  roots.set(revision,{...roots.get(revision),auto:true});await controller.refresh(courses);
  assert.deepEqual(calls,['A','B','A'],'Turning the master back on preserves individual exclusions');
  const reopened=courseDownloader(context,{storage,request});await reopened.refresh(courses);
  assert.equal(calls.length,3,'Reopening preserves inheritance and exclusions');
  records.set(downloadKey(revision,'B'),{...records.get(downloadKey(revision,'B')),auto:null});
  await reopened.refresh(courses);assert.equal(calls.at(-1),'B','Returning to follow-global resumes downloading');
  // A second tab changes the master during an HTTP response, before any disk write.
  materials=[{...material('A'),updated_at:'v3'}];
  onRequest=async()=>{roots.set(revision,{...roots.get(revision),auto:false});};
  await reopened.refresh(courses);
  const a=records.get(downloadKey(revision,'A'));
  assert.equal(a.files.A.version,JSON.stringify(['v2','A.pdf']),'Global off in another tab prevents late saves');
  assert.equal(await fs.readFile(path.join(a.directory.path,'A.pdf'),'utf8'),'synthetic A');
  onRequest=async()=>{};roots.set(revision,{...roots.get(revision),auto:true});
  onWrite=async()=>{roots.set(revision,{...roots.get(revision),auto:false});};
  await reopened.refresh(courses);
  assert.equal(records.get(a.key).files.A.version,JSON.stringify(['v2','A.pdf']),'Global off before commit aborts the staged replacement');
  assert.equal(await fs.readFile(path.join(a.directory.path,'A.pdf'),'utf8'),'synthetic A');
  onWrite=async()=>{};
  // Upgrade keeps enabled old courses enabled and disabled courses excluded.
  roots.set(revision,{...roots.get(revision),auto:undefined});
  records.set(a.key,{...records.get(a.key),auto:true});
  records.set(downloadKey(revision,'B'),{...records.get(downloadKey(revision,'B')),auto:false});
  await reopened.refresh(courses);assert.equal(roots.get(revision).auto,true);
  assert.equal(records.get(downloadKey(revision,'B')).auto,false);
  // Another controller is already queued behind an automatic batch when it is paused.
  records.set(downloadKey(revision,'B'),{...records.get(downloadKey(revision,'B')),auto:null});
  materials=[material('A'),material('B')].map(item=>({...item,updated_at:'v4'}));
  let started,release;const entered=new Promise(resolve=>{started=resolve;}),gate=new Promise(resolve=>{release=resolve;});
  onRequest=async()=>{started();await gate;};
  const beforeQueue=calls.length,active=reopened.refresh(courses);await entered;
  const queued=courseDownloader(context,{storage,request}).refresh(courses);
  roots.set(revision,{...roots.get(revision),auto:false});release();await Promise.all([active,queued]);
  assert.equal(calls.length,beforeQueue+1,'A queued tab and later courses honor the new master setting before HTTP');
  assert.equal(records.get(a.key).files.A.version,JSON.stringify(['v3','A.pdf']));
  console.log('PASS: global automatic pull, future-course inheritance, individual exclusions, reopen, master toggles, cross-tab cancellation before request/write/commit, queued batches, and legacy preferences');
}finally{assert.ok(base.startsWith(temporary+path.sep));await fs.rm(base,{recursive:true});}
