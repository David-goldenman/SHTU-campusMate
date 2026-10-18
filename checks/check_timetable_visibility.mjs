import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {escape} from '../web/shared.js';
import {isLesson,lessonLayout,matchesFilter,periodsFor,compareEvents} from '../modules/timetable/web/planner.js';

// Exercise the real private renderer with synthetic schedule data, without a browser or account.
const source=await readFile(new URL('../modules/timetable/web/index.js',import.meta.url),'utf8');
const section=(start,end)=>{const first=source.indexOf(start),last=source.indexOf(end,first);assert.ok(first>=0&&last>first);return source.slice(first,last);};
const methods=section('  function when(item)', '  function overviewCard(item)')+section('  function weekView(', '  function mobileDay(');
const kinds={class:'课程',quiz:'Quiz',exam:'考试',activity:'活动',lecture:'讲座',deadline:'作业截止',calendar:'校历'};
const factory=new Function('snapshot','periodsFor','lessonLayout','isLesson','compareEvents','e','clock','kinds','statuses','otherOpen',methods+';return weekView;');
const classes=[{id:'class',title:'Synthetic course',event_type:'class',period_start:1,period_end:2,at:'2026-10-19T08:00:00+08:00',ends_at:'2026-10-19T09:00:00+08:00'},
  {id:'period-quiz',title:'Period quiz',event_type:'quiz',source:'local',period_start:3,period_end:3}];
const other=[{id:'quiz',title:'Synthetic Quiz',event_type:'quiz',source:'local',at:'2026-10-19T10:00:00+08:00'},
  {id:'exam',title:'Synthetic exam',event_type:'exam',source:'eams'},
  {id:'activity',title:'Synthetic activity',event_type:'activity',source:'local',at:'2026-10-19T12:00:00+08:00'},
  {id:'lecture',title:'Synthetic lecture',event_type:'lecture',all_day:true},
  {id:'deadline',title:'Synthetic deadline',event_type:'deadline',at:'2026-10-19T18:00:00+08:00'},
  {id:'calendar',title:'<Synthetic calendar>',event_type:'calendar',all_day:true}];
const day={date:'2026-10-19',events:[...classes,...other]},cal={week_one:'2026-10-19',days:[day],periods:[]};
const render=open=>factory({data:{metadata:{units:3},timetable:classes}},periodsFor,lessonLayout,isLesson,compareEvents,escape,()=> '10:00',kinds,{},open);
const html=render(false)(cal,item=>matchesFilter(item,'all'),()=>'', 'Synthetic week','<th>Monday</th>');
const agenda=html.match(/<details class="planner-issues planner-other-events"[^>]*>[\s\S]*?<\/details>/)?.[0];
assert.ok(agenda,'Desktop non-course items need a visible disclosure');
assert.match(agenda,/其他安排与截止（6）/);assert.doesNotMatch(agenda,/^<details[^>]*\sopen(?:\s|>)/,'Additional items stay collapsed by default');
for(const item of other)assert.ok(agenda.includes('data-event="'+item.id+'"'),'The existing clickable event path remains available for '+item.id);
for(const item of classes){assert.ok(html.includes('data-event="'+item.id+'"'));assert.ok(!agenda.includes('data-event="'+item.id+'"'),'Period items already in the course grid must not duplicate');}
assert.equal((html.match(/<table\b/g)||[]).length,1,'The fix must not restore a second wide event grid');
assert.ok(agenda.includes('&lt;Synthetic calendar&gt;'),'Titles remain escaped');
const life=render(true)(cal,item=>matchesFilter(item,'life'),()=>'', 'Synthetic week','');
assert.match(life,/<details class="planner-issues planner-other-events" open>/);assert.match(life,/其他安排与截止（2）/);
assert.ok(life.includes('data-event="activity"')&&life.includes('data-event="lecture"'));assert.ok(!life.includes('data-event="exam"'),'Agenda follows the existing study/life filter');
const empty=render(false)({...cal,days:[{...day,events:classes}]},()=>true,()=>'', 'Synthetic week','');
assert.ok(!empty.includes('planner-other-events'),'No empty disclosure when there are no additional items');
assert.match(source,/querySelectorAll\('\[data-event\]'\)\.forEach/,'New event buttons use the shared detail/edit binding');
assert.match(source,/otherAgenda\.ontoggle\s*=\s*\(\)\s*=>\s*\{\s*otherOpen\s*=\s*otherAgenda\.open;/,'Rerenders retain the disclosure choice');

const css=await readFile(new URL('../web/themes/observatory.css',import.meta.url),'utf8');
const badge=css.match(/:root\[data-art-theme="observatory"\] \.week-planner \.four-week-grid \.overview-day\.is-today::before\s*\{([^}]+)\}/)?.[1];
assert.ok(badge,'The badge override must be local to Observatory');assert.match(badge,/font-size:12px/);assert.match(badge,/color:var\(--night-button-text\)/);
const tokens=Object.fromEntries([...css.matchAll(/(--[\w-]+):\s*(#[\da-f]{6})\b/gi)].map(([,key,value])=>[key,value]));
const luminance=color=>color.slice(1).match(/../g).map(value=>parseInt(value,16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
const levels=[luminance(tokens['--night-button-text']),luminance(tokens['--nord8'])].sort((a,b)=>a-b),contrast=(levels[1]+.05)/(levels[0]+.05);
assert.ok(contrast>=4.5,'Night Today badge must meet normal-text contrast');
console.log(`Timetable visibility: desktop disclosures, filters, nonduplicated period items and event actions passed; night badge ${contrast.toFixed(2)}:1 at 12px.`);
