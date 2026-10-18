import assert from 'node:assert/strict';
import {buildDayPlan,nextStop,smartMarkers,transferText,dayAt,clockAt} from '../web/journey.js';
import {journeyMarkup} from '../web/journey-view.js';

const buildings=['甲楼','乙楼','丙楼'].map((name,id)=>({id:String(id),name,aliases:[name]}));
const day='2026-10-21',at=clock=>day+'T'+clock+':00+08:00';
const routeFor=(a,b)=>a.id===b.id?{status:'same'}:{status:'ok',minutes:8,length:620};
const event=(id,start,end,location='甲楼',extra={})=>({id,title:id,event_type:'class',location,at:start?at(start):null,ends_at:end?at(end):null,...extra});
const first=event('first','09:00','09:50'),second=event('second','10:00','10:45','乙楼');
const deadline=event('deadline','09:55',null,'丙楼',{event_type:'deadline'});
const make=(events,route=routeFor,buffer=5)=>buildDayPlan(events,buildings,route,buffer);
const plan=make([second,deadline,first]);
assert.deepEqual(plan.entries.map(entry=>entry.item.id),['first','deadline','second']);
assert.deepEqual(plan.stops.map(entry=>entry.item.id),['first','second']);
const leg=plan.legs.get(2);assert.equal(leg.from.item.id,'first');assert.equal(leg.gap,10);assert.equal(leg.slack,-3);
assert.equal(clockAt(leg.departure),'09:47');assert(transferText(leg).includes('约缺 3 分钟'));
assert(!journeyMarkup(plan,{escape:String,day,schedule:{available:true},now:Date.parse(at('09:55'))}).summary.includes('建议 '),'Do not recommend leaving before the previous event ends');
assert.equal(make([first,second],routeFor,0).legs.get(1).slack,2);
assert.equal(nextStop(plan,day,Date.parse(at('09:30'))).active[0].item.id,'first');
assert.equal(nextStop(plan,day,Date.parse(at('09:55'))).next.item.id,'second');
assert.equal(nextStop(plan,day,Date.parse(at('09:55'))).remaining,5);
assert.equal(nextStop(plan,day,Date.parse(at('10:46'))).next,undefined);
assert.deepEqual(smartMarkers(plan,day,Date.parse(at('09:55'))).map(entry=>entry.item.id),['second']);
assert.equal(smartMarkers(plan,day,Date.parse(at('10:46'))).length,0);
assert.equal(smartMarkers(plan,day,Date.parse('2026-10-20T09:55:00+08:00')).length,2);
assert.equal(nextStop(plan,day,Date.parse('2026-10-20T09:55:00+08:00')).next.item.id,'first');
assert.equal(nextStop(plan,day,Date.parse('2026-10-22T09:55:00+08:00')).next,undefined);

const unknownEnd=make([{...first,ends_at:null},second]).legs.get(1);
assert.equal(unknownEnd.gap,null);assert.equal(unknownEnd.slack,null);assert(transferText(unknownEnd).includes('结束时间待定'));
assert.equal(make([{...first,ends_at:at('08:00')},second]).legs.get(1).gap,null);
const overlap=make([{...first,ends_at:at('10:20')},second]);
assert(transferText(overlap.legs.get(1)).startsWith('时间重叠 20 分钟'));
assert.equal(nextStop(overlap,day,Date.parse(at('10:10'))).active.length,2);
const earlierOverlap=make([event('long-class','09:00','11:00'),event('short-class','09:40','09:50','乙楼'),second],routeFor,0);
assert.equal(earlierOverlap.legs.get(2).gap,10);
assert.deepEqual(earlierOverlap.legs.get(2).conflicts.map(entry=>entry.item.id),['long-class']);
assert(transferText(earlierOverlap.legs.get(2)).includes('较早的安排时间重叠'));
const overlapSummary=journeyMarkup(earlierOverlap,{escape:String,day,schedule:{available:true},now:Date.parse(at('09:55'))}).summary;
assert(overlapSummary.includes('时间重叠')&&!overlapSummary.includes('建议 '),'Do not recommend a departure while an earlier commitment still overlaps');
const same=make([first,{...second,location:'甲楼'}]).legs.get(1);
assert.equal(same.minutes,0);assert(transferText(same).startsWith('同一建筑'));
const blocked=make([first,second],()=>({status:'restricted'})).legs.get(1);
assert.equal(blocked.minutes,null);assert.equal(blocked.departure,null);assert(transferText(blocked).includes('通行限制'));

let routes=0;
const uncertain=make([first,event('unknown','09:51','09:56','尚未确定'),second],()=>{routes++;return {status:'ok',minutes:8};});
assert.equal(routes,0,'Never route past an intervening unknown location');
assert([...uncertain.legs.values()].every(item=>item.route.status==='unknown_location'));
const ambiguous=make([first,{...second,location:'甲楼或乙楼'}]);
assert.equal(ambiguous.legs.get(1).route.status,'unknown_location');
const filtered=make([first,second,...['cancel','leave','moved'].map(status=>({...first,id:status,status})),{...second,id:'adjusted',status:'rescheduled'}]);
assert.deepEqual(filtered.entries.map(entry=>entry.item.id),['first','second','adjusted']);

const missing=make([event('unknown-time',null,null),event('exam','00:00',null,'乙楼',{event_type:'exam',source:'eams'}),
  event('local-exam','11:00','12:00','丙楼',{event_type:'exam',source:'local'}),{...first,id:'all-day',all_day:true},
  {...first,id:'calendar',event_type:'calendar'},{...first,id:'naive',at:day+'T13:00:00',ends_at:null}]);
assert.equal(missing.untimed.length,3);assert.equal(missing.stops.length,4);
assert.equal(missing.stops.find(entry=>entry.item.id==='exam').start,null);
assert.equal(missing.stops.find(entry=>entry.item.id==='local-exam').start,Date.parse(at('11:00')));
assert.equal(missing.legs.size,0);assert.equal(smartMarkers(missing,day,Date.parse(at('18:00'))).length,3);
assert.equal(dayAt(Date.parse('2026-10-20T16:30:00Z')),day);
assert.equal(clockAt(Date.parse('2026-10-20T16:30:00Z')),'00:30');
console.log('campus-map: chronological attendance, next stop, completed markers, time uncertainty, transfer gaps, closures and unknown-location boundaries passed');
