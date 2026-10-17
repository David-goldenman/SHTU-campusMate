import assert from 'node:assert/strict';
import {createChatSession} from '../web/session.js';

function fixture() {
  const lifetime=new AbortController(),session=createChatSession();
  let emit,resolve,reject,requests=0,transportAborted=false;
  session.attach({signal:lifetime.signal,api:async(path,options)=>{
    if(path==='/conversations')return {id:'first'};
    assert.equal(path,'/chat/stream');requests++;
    emit=options.onEvent;
    return new Promise((yes,no)=>{
      resolve=yes;reject=no;
      const signal=AbortSignal.any([lifetime.signal,options.signal]);
      signal.addEventListener('abort',()=>{transportAborted=true;no(new DOMException('Stopped','AbortError'));},{once:true});
    });
  }});
  session.bindOwner('synthetic-owner');
  return {session,lifetime,get requests(){return requests;},get aborted(){return transportAborted;},
    emit:value=>emit(value),finish:()=>resolve(),fail:()=>reject(new Error('Synthetic disconnect'))};
}

const f=fixture(),page=new AbortController();
let pageUpdates=0;
f.session.subscribe(()=>pageUpdates++,page.signal);
const turn=f.session.start('first','合成问题',[]);
f.emit({type:'activity',steps:[{label:'读取讲义',status:'running'}]});
f.emit({type:'delta',text:'第一段'});
page.abort();const detachedUpdates=pageUpdates;
f.emit({type:'delta',text:'第二段'});
assert.equal(pageUpdates,detachedUpdates);
assert.equal(f.aborted,false,'Leaving a page must not abort the background request');
assert.equal(f.session.current.text,'第一段第二段');
assert.equal(f.session.current.message,'合成问题');
assert.equal(f.session.current.steps[0].label,'读取讲义');
const returnedPage=new AbortController();let completions=0;
f.session.subscribe(value=>{if(value?.status==='complete')completions++;},returnedPage.signal);
assert.equal(f.session.start('first','重复点击',[]),undefined);
f.emit({type:'complete',message:{role:'assistant',text:'完整回答'}});f.finish();await turn.finished;
assert.equal(completions,1);assert.equal(f.requests,1);
assert.equal(f.session.current.answer.text,'完整回答');
assert.equal(f.session.current.status,'complete');
f.session.forget('first');assert.equal(f.session.current,undefined);

const away=fixture(),awayPage=new AbortController();
away.session.subscribe(()=>{},awayPage.signal);
const awayTurn=away.session.start(null,'首次发问',[]);
awayPage.abort();await Promise.resolve();
assert.equal(away.session.current.conversationId,'first');
away.emit({type:'complete',message:{text:'离开时完成'}});away.finish();await awayTurn.finished;
assert.equal(away.session.current.status,'complete');
assert.equal(away.requests,1);

for(const action of ['stop','unload','owner']) {
  const next=fixture();
  next.session.drafts.set('draft','合成草稿');
  const current=next.session.start('first','可重试的问题',[]);
  if(action==='stop')next.session.stop();
  if(action==='unload')next.lifetime.abort();
  if(action==='owner')next.session.bindOwner('another-owner');
  await current.finished;assert(next.aborted);
  if(action==='stop') {
    assert.equal(next.session.current.status,'stopped');
    assert.equal(next.session.drafts.get('first'),'可重试的问题');
  } else {
    assert.equal(next.session.current,undefined);
    assert.equal(next.session.drafts.size,0,'Private drafts and partial responses must not survive owner/unload changes');
  }
}
const failed=fixture(),failedTurn=failed.session.start('first','重试问题',[]);
failed.fail();await failedTurn.finished;
assert.equal(failed.session.current.status,'error');
assert.equal(failed.session.drafts.get('first'),'重试问题');
console.log('chat session: page detach/return, background completion, single request, stop, failure, owner isolation and module unload passed');
