import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {courseDownloader} from '../web/download-panel.js';
import {downloadFiles,resourceVersion} from '../web/downloads.js';
import {downloadKey} from '../web/download-store.js';
import {courseFolder,withDownloadLock} from '../web/download-folders.js';
import {directoryAt,installLocks,memoryStore} from './download-fixture.mjs';

const temporary=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../../.codex/tmp');
await fs.mkdir(temporary,{recursive:true});
const root=await fs.mkdtemp(path.join(temporary,'download-layout-'));
const revision='synthetic-account',signal=new AbortController().signal;
const pdf=(text,name='Lecture1.pdf')=>new Response(text,{headers:{'content-type':'application/pdf','content-disposition':`attachment; filename="${name}"`}});
const material=id=>({id,title:'Lecture1.pdf',updated_at:'v1',source:'piazza',course_id:'piazza:'+id,resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id='+id});
const storeFor = memoryStore;
function binding(course,directory,files={}){const key=downloadKey(revision,course.id);return {key,revision,courseId:course.id,directory,auto:true,token:course.id,files};}
installLocks();
try{
  const shared=directoryAt(root),courses=['A','B'].map(id=>({id,code:id,title:'合成课程',term:'2026-fall',course_ids:['piazza:'+id]}));
  const records=new Map(courses.map(course=>{const value=binding(course,shared);return [value.key,value];})),storage=storeFor(records);
  let materials=courses.map(course=>material(course.id)),fileCalls=0,active=0,maximum=0;
  const request=async url=>{
    if(url==='/api/v1/modules/piazza/snapshot')return Response.json({account_revision:revision,status:'ready',data:{materials}});
    fileCalls++;maximum=Math.max(maximum,++active);await new Promise(resolve=>setTimeout(resolve,8));active--;
    const id=new URL(url,'http://synthetic').searchParams.get('material_id');
    return pdf('CONTENTS FOR '+id+' '+materials.find(item=>item.id===id).updated_at);
  };
  const notices=[],controllers=[1,2].map(()=>courseDownloader({signal,ui:{toast:message=>notices.push(message)}},{storage,request}));
  await Promise.all(controllers.map(controller=>controller.refresh(courses)));
  const a=records.get(downloadKey(revision,'A')),b=records.get(downloadKey(revision,'B'));
  assert.notEqual(a.directory.path,b.directory.path,'Each course owns a separate child of the chosen root');
  assert.equal(path.dirname(a.directory.path),path.join(root,'2026 年秋季'));assert.equal(path.dirname(b.directory.path),path.join(root,'2026 年秋季'));
  assert.equal(await fs.readFile(path.join(a.directory.path,'Lecture1.pdf'),'utf8'),'CONTENTS FOR A v1');
  assert.equal(await fs.readFile(path.join(b.directory.path,'Lecture1.pdf'),'utf8'),'CONTENTS FOR B v1');
  assert.equal(fileCalls,2,'Waiting tabs reload manifests instead of repeating downloads');assert.equal(maximum,1);
  assert.equal(notices.length,1,'Only actual successful saves notify');
  materials[0]={...materials[0],updated_at:'v2'};
  await Promise.all(controllers.map(controller=>controller.refresh(courses)));
  assert.deepEqual(await fs.readdir(a.directory.path),['Lecture1.pdf'],'Several versions retain one stable file');
  assert.equal(await fs.readFile(path.join(a.directory.path,'Lecture1.pdf'),'utf8'),'CONTENTS FOR A v2');
  await fs.writeFile(path.join(a.directory.path,'Lecture1.pdf'),'my handwritten annotations');
  materials[0]={...materials[0],updated_at:'v3'};
  const callsBeforeEdit=fileCalls;await controllers[0].refresh(courses);
  assert.equal(fileCalls,callsBeforeEdit,'Edited files pause before requesting new bytes');
  assert.equal(await fs.readFile(path.join(a.directory.path,'Lecture1.pdf'),'utf8'),'my handwritten annotations');
  assert.deepEqual(await fs.readdir(a.directory.path),['Lecture1.pdf']);
  // Even a matching size/timestamp cannot make changed content a managed original.
  const altered=await fs.stat(path.join(a.directory.path,'Lecture1.pdf'));
  const current=records.get(a.key);current.files.A={...current.files.A,size:altered.size,lastModified:altered.mtimeMs};
  await controllers[0].refresh(courses);assert.equal(fileCalls,callsBeforeEdit,'Saved content digest protects metadata-preserving edits');
  const renamed={...courses[0],title:'新课程名'};
  await controllers[0].refresh([renamed,courses[1]]);
  assert.equal(records.get(a.key).directory.path,a.directory.path,'Course renaming never creates another folder');
  materials.push({...material('B-other'),course_id:'piazza:B'});
  await controllers[0].refresh(courses);
  assert.deepEqual((await fs.readdir(b.directory.path)).sort(),['Lecture1 · B-other.pdf','Lecture1.pdf'].sort(),'Different resources with the same name remain distinct');
  materials[2]={...materials[2],updated_at:'v2'};await controllers[0].refresh(courses);
  assert.equal((await fs.readdir(b.directory.path)).length,2,'The second resource also keeps one latest version');
  assert.equal(await fs.readFile(path.join(b.directory.path,'Lecture1.pdf'),'utf8'),'CONTENTS FOR B v1');
  const sameLabel={...courses[0],id:'another-A',course_ids:[]};
  const sameBinding=binding(sameLabel,shared);records.set(sameBinding.key,sameBinding);
  const allocated=await withDownloadLock(signal,()=>courseFolder(sameBinding,sameLabel,storage,signal));
  assert.notEqual(allocated.directory.path,a.directory.path,'Distinct courses with equal labels stay separate');

  // Upgrade a legacy flat layout without HTTP or changing the user's own files.
  const oldRoot=path.join(root,'legacy');await fs.mkdir(oldRoot);
  const oldDirectory=directoryAt(oldRoot),oldCourse={id:'legacy',code:'EE130',title:'电磁学'};
  await fs.writeFile(path.join(oldRoot,'notes.pdf'),'original lecture');
  await fs.writeFile(path.join(oldRoot,'my-notes.pdf'),'my own annotations');
  const stat=await fs.stat(path.join(oldRoot,'notes.pdf')),item={...material('legacy'),title:'notes.pdf'};
  const old=binding(oldCourse,oldDirectory,{legacy:{name:'notes.pdf',size:stat.size,lastModified:stat.mtimeMs,version:resourceVersion(item),managed:true}});
  const oldRecords=new Map([[old.key,old]]),oldStorage=storeFor(oldRecords);
  const prepared=await withDownloadLock(signal,()=>courseFolder(old,oldCourse,oldStorage,signal));
  const migrate=options=>downloadFiles({items:[item],directory:prepared.directory,legacyDirectory:oldDirectory,files:oldRecords.get(old.key).files,revision,signal,
    request:()=>{throw Error('An unchanged file must move without HTTP');},onRecord:async(id,record)=>{oldRecords.get(old.key).files[id]=record;},...options});
  assert.equal((await migrate()).saved.length,1);
  assert.equal(await fs.readFile(path.join(prepared.directory.path,'notes.pdf'),'utf8'),'original lecture');
  assert.ok(!(await fs.readdir(oldRoot)).includes('notes.pdf'));
  assert.equal(await fs.readFile(path.join(oldRoot,'my-notes.pdf'),'utf8'),'my own annotations');
  assert.equal((await migrate()).skipped.length,1,'Reopening does not migrate or download twice');

  // Preserve legacy files that were edited or originally adopted from the user.
  for(const [id,managed] of [['edited',true],['adopted',false]]){
    const name=id+'.pdf';await fs.writeFile(path.join(oldRoot,name),'local notes');
    const meta=await fs.stat(path.join(oldRoot,name));
    const result=await migrate({items:[material(id)],files:{[id]:{name,legacy:true,managed,size:managed?1:meta.size,lastModified:meta.mtimeMs,version:'old'}}});
    assert.equal(result.preserved.length,1);assert.equal(await fs.readFile(path.join(oldRoot,name),'utf8'),'local notes');
    assert.ok(!(await fs.readdir(prepared.directory.path)).includes(name));
  }
  const claimA={id:'claim-a',title:'Claim A'},claimB={id:'claim-b',title:'Claim B'};
  await fs.writeFile(path.join(oldRoot,'shared.pdf'),'ambiguous old file');
  const sharedStat=await fs.stat(path.join(oldRoot,'shared.pdf'));
  const sharedRecord={name:'shared.pdf',managed:true,size:sharedStat.size,lastModified:sharedStat.mtimeMs,version:'old'};
  const claims=new Map([claimA,claimB].map(course=>{const value=binding(course,oldDirectory,{[course.id]:sharedRecord});return [value.key,value];})),claimStore=storeFor(claims);
  for(const course of [claimA,claimB]){
    const value=await withDownloadLock(signal,()=>courseFolder(claims.get(downloadKey(revision,course.id)),course,claimStore,signal));
    assert.equal(value.files[course.id].managed,false,'Ambiguous legacy ownership must not move or delete the original');
  }
  assert.equal(await fs.readFile(path.join(oldRoot,'shared.pdf'),'utf8'),'ambiguous old file');

  // Edits after the HTTP request, or while the stream is staged, must abort replacement.
  const raceRoot=path.join(root,'edit-races');await fs.mkdir(raceRoot);
  let duringWrite=async()=>{};const raceDirectory=directoryAt(raceRoot,{onWrite:target=>duringWrite(target)}),raceFiles={};
  const run=options=>downloadFiles({items:[material('race')],directory:raceDirectory,files:raceFiles,revision,signal,request:async()=>pdf('original'),
    onRecord:async(id,record)=>{raceFiles[id]=record;},...options});
  await run();
  let result=await run({items:[{...material('race'),updated_at:'v2'}],request:async()=>{await fs.writeFile(path.join(raceRoot,'Lecture1.pdf'),'edited during HTTP');return pdf('new');}});
  assert.equal(result.preserved.length,1);assert.equal(await fs.readFile(path.join(raceRoot,'Lecture1.pdf'),'utf8'),'edited during HTTP');
  await fs.unlink(path.join(raceRoot,'Lecture1.pdf'));await run();
  duringWrite=target=>fs.writeFile(target,'edited while staging');
  result=await run({items:[{...material('race'),updated_at:'v3'}]});
  assert.equal(result.preserved.length,1);assert.equal(await fs.readFile(path.join(raceRoot,'Lecture1.pdf'),'utf8'),'edited while staging');
  await fs.writeFile(path.join(raceRoot,'Lecture1.pdf'),'');
  result=await run({items:[{...material('race'),updated_at:'v4'}]});
  assert.equal(result.preserved.length,1);assert.equal((await fs.stat(path.join(raceRoot,'Lecture1.pdf'))).size,0,'Truncated local files count as user edits');

  // Leaving a page while waiting cancels the queued work before it can create or write files.
  let release;
  const held=withDownloadLock(signal,()=>new Promise(resolve=>{release=resolve;}));
  await new Promise(resolve=>setTimeout(resolve,0));
  const cancelled=new AbortController();let entered=false;
  const pending=withDownloadLock(cancelled.signal,()=>{entered=true;});cancelled.abort();
  await assert.rejects(pending,{name:'AbortError'});release();await held;assert.equal(entered,false);
  delete navigator.locks;await assert.rejects(withDownloadLock(signal,()=>{}),/安全的多窗口下载/);
  console.log('PASS: two tabs/two courses sharing a root, same-name resources, fresh manifests, stable latest versions, edited/empty files, content checks, legacy migration, rename/collision handling and queued cancellation');
}finally{
  assert.ok(root.startsWith(temporary+path.sep));await fs.rm(root,{recursive:true});
}
