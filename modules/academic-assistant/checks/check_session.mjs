import assert from 'node:assert/strict';
import {createChatSession} from '../web/session.js';
import * as composer from '../web/composer.js';
const {composeMessage}=composer;

function fixture() {
  const lifetime=new AbortController(),session=createChatSession();
  let emit,resolve,reject,requests=0,transportAborted=false;
  const sent=[];
  session.attach({signal:lifetime.signal,api:async(path,options)=>{
    if(path==='/conversations')return {id:'first'};
    assert.equal(path,'/chat/stream');requests++;sent.push(options.body.message);
    emit=options.onEvent;
    return new Promise((yes,no)=>{
      resolve=yes;reject=no;
      const signal=AbortSignal.any([lifetime.signal,options.signal]);
      signal.addEventListener('abort',()=>{transportAborted=true;no(new DOMException('Stopped','AbortError'));},{once:true});
    });
  }});
  session.bindOwner('synthetic-owner');
  return {session,lifetime,sent,get requests(){return requests;},get aborted(){return transportAborted;},
    emit:value=>emit(value),finish:()=>resolve(),fail:()=>reject(new Error('Synthetic disconnect'))};
}

const f=fixture(),page=new AbortController();
assert(f.session.composerModes instanceof Map,'Session keeps selected modes independently from user drafts');
let pageUpdates=0;
f.session.subscribe(()=>pageUpdates++,page.signal);
const turn=f.session.start('first','合成问题',[]);
f.emit({type:'activity',steps:[{label:'读取讲义',status:'running'}]});
f.emit({type:'delta',text:'第一段'});
f.emit({type:'file-approval',approval:{id:'file-one',path:'C:/synthetic.txt'}});
page.abort();const detachedUpdates=pageUpdates;
f.emit({type:'delta',text:'第二段'});
assert.equal(pageUpdates,detachedUpdates);
assert.equal(f.aborted,false,'Leaving a page must not abort the background request');
assert.equal(f.session.current.text,'第一段第二段');
assert.equal(f.session.current.message,'合成问题');
assert.equal(f.session.current.approvals[0].path,'C:/synthetic.txt','Approval survives page navigation');
f.emit({type:'file-approval-closed',id:'file-one'});
assert.equal(f.session.current.approvals.length,0);
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
  next.session.composerModes.set('draft','explain');
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
    assert.equal(next.session.composerModes.size,0,'Selected modes must not survive owner/unload changes');
  }
}
const failed=fixture(),failedTurn=failed.session.start('first','重试问题',[]);
failed.fail();await failedTurn.finished;
assert.equal(failed.session.current.status,'error');
assert.equal(failed.session.drafts.get('first'),'重试问题');
console.log('chat session: page detach/return, background completion, single request, stop, failure, owner isolation and module unload passed');
const edited=fixture(),editedTurn=edited.session.start('first','添加合成安排',[]);
edited.emit({type:'change',change:{applied:true,action:'create',after:{title:'合成安排'}}});
edited.session.stop();await editedTurn.finished;
assert.equal(edited.session.current.changes.length,1);
assert(edited.session.current.error.includes('已保存'));
console.log('chat session: completed writes remain visible when generation is stopped');

const original='  我写的题目与要求\n请保留这里的换行。  ';
const explain={id:'explain',label:'讲懂知识',prompt:'从直觉和例子讲解。'},quiz={id:'quiz',label:'自测',prompt:'一次只问一道题。'};
const selected=fixture();
const selectedTurn=selected.session.start(null,composeMessage(original,explain),[],{text:original,modeId:explain.id});
await Promise.resolve();
assert.equal(selected.session.current.composer.text,original);
assert.equal(selected.session.composerModes.get('first'),explain.id,'New conversation receives the selected mode');
assert.equal(selected.session.composerModes.has(''),false,'Unassigned mode must not leak into another new conversation');
selected.fail();await selectedTurn.finished;
assert.equal(selected.session.drafts.get('first'),original,'Failure restores the exact user draft, not the composed request');
const retried=selected.session.start('first',composeMessage(selected.session.drafts.get('first'),quiz),[],{text:original,modeId:quiz.id});
assert(!selected.sent.at(-1).includes(explain.prompt));assert(selected.sent.at(-1).includes(quiz.prompt));
assert.equal(selected.sent.at(-1).split(quiz.prompt).length-1,1,'Retry adds the current mode only once');
selected.session.stop();await retried.finished;
assert.equal(selected.session.drafts.get('first'),original);
assert.equal(selected.session.composerModes.get('first'),quiz.id);
selected.session.drafts.set('second','另一个对话的草稿');selected.session.composerModes.set('second',explain.id);
const completed=selected.session.start('first',composeMessage(original,quiz),[],{text:original,modeId:quiz.id});
selected.emit({type:'complete',message:{text:'已完成'}});selected.finish();await completed.finished;
assert(!selected.session.drafts.has('first'));assert.equal(selected.session.composerModes.get('first'),quiz.id);
assert.equal(selected.session.drafts.get('second'),'另一个对话的草稿');assert.equal(selected.session.composerModes.get('second'),explain.id);
selected.lifetime.abort();assert.equal(selected.session.composerModes.size,0);
console.log('chat composer state: exact draft recovery, mode-only replacement on retry, new conversation, successful send, conversation isolation and unload passed');
