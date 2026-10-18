import {eventTime} from './locations.js';
import {nextStop,clockAt,transferText} from './journey.js';

const kinds={class:'课程',deadline:'作业截止',exam:'考试',quiz:'Quiz',tutorial:'习题课',study:'学习',presentation:'展示',activity:'活动',lecture:'讲座',calendar:'校历'};
const notices={missing:'尚未提供地点',unknown:'地点待确认',ambiguous:'包含多个建筑，需选择具体地点'};
export function journeyMarkup(plan,{escape:e,day,schedule,selectedEvent,now=Date.now(),lastRead}) {
  const {entries,legs}=plan,{kind,active,next,remaining}=nextStop(plan,day,now);
  const title=entry=>entry.item.title||entry.item.course_title||'未命名安排';
  const canWalk=entry=>entry.attendance&&entry.match.status==='matched';
  const canTransfer=leg=>['ok','same'].includes(leg?.route?.status);
  const transfer=leg=>`<div class="map-transfer${leg.slack<0||leg.gap<0?' is-tight':''}"><p>${e(transferText(leg))}</p>${canTransfer(leg)?`<button type="button" data-transfer="${leg.to.index}" aria-label="查看${e(title(leg.from))}到${e(title(leg.to))}的路线">查看这段路线 ↗</button>`:''}</div>`;
  const leg=next&&legs.get(next.index);
  const nextCard=next?`<section class="map-next-stop" aria-label="下一站"><div class="map-next-heading"><span>${kind>0?'当日首项':'下一站'}</span><strong>${kind===0?remaining+' 分钟后开始':e(eventTime(next.item))}</strong></div><button type="button" class="map-next-title" data-event="${next.index}">${e(title(next))} ↗</button><p>${e(next.item.location||'地点待确认')} · ${e(eventTime(next.item))}</p>${leg?`<p class="map-next-origin">按上一安排的地点：${e(leg.from.item.location||'待确认')}</p>${transfer(leg)}${leg.departure!==null&&leg.gap!==null&&leg.gap>=0&&leg.route?.status==='ok'?`<p>建议 ${e(clockAt(leg.departure))} 前从上一地点出发</p>`:''}`:canWalk(next)?`<button type="button" class="map-next-action" data-walk-event="${next.index}">选择起点，步行到这里 ↗</button>`:''}</section>`:'';
  const current=active.length?`<p class="map-current">正在进行：${e(active.map(title).join('、'))}${active.length>1?' · 时间有重叠':''}</p>`:'';
  const noNext=kind===0&&plan.stops.length&&!next?'<p class="map-notice">今天没有更晚的定时安排。</p>':'';
  const knownLegs=[...legs.values()].filter(canTransfer),total=knownLegs.reduce((sum,item)=>sum+(item.route.length||0),0);
  const daySummary=`<p class="map-day-summary">${e(day)} · ${entries.length} 项安排 · ${plan.stops.length} 项到场安排${knownLegs.length?`<br>已测算 ${knownLegs.length} 段室外行程 · 合计约 ${Math.round(total/10)*10} 米`:''}</p>`;
  const untimed=plan.untimed.length?`<p class="map-notice">另有 ${plan.untimed.length} 项到场安排时间待定，未纳入先后顺序与课间测算。</p>`:'';
  const rows=entries.map(entry=>{
    const {item,index,match}=entry;
    const state=kind!==0||!entry.attendance||entry.start===null?'':entry.end!==null&&entry.end<=now?'已结束':entry.start>now?'未开始':entry.end!==null?'进行中':'已到开始时间 · 结束待定';
    return `<li>${legs.has(index)?transfer(legs.get(index)):''}<button type="button" data-event="${index}" class="map-event${selectedEvent===item.id?' is-active':''}${state==='已结束'?' is-finished':''}"><span class="map-event-number${match.status==='matched'&&entry.attendance?'':' is-unlocated'}">${index+1}</span><span class="map-event-body"><span class="map-event-time">${e(eventTime(item))}${state?` · ${e(state)}`:''}</span><strong>${e(title(entry))}</strong><span>${e(item.location||'尚未提供地点')}</span><small>${e(kinds[item.event_type]||'安排')}${item.status==='rescheduled'?' · 调课后':''}${!entry.attendance?' · 不作为通勤地点':match.status==='matched'?' · 点击定位':' · '+e(notices[match.status])}</small></span></button>${canWalk(entry)?`<button class="map-walk-event" type="button" data-walk-event="${index}" aria-label="步行到${e(title(entry))}">↗ 步行到这里</button>`:''}</li>`;
  }).join('');
  return {summary:`${current}${nextCard}${noNext}`,agenda:`${schedule.issues?.length?`<p class="map-notice">${e(schedule.issues.join('；'))}</p>`:''}${schedule.status==='partial'?'<p class="map-notice">部分来源尚未就绪，以下为当前可用安排。</p>':''}${daySummary}${untimed}${entries.length?`<ol class="map-events">${rows}</ol><p class="map-journey-note">按安排中的地点测算，不代表当前位置。室外步行按 80 米/分钟估算，另预留 ${plan.buffer} 分钟进楼；楼内路线及临时通行情况以现场为准。</p>`:`<div class="map-empty"><span aria-hidden="true">${schedule.available?'☀':'⌖'}</span><h3>${schedule.available?'这一天暂无安排':'日程暂不可用'}</h3><p>${schedule.available?'可以切换日期查看课程，或把地点标注切换为“全部”。':'校园地图仍可查看。可到设置检查时间表模块。'}</p></div>`}${lastRead?`<p class="map-journey-note">${e(clockAt(lastRead))} 读取时间表 · 仅刷新本地已同步安排</p>`:''}`};
}
