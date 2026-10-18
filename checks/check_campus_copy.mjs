import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {escape} from '../web/shared.js';

const originalStorage = Object.getOwnPropertyDescriptor(globalThis,'sessionStorage');
const originalRandom = Math.random;
const data = new Map(), writes = [];
const storage = {
  getItem:key => data.get(key) ?? null,
  setItem:(key,value) => { writes.push([key,value]);data.set(key,String(value)); },
};
let serial = 0, draws = 0;
const load = async (value, target = storage) => {
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:target});
  Math.random = () => {draws++;return value;};
  return import('../web/themes/campus-copy.js?check=' + serial++);
};
try {
  const first = await load(0);
  assert.deepEqual(Object.keys(first.copyCatalog),['general','grades','deadlines','timetable','documents']);
  assert.equal(first.copyCatalog.general.length,7);
  const general = first.quoteFor();
  const count = draws;
  assert.equal(first.quoteFor('general'),general,'Switching views must retain the same cached quote');
  assert.equal(draws,count,'Cached topics do not draw again');
  const expected = '<div class="study-bilingual-quote"><p lang="en">' + escape(general.en) + '</p><p lang="zh-CN">' + escape(general.zh) + '</p></div>';
  assert.equal(first.renderStudyQuote(),expected,'Both languages render through shared HTML escaping');
  assert.ok(expected.includes('don&#39;t'),'The corpus apostrophe is escaped');
  assert.ok(!expected.includes('aria-live'),'Decoration must not announce page changes');
  const grades = first.quoteFor('grades');
  assert.equal(grades.en,'Your GPA called. We need to talk.');
  assert.equal(grades.zh,'你的GPA有话要说。');
  assert.ok(first.copyCatalog.general.every(item => !/GPA/i.test(item.en + item.zh)),'GPA belongs only to the explicitly selected grades topic');
  for (const topic of ['deadlines','timetable','documents']) {
    const item = first.quoteFor(topic);
    assert.ok(first.copyCatalog[topic].includes(item));
    assert.ok(!first.copyCatalog.general.includes(item),'Scenario pools do not leak into general');
  }
  for (const topic of ['__proto__','constructor','unknown',null,{},'Grades']) assert.equal(first.quoteFor(topic),general,'Unknown topics fall back to general');
  const refreshed = await load(.99);
  assert.equal(refreshed.quoteFor().id,general.id,'A refresh restores the session quote instead of choosing again');
  assert.equal(refreshed.quoteFor('grades').id,grades.id,'Each topic has its own remembered ID');

  data.set('campus.copy.v1.general',grades.id);
  const recovered = await load(.5);
  assert.ok(recovered.copyCatalog.general.includes(recovered.quoteFor()),'An ID from another topic must be rejected');
  assert.ok(recovered.quoteFor().id !== grades.id);
  data.set('campus.copy.v1.timetable','synthetic-invalid-id');
  assert.ok(recovered.copyCatalog.timetable.includes(recovered.quoteFor('timetable')),'Stale IDs recover to a valid topic quote');
  for (const [key,id] of writes) {
    const topic = key.slice('campus.copy.v1.'.length);
    assert.ok(Object.hasOwn(first.copyCatalog,topic));
    assert.ok(first.copyCatalog[topic].some(item => item.id === id),'Only allowlisted non-sensitive quote IDs are stored');
  }

  const blocked = {getItem:()=>{throw Error('synthetic blocked storage');},setItem:()=>{throw Error('synthetic blocked storage');}};
  const fallback = await load(.25,blocked);
  const stable = fallback.quoteFor();
  Math.random = () => .99;
  assert.equal(fallback.quoteFor(),stable,'Blocked storage retains the in-memory selection');
  assert.equal(fallback.renderStudyQuote(),fallback.renderStudyQuote(),'Blocked storage keeps rendered text stable');
  Object.defineProperty(globalThis,'sessionStorage',{configurable:true,get:()=>{throw Error('synthetic blocked getter');}});
  assert.ok(fallback.copyCatalog.documents.includes(fallback.quoteFor('documents')),'A blocked storage property is harmless');
  const source = await readFile(new URL('../web/themes/campus-copy.js',import.meta.url),'utf8');
  assert.doesNotMatch(source,/\b(?:localStorage|fetch|setTimeout|setInterval)\b/,'Copy selection has no persistent user storage, network, or timers');
  assert.ok(Object.isFrozen(first.copyCatalog) && Object.values(first.copyCatalog).every(Object.isFrozen));
  const art = await import('../web/themes/art.js');
  const home = art.renderSlot('assistant.home');
  assert.equal((home.match(/class="study-bilingual-quote"/g)||[]).length,1,'The real homepage slot contains a greeting without needing a chat draft');
  assert.ok(home.includes('lang="en"') && home.includes('lang="zh-CN"'));
  assert.ok(first.copyCatalog.general.every(item=>item.id!=='portal-somewhere'),'The random greeting must not repeat the fixed hero heading');
  console.log('campus copy: bilingual escaping, stable per-topic session IDs, scoped GPA, invalid-ID recovery and blocked-storage fallback passed');
} finally {
  Math.random = originalRandom;
  if (originalStorage) Object.defineProperty(globalThis,'sessionStorage',originalStorage);
  else delete globalThis.sessionStorage;
}
