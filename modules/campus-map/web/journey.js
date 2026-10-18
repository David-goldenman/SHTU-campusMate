import {matchLocation} from './locations.js';

const attendanceTypes=new Set(['class','exam','quiz','tutorial','study','presentation','activity','lecture']);
const zone={timeZone:'Asia/Shanghai'};
export const dayAt=now=>new Intl.DateTimeFormat('sv-SE',zone).format(new Date(now));
export const clockAt=now=>new Intl.DateTimeFormat('zh-CN',{...zone,hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(now));
const timestamp=value=>typeof value==='string'&&/T\d{2}:\d{2}.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)&&Number.isFinite(Date.parse(value))?Date.parse(value):null;

export function buildDayPlan(events,buildings,routeFor,buffer=5) {
  const entries=events.filter(item=>!['cancel','leave','moved'].includes(item.status)).map((item,order)=>{
    const attendance=attendanceTypes.has(item.event_type)&&!item.all_day;
    const hasTime=!item.all_day&&!(item.event_type==='exam'&&item.source!=='local'&&!item.start_time);
    const start=hasTime?timestamp(item.at||item.starts_at):null,end=hasTime?timestamp(item.ends_at):null;
    return {item,order,attendance,start,end:start!==null&&end!==null&&end>=start?end:null,match:matchLocation(item.location,buildings)};
  }).sort((a,b)=>(a.start??Infinity)-(b.start??Infinity)||a.order-b.order).map((entry,index)=>({...entry,index}));
  const stops=entries.filter(entry=>entry.attendance),legs=new Map();
  for(let i=1;i<stops.length;i++) {
    const from=stops[i-1],to=stops[i];
    if(from.start===null||to.start===null)continue;
    const route=from.match.status==='matched'&&to.match.status==='matched'
      ?routeFor(from.match.buildings[0],to.match.buildings[0]):{status:'unknown_location'};
    const minutes=route?.status==='same'?0:route?.status==='ok'?route.minutes:null;
    const gap=from.end===null?null:(to.start-from.end)/60000;
    const conflicts=stops.slice(0,i).filter(entry=>entry.end!==null&&entry.end>to.start);
    legs.set(to.index,{from,to,route,gap,minutes,buffer,conflicts,
      slack:gap!==null&&minutes!==null?gap-minutes-buffer:null,
      departure:minutes!==null?to.start-(minutes+buffer)*60000:null});
  }
  return {entries,stops,legs,untimed:stops.filter(entry=>entry.start===null),buffer};
}

export function nextStop(plan,day,now=Date.now()) {
  const kind=day.localeCompare(dayAt(now));
  const active=kind===0?plan.stops.filter(entry=>entry.start!==null&&entry.end!==null&&entry.start<=now&&entry.end>now):[];
  const next=kind<0?undefined:plan.stops.find(entry=>entry.start!==null&&(kind>0||entry.start>now));
  return {kind,active,next,remaining:next?Math.max(0,Math.ceil((next.start-now)/60000)):null};
}

export function smartMarkers(plan,day,now=Date.now()) {
  return plan.stops.filter(entry=>entry.match.status==='matched'&&(day!==dayAt(now)||entry.end===null||entry.end>now));
}

export function transferText(leg) {
  if(!leg)return '';
  if(leg.gap!==null&&leg.gap<0)return `时间重叠 ${Math.ceil(-leg.gap)} 分钟，请先核对安排`;
  if(leg.conflicts.length)return '与较早的安排时间重叠，请先核对安排';
  if(leg.route?.status==='unknown_location')return '前后地点未能明确定位，请先核对地点';
  if(leg.minutes===null)return ({conditions_unavailable:'通行信息未就绪，暂不测算',conditions_invalid:'通行范围需复核，暂不测算',restricted:'起点或终点受通行限制',disconnected:'已收录道路不连通',unmapped:'地点附近缺少可用道路'})[leg.route?.status]||'室外路线暂不可用';
  if(leg.gap===null)return '上一项结束时间待定，无法判断间隔是否足够';
  if(leg.route.status==='same')return `同一建筑 · 间隔 ${Math.floor(leg.gap)} 分钟，楼内换教室用时未计`;
  const prefix=`间隔 ${Math.floor(leg.gap)} 分钟 · 步行约 ${leg.minutes} 分钟`;
  return prefix+(leg.slack<0?` · 加上预留时间约缺 ${Math.ceil(-leg.slack)} 分钟`:` · 预留后约余 ${Math.floor(leg.slack)} 分钟`);
}
