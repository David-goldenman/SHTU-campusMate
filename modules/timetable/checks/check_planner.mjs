import assert from 'node:assert/strict';
import {applyLessonPositions, compareEvents, eventGroup, isCancelledClass, lessonLayout, matchesFilter, periodsFor} from '../web/planner.js';

const lessons = [
  {id:'a',event_type:'class',period_start:10,period_end:11,at:null},
  {id:'z',event_type:'class',period_start:3,period_end:4,at:null},
  {id:'b',event_type:'class',period_start:7,period_end:9,at:null},
  {id:'overlap',event_type:'class',period_start:4,period_end:5,at:null},
];
assert(lessons.every(item => eventGroup(item) === 'class'), 'Untimed courses stay in the course grid');
assert.deepEqual([...lessons].sort(compareEvents).map(item => item.period_start),[3,4,7,10]);
const layout = lessonLayout(lessons);
assert.equal(layout.lanes,2);
assert.deepEqual(layout.items.map(({item,lane}) => [item.id,lane]),[['z',1],['overlap',2],['b',1],['a',1]]);
assert.deepEqual(lessons.map(item => item.id),['a','z','b','overlap'], 'Rendering does not reorder source data');
const calendar = {days:[{events:lessons}]};
assert.deepEqual(periodsFor(calendar,{units:13}).map(item => item.period),Array.from({length:13},(_,i) => i+1));
assert.equal(periodsFor(calendar,{}).length,11);
assert.equal(periodsFor({...calendar,periods:[{period:3,start:'10:15',end:'11:00'}]},{units:13})[2].start,'10:15');
const early = {id:'early',at:'2026-10-20T09:00:00+09:00',event_type:'activity'};
const late = {id:'late',at:'2026-10-20T08:30:00+08:00',event_type:'activity'};
assert.deepEqual([late,early].sort(compareEvents).map(item => item.id),['early','late']);
assert.equal(eventGroup(early),'timed');
assert.equal(eventGroup({...early,event_type:'deadline'}),'deadline');
assert.equal(eventGroup({...early,all_day:true}),'untimed');
assert.equal(eventGroup({...early,event_type:'exam',start_time:''}),'untimed');
assert.equal(eventGroup({...early,event_type:'class',status:'rescheduled'}),'timed');
assert.equal(eventGroup({...early,event_type:'exam',source:'local'}),'timed');
assert.equal(eventGroup({id:'tutorial',event_type:'tutorial',period_start:5,period_end:6}),'class');
console.log('PASS: legacy lesson placement, numeric ordering, overlap lanes, period clocks and event groups');

const cancelled = {...lessons[1],id:'cancelled',status:'cancel'};
const cancellationEvents = [lessons[1],cancelled,early];
const visible = cancellationEvents.filter(item => matchesFilter(item));
assert.deepEqual(visible.map(item => item.id),['z','early']);
assert.equal(lessonLayout(visible).lanes,1,'Cancelled lessons do not consume overlap lanes');
assert.deepEqual(lessonLayout(visible).items.map(({item}) => item.id),['z']);
assert.equal(lessonLayout([cancelled].filter(item => matchesFilter(item))).items.length,0,'A cancelled-only week has no course cards');
assert(!matchesFilter({...cancelled,period_start:null,period_end:null,at:early.at}),'Clock-based cancelled classes are also hidden');
assert.deepEqual(cancellationEvents.filter(item => matchesFilter(item,'study',true)).map(item => item.id),['z','cancelled']);
assert.deepEqual(cancellationEvents.filter(item => matchesFilter(item,'life',true)).map(item => item.id),['early']);
assert(matchesFilter(cancelled,'all',true),'Cancelled lessons remain available for restoration');
assert(matchesFilter({...cancelled,status:'scheduled'}),'Restored lessons appear by default');
for (const status of ['scheduled','leave','moved','rescheduled']) assert(matchesFilter({...cancelled,status}));
assert(isCancelledClass(cancelled));
assert(!isCancelledClass({...cancelled,event_type:'activity'}));
assert.equal(cancelled.status,'cancel','Visibility does not erase cancellation records');
console.log('PASS: cancelled courses hidden by default, recoverable on demand and combined with category filters');

const axis = {dataset:{periodCount:'13'},style:{setProperty(name,value) {this[name]=value;}}};
const day = {dataset:{periodCount:'13',lessonLanes:'2'},style:{setProperty(name,value) {this[name]=value;}}};
const block = {dataset:{lessonStart:'10',lessonSpan:'2',lessonLane:'2'},style:{}};
applyLessonPositions({querySelectorAll(selector) {return {'[data-period-count]':[axis,day],'[data-lesson-lanes]':[day],'[data-lesson-start]':[block]}[selector];}});
assert.equal(axis.style['--period-count'],'13');
assert.equal(day.style['--lesson-lanes'],'2');
assert.equal(block.style.gridRow,'10 / span 2');
assert.equal(block.style.gridColumn,'2');
console.log('PASS: course axis, span and overlap lane positions use CSP-compatible CSSOM properties');
