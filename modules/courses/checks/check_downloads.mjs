import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {fileName, courseFiles, downloadFiles} from '../web/downloads.js';
import {downloadKey} from '../web/download-store.js';
import {courseDownloader, downloadNoticeMessage} from '../web/download-panel.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..','.codex','tmp');
await fs.mkdir(root,{recursive:true});
const folder = await fs.mkdtemp(path.join(root,'course-downloads-'));
const fixture = (id,title=id)=>({id,title,updated_at:'2026-10-01',source:'piazza',course_id:'piazza:class',resource_type:'file',download_url:'/api/v1/modules/piazza/file?material_id='+encodeURIComponent(id)});
const pdf = (name,body='%PDF-synthetic')=>new Response(body,{headers:{'content-type':'application/pdf','content-disposition':`attachment; filename*=UTF-8''${encodeURIComponent(name)}`}});
let onWrite = ()=>{};
const directory = {
  name:'Synthetic course folder',
  async queryPermission(){return 'granted';},
  async *entries(){ for(const name of await fs.readdir(folder)) yield [name,{kind:(await fs.stat(path.join(folder,name))).isFile()?'file':'directory'}]; },
  async getFileHandle(name,options={}){
    assert.equal(path.basename(name),name);
    const target=path.join(folder,name);
    try { if ((await fs.stat(target)).isDirectory()) throw new DOMException('Directory','TypeMismatchError'); }
    catch(error) { if(error.code!=='ENOENT') throw error; if(!options.create) throw new DOMException('Missing','NotFoundError'); await fs.writeFile(target,'',{flag:'wx'}); }
    return {async getFile(){const stat=await fs.stat(target);return {size:stat.size,lastModified:stat.mtimeMs};},async createWritable(){let content;return {
      async write(blob){content=Buffer.from(await blob.arrayBuffer());onWrite();},
      async close(){await fs.writeFile(target,content);},
      async abort(){},
    };}};
  },
  async removeEntry(name){await fs.unlink(path.join(folder,name));},
};
try {
  assert.equal(fileName(pdf('课件.pdf'),'title'),'课件.pdf');
  assert.equal(fileName(pdf('LAB1'),'title'),'LAB1.pdf');
  assert.equal(fileName(pdf('CON'),'title'),'_CON.pdf');
  assert.equal(fileName(pdf('../bad/name.pdf'),'title'),'.._bad_name.pdf');
  assert.equal(fileName(new Response('',{headers:{'content-type':'application/pdf','content-disposition':"attachment; filename*=UTF-8''%ZZ"}}),'Fallback'),'Fallback.pdf');
  assert.ok(fileName(pdf('x'.repeat(300)+'.pdf'),'title').length<=144);
  assert.notEqual(downloadKey('account-a','course'),downloadKey('account-b','course'));
  const a=fixture('one','Intro'),b=fixture('two','LAB1'),c=fixture('three','Tool.pdf');
  assert.deepEqual(courseFiles({data:{materials:[a,{...b,course_id:'piazza:other'},{...b,resource_type:'link'},{...b,source:'elrc'}]}},{course_ids:['piazza:class']}),[a]);
  await fs.writeFile(path.join(folder,'INTRO.pdf'),'original');
  const attempts=[],files={};
  let broken=true;
  const request=async(url,options)=>{
    const id=new URL(url,'http://local').searchParams.get('material_id');
    assert.equal(new URL(url,'http://local').searchParams.get('account_revision'),'batch-owner');
    assert.equal(options.credentials,'same-origin');assert.equal(options.redirect,'error');attempts.push(id);
    if(id==='two' && broken) return new Response(JSON.stringify({detail:'模拟来源失败'}),{status:502});
    return pdf({one:'Intro.pdf',two:'LAB1',three:'Tool.pdf'}[id]||id+'.pdf');
  };
  const run=options=>downloadFiles({directory,files,revision:'batch-owner',signal:new AbortController().signal,request,onRecord:async(id,record)=>{files[id]=record;},...options});
  const first=await run({items:[a,b]});
  assert.deepEqual(first.skipped,[{id:'one',name:'INTRO.pdf'}]);assert.equal(first.failed[0].message,'模拟来源失败');
  assert.deepEqual(attempts,['two'],'Existing files never request file bytes');
  broken=false;assert.equal((await run({items:[a,b]})).saved[0].name,'LAB1.pdf');
  const before=attempts.length;
  const restored=JSON.parse(JSON.stringify(files));
  assert.equal((await run({items:[a,b],files:restored})).skipped.length,2);assert.equal(attempts.length,before);
  assert.equal((await run({items:[a,b,c]})).saved.length,1);assert.equal(attempts.at(-1),'three');
  const b2={...b,updated_at:'2026-10-02'};
  assert.equal((await run({items:[b2]})).saved[0].name,'LAB1.pdf','Unedited managed file updates in place');
  await fs.writeFile(path.join(folder,'LAB1.pdf'),'my annotated notes');
  assert.equal((await run({items:[b2]})).skipped.length,1,'Local notes remain when remote version is unchanged');
  const b3={...b,updated_at:'2026-10-03'};
  assert.equal((await run({items:[b3]})).saved[0].name,'LAB1 (2).pdf');
  assert.equal(await fs.readFile(path.join(folder,'LAB1.pdf'),'utf8'),'my annotated notes');
  assert.equal((await run({items:[{...a,updated_at:'2026-10-02'}]})).saved[0].name,'Intro (2).pdf','Adopted files never overwritten');
  assert.equal(await fs.readFile(path.join(folder,'INTRO.pdf'),'utf8'),'original');
  await fs.unlink(path.join(folder,'Tool.pdf'));
  assert.equal((await run({items:[c]})).saved[0].name,'Tool.pdf','Missing tracked file restored');
  let calls=0;
  const changed=await run({items:[fixture('new1'),fixture('new2')],request:async()=>{calls++;return new Response(JSON.stringify({detail:'账号已切换'}),{status:409});}});
  assert.equal(calls,1);assert.equal(changed.remaining[0].id,'new2');assert.equal(changed.failed.length,1);
  const writing=new AbortController();onWrite=()=>writing.abort();
  const partial=await run({items:[fixture('partial')],signal:writing.signal});
  assert.equal(partial.cancelled,true);assert.ok(!(await fs.readdir(folder)).includes('partial.pdf'));
  const overwriting=new AbortController();onWrite=()=>overwriting.abort();
  assert.equal((await run({items:[{...c,updated_at:'next'}],signal:overwriting.signal})).cancelled,true);
  assert.equal(await fs.readFile(path.join(folder,'Tool.pdf'),'utf8'),'%PDF-synthetic','Cancelled replacement keeps original');
  onWrite=()=>{};
  const committed=await run({items:[fixture('persist-error')],onRecord:async()=>{throw Error('Storage full');}});
  assert.equal(committed.failed.length,1);assert.equal(await fs.readFile(path.join(folder,'persist-error.pdf'),'utf8'),'%PDF-synthetic','Persistence failure must not remove completed file');
  const html=await run({items:[fixture('html')],request:async()=>new Response('<html>Login</html>',{headers:{'content-type':'text/html'}})});
  assert.equal(html.saved.length,0);assert.match(html.failed[0].message,/登录页/);
  const unsafe=await run({items:[{...a,download_url:'https://other.example/file'}],request:()=>{throw Error('External URL');}});
  assert.equal(unsafe.saved.length,0);assert.match(unsafe.failed[0].message,/地址无效/);
  let removed=false;
  const denied=await run({items:[fixture('denied')],directory:{entries:async function*(){},getFileHandle:async()=>{throw new DOMException('Denied','NotAllowedError');},removeEntry:async()=>{removed=true;}}});
  assert.equal(denied.saved.length,0);assert.equal(removed,false);
  const cancelled=new AbortController();cancelled.abort();
  assert.equal((await run({items:[a,b],signal:cancelled.signal})).remaining.length,2);
  // Drive the real controller and downloader together; storage stands in for IndexedDB.
  Object.defineProperty(globalThis,'navigator',{value:{},configurable:true});
  const course={id:'course:notice',code:'EE291F',course_ids:['piazza:class']};
  const key=downloadKey('batch-owner',course.id);
  const stored=new Map([[key,{key,courseId:course.id,revision:'batch-owner',directory,auto:true,token:'folder-token',files:{}}]]);
  const storage={all:async()=>[...stored.values()],get:async key=>stored.get(key),
    update:async(key,change)=>{const next=change(stored.get(key));if(next)stored.set(key,next);}};
  let noticeMaterials=[fixture('notice-one'),fixture('notice-two')], noticeOwner='batch-owner', failFile='notice-two', abortOn='', fileCalls=0;
  let notificationAbort=new AbortController();
  const notices=[];
  const context={signal:notificationAbort.signal,ui:{toast:message=>notices.push(message)}};
  const noticeRequest=async url=>{
    if(url==='/api/v1/modules/piazza/snapshot')return Response.json({account_revision:noticeOwner,status:'ready',data:{materials:noticeMaterials}});
    fileCalls++;
    const id=new URL(url,'http://local').searchParams.get('material_id');
    if(id===abortOn)notificationAbort.abort();
    if(id===failFile)return Response.json({detail:'Synthetic missing file'},{status:502});
    return pdf(id+'.pdf');
  };
  const downloader=courseDownloader(context,{storage,request:noticeRequest});
  await downloader.refresh([course]);
  assert.equal(notices.length,1);assert.match(notices[0],/EE291F.*已保存 1 份.*Synthetic course folder.*1 份未完成/);
  assert.deepEqual(stored.get(key).lastDownload.names,['notice-one.pdf']);
  const firstNotice=stored.get(key).lastDownload;
  await downloader.refresh([course]);
  assert.equal(notices.length,1,'Skipped files and an entirely failed retry do not notify');
  assert.deepEqual(stored.get(key).lastDownload,firstNotice,'No-change checks retain the last successful pull');
  failFile='';await downloader.refresh([course]);
  assert.equal(notices.length,2);assert.deepEqual(stored.get(key).lastDownload.names,['notice-two.pdf']);
  notificationAbort.abort();
  notificationAbort=new AbortController();
  const restoredDownloader=courseDownloader({...context,signal:notificationAbort.signal},{storage,request:noticeRequest});
  const beforeRestore=fileCalls;
  await restoredDownloader.refresh([course]);
  assert.equal(notices.length,2);assert.equal(fileCalls,beforeRestore,'Reopen neither redownloads nor repeats the notification');
  noticeMaterials[0]={...noticeMaterials[0],updated_at:'2026-10-22'};
  await restoredDownloader.refresh([course]);
  assert.equal(notices.length,3,'Successfully saved updated versions notify');
  stored.set(key,{...stored.get(key),auto:false});noticeMaterials.push(fixture('notice-three'));
  await restoredDownloader.refresh([course]);assert.equal(notices.length,3,'Automatic pull disabled means no new-file notification');
  stored.set(key,{...stored.get(key),auto:true});
  const other={id:'course:other',code:'CS100',course_ids:['piazza:other']},otherKey=downloadKey('batch-owner',other.id);
  stored.set(otherKey,{key:otherKey,courseId:other.id,revision:'batch-owner',directory,auto:true,token:'other-token',files:{}});
  noticeMaterials.push({...fixture('notice-other'),course_id:'piazza:other'});
  await restoredDownloader.refresh([course,other]);
  assert.equal(notices.length,4,'Several courses produce one combined reminder');assert.match(notices[3],/EE291F.*CS100/);
  noticeOwner='changed-account';await restoredDownloader.refresh([course]);
  assert.equal(notices.length,4,'Other account does not reuse folder or reminder');
  noticeOwner='batch-owner';noticeMaterials=[fixture('stop-first'),fixture('stop-second')];abortOn='stop-second';
  await restoredDownloader.refresh([course]);
  assert.equal(notices.length,4,'No late popup after the module is unloaded');
  assert.deepEqual(stored.get(key).lastDownload.names,['stop-first.pdf'],'Completed files remain in the last-pull record after cancellation');
  assert.equal(downloadNoticeMessage([]),'');
  assert.match(downloadNoticeMessage(Array.from({length:5},(_,index)=>({course:'C'+index,directory:'Folder',count:2,remaining:0}))),/另外 2 批已保存 4 份/);
  console.log('Course downloads: skip without HTTP, restored manifests, incremental files, missing files, version updates, local edits, account guards, abort and safe cleanup passed');
  console.log('Download reminders: persisted latest pull, actual saves only, partial failures, no repeats, merged courses, preference/account isolation and unload cleanup passed');
} finally {
  assert.ok(path.resolve(folder).startsWith(root+path.sep));
  await fs.rm(folder,{recursive:true});
}
