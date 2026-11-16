import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {courseDownloader} from '../web/download-panel.js';
import {downloadKey} from '../web/download-store.js';
import {savedRoot,withDownloadLock} from '../web/download-folders.js';
import {directoryAt,installLocks,memoryStore} from './download-fixture.mjs';

const temporary=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../.codex/tmp');
await fs.mkdir(temporary,{recursive:true});
const base=await fs.mkdtemp(path.join(temporary,'global-downloads-'));
const revision='owner',signal=new AbortController().signal,records=new Map(),roots=new Map(),storage=memoryStore(records,roots);
const course=(id,term)=>({id,code:id,title:'合成课程',term,course_ids:['piazza:'+id]});
const material=id=>({id,title:'Lecture.pdf',updated_at:'v1',source:'piazza',course_id:'piazza:'+id,resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id='+id});
const notices=[],context={signal,ui:{toast:message=>notices.push(message)}};
let owner=revision,fileCalls=0;
const request=async url=>{
  if(url==='/api/v1/modules/piazza/snapshot')return Response.json({status:'ready',account_revision:owner,data:{materials:[material('A'),material('B')]}});
  fileCalls++;return new Response('synthetic '+new URL(url,'http://synthetic').searchParams.get('material_id'),{headers:{'content-type':'application/pdf','content-disposition':'attachment; filename="Lecture.pdf"'}});
};
installLocks();
try{
  const first=path.join(base,'first'),second=path.join(base,'second');await fs.mkdir(first);await fs.mkdir(second);
  const root={revision,directory:directoryAt(first),token:'selected-once'};await storage.putRoot(root);
  const controller=courseDownloader(context,{storage,request});
  const courses=[course('A','2026-fall'),course('B','2026-spring'),course('C','')];
  await controller.refresh(courses);
  assert.equal(fileCalls,0,'A shared root creates all folders without enabling automatic downloads');
  assert.equal(roots.get(revision).auto,false,'Existing roots with no enabled course default the new master switch off');
  for(const [id,semester] of [['A','2026 年秋季'],['B','2026 年春季'],['C','学期待确认']]){
    const saved=records.get(downloadKey(revision,id));assert.equal(saved.relativePath,semester+' / '+id+' · 合成课程');
    assert.equal(saved.rootToken,'selected-once');assert.equal(saved.auto,null);assert.ok((await fs.stat(saved.directory.path)).isDirectory());
  }
  courses.push(course('D','2027-spring'));await controller.refresh(courses);
  const added=records.get(downloadKey(revision,'D'));assert.ok(added.directory.path.startsWith(first+path.sep));
  assert.equal(path.basename(path.dirname(added.directory.path)),'2027 年春季');
  assert.equal(roots.size,1);assert.equal(roots.get(revision).token,'selected-once');
  const originalA=records.get(downloadKey(revision,'A'));originalA.auto=true;
  records.get(downloadKey(revision,'B')).auto=false;
  roots.set(revision,{...roots.get(revision),auto:true});
  await controller.refresh(courses);assert.equal(fileCalls,1);
  const restarted=courseDownloader(context,{storage,request});await restarted.refresh(courses);assert.equal(fileCalls,1,'A new controller restores the root and manifests without a second selection');
  // Correcting a semester relocates owned files locally and removes the old empty course folder.
  const oldAPath=originalA.directory.path;courses[0]={...courses[0],term:'2026-spring'};
  await restarted.refresh(courses);
  const movedA=records.get(originalA.key);assert.notEqual(movedA.directory.path,oldAPath);
  assert.equal(await fs.readFile(path.join(movedA.directory.path,'Lecture.pdf'),'utf8'),'synthetic A');
  await assert.rejects(fs.stat(oldAPath),{code:'ENOENT'});assert.equal(fileCalls,1);
  await fs.writeFile(path.join(movedA.directory.path,'Lecture.pdf'),'my notes');
  records.get(downloadKey(revision,'B')).auto=true;await restarted.refresh(courses);assert.equal(fileCalls,2);
  const oldBPath=records.get(downloadKey(revision,'B')).directory.path;
  await storage.putRoot({revision,directory:directoryAt(second),token:'changed-root',auto:true});
  await restarted.refresh(courses);
  const newA=records.get(originalA.key),newB=records.get(downloadKey(revision,'B'));
  assert.ok(newA.directory.path.startsWith(second+path.sep));assert.ok(newB.directory.path.startsWith(second+path.sep));
  assert.equal(await fs.readFile(path.join(movedA.directory.path,'Lecture.pdf'),'utf8'),'my notes','Switching roots keeps local edits at their original location');
  assert.equal((await fs.readdir(newA.directory.path)).length,0,'No replacement or duplicate is created for edited files');
  assert.equal(await fs.readFile(path.join(newB.directory.path,'Lecture.pdf'),'utf8'),'synthetic B');
  await assert.rejects(fs.stat(oldBPath),{code:'ENOENT'});assert.equal(fileCalls,2,'Unedited files move to the shared root without HTTP');
  assert.equal(newA.auto,true);assert.equal(records.get(added.key).auto,null,'Course inheritance survives changes to the shared root');
  courses.push(course('E','2027-fall'));await restarted.refresh(courses);
  assert.ok(records.get(downloadKey(revision,'E')).directory.path.startsWith(second+path.sep),'Later courses inherit the latest root');
  owner='other-owner';await restarted.refresh(courses);
  assert.equal(roots.has(owner),false);assert.equal(records.has(downloadKey(owner,'A')),false);assert.equal(fileCalls,2,'Another account never inherits directory access or manifests');

  const ambiguous=new Map();
  for(const [id,directory] of [['one',directoryAt(first)],['two',directoryAt(second)]]){
    const key=downloadKey(revision,id);ambiguous.set(key,{key,revision,courseId:id,directory,token:id,auto:false,files:{}});
  }
  const legacyStore=memoryStore(ambiguous);
  assert.equal(await withDownloadLock(signal,()=>savedRoot(revision,legacyStore,signal)),undefined,'Several legacy roots require an explicit choice');
  for(const binding of ambiguous.values())binding.auto=true;
  let unconfiguredCalls=0;
  await courseDownloader(context,{storage:legacyStore,request:async url=>{
    if(url==='/api/v1/modules/piazza/snapshot')return Response.json({status:'ready',account_revision:revision,data:{materials:[material('one'),material('two')]}});
    unconfiguredCalls++;return new Response('synthetic');
  }}).refresh([course('one','2026-fall'),course('two','2026-fall')]);
  assert.equal(unconfiguredCalls,0,'Without a unified root, old bindings cannot bypass the displayed disabled master');
  ambiguous.delete(downloadKey(revision,'two'));
  const promoted=await withDownloadLock(signal,()=>savedRoot(revision,legacyStore,signal));
  assert.equal(promoted.directory.path,first,'One legacy root is reused without choosing it again');
  const oldChildPath=path.join(first,'old-course-folder');await fs.mkdir(oldChildPath);
  await fs.writeFile(path.join(oldChildPath,'Lecture.pdf'),'old course download');
  await fs.writeFile(path.join(first,'personal.pdf'),'personal notes');
  const oldMeta=await fs.stat(path.join(oldChildPath,'Lecture.pdf')),personalMeta=await fs.stat(path.join(first,'personal.pdf'));
  const legacyCourse=course('legacy','2025-fall'),legacyKey=downloadKey(revision,'legacy'),legacyItem=material('legacy');
  const oldBinding={key:legacyKey,revision,courseId:'legacy',token:'v1-token',auto:true,layout:'course-v1',directory:directoryAt(oldChildPath),parentDirectory:directoryAt(first),legacyDirectory:directoryAt(first),
    files:{legacy:{name:'Lecture.pdf',managed:true,size:oldMeta.size,lastModified:oldMeta.mtimeMs,version:JSON.stringify(['v1','Lecture.pdf'])},
      personal:{name:'personal.pdf',managed:false,legacy:true,size:personalMeta.size,lastModified:personalMeta.mtimeMs,version:'old'}}};
  const mixedRecords=new Map([[legacyKey,oldBinding]]),mixedStore=memoryStore(mixedRecords);
  const mixedController=courseDownloader(context,{storage:mixedStore,request:async url=>{
    if(url==='/api/v1/modules/piazza/snapshot')return Response.json({status:'ready',account_revision:revision,data:{materials:[legacyItem,{...material('personal'),course_id:'piazza:legacy'}]}});
    throw Error('Legacy course files migrate locally');
  }});
  await mixedController.refresh([legacyCourse]);
  const upgraded=mixedRecords.get(legacyKey);
  assert.equal(upgraded.layout,'semester-v2');assert.equal(upgraded.auto,true);assert.equal(upgraded.token,'v1-token');
  assert.equal(await fs.readFile(path.join(upgraded.directory.path,'Lecture.pdf'),'utf8'),'old course download');
  assert.equal(await fs.readFile(path.join(first,'personal.pdf'),'utf8'),'personal notes');
  await assert.rejects(fs.stat(oldChildPath),{code:'ENOENT'});
  console.log('PASS: one saved root for all/current/future courses, semester folders, unknown terms, reopen, semester correction, root changes, local moves, edited files, independent auto switches, account isolation and legacy root promotion');
}finally{assert.ok(base.startsWith(temporary+path.sep));await fs.rm(base,{recursive:true});}
