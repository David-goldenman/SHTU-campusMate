import {today, shiftDay, validDay, matchLocation, eventTime, projectCampus, buildingLabel, layoutLabels} from './locations.js';

import {buildWalkingGraph, planWalk} from './routing.js';
import {compileConditions,routeConditionWarnings} from './conditions.js';
import {createMaintenance} from './maintenance.js';
import {createDiscovery} from './discovery.js';
import {bindMapGestures,zoomView} from './interactions.js';

const kinds = {class:'课程', deadline:'作业截止', exam:'考试', quiz:'Quiz', tutorial:'习题课', study:'学习', presentation:'展示', activity:'活动', lecture:'讲座', calendar:'校历'};
const notices = {missing:'尚未提供地点', unknown:'地点待确认，未在图上标记', ambiguous:'包含多个建筑，请选择具体地点'};

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css', import.meta.url), context.signal);
  let request, serial = 0, data, projection, schedule, selected, selectedEvent, layer = 'day', observer, cancelGesture;
  const cleanup = () => {request?.abort();cancelGesture?.();observer?.disconnect();removeStyle();container.classList.remove('campus-map','map-expanded');};
  context.signal.addEventListener('abort', cleanup, {once:true});
  container.classList.add('campus-map');
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  let day = validDay(params.get('date')) ? params.get('date') : today();
  let view, graph, route, startId='', endId='', routeEvent, networkRequest, maintenance, discovery, conditionState;
  context.signal.addEventListener('abort',()=>networkRequest?.abort(),{once:true});
  container.innerHTML = `<header class="map-heading"><div><span class="map-eyebrow">SHANGHAITECH · CAMPUS</span><h2>今天，去哪儿</h2><p>把每天的安排，放回校园里。</p></div><a class="button button-secondary" href="https://map.shanghaitech.edu.cn/" target="_blank" rel="noopener noreferrer">学校官方地图 ↗</a></header>
    <div class="map-layout"><section class="map-panel" aria-label="校园建筑地图"><div class="map-tools"><div class="map-layers" aria-label="地图图层"><button type="button" data-layer="day" aria-pressed="true">当天地点</button><button type="button" data-layer="elevators" aria-pressed="false">电梯位置</button><button type="button" data-layer="gates" aria-pressed="false">出入口</button><button type="button" data-layer="conditions" aria-pressed="false">施工 / 通行</button></div><label class="map-search-label"><span class="map-sr-only">搜索建筑或教室</span><input data-search type="search" placeholder="搜索建筑 / 教室，如信息学院1D-102" autocomplete="off"></label></div><div data-results class="map-search-results" hidden></div>
    <section class="map-routing" aria-label="室外步行路线"><div class="map-route-heading"><h3>室外步行</h3><span>选地点 · 连成路</span></div><form data-route-form><div class="map-route-fields"><label>起点<select data-route-start aria-label="步行起点" disabled><option value="">正在读取路网…</option></select></label><button type="button" data-route-swap aria-label="交换起点和终点" title="交换起点和终点">⇄</button><label>终点<select data-route-end aria-label="步行终点" disabled><option value="">正在读取路网…</option></select></label></div><div class="map-route-actions"><button class="button button-primary" type="submit" data-route-submit disabled>规划步行路线</button><button class="button button-secondary" type="button" data-route-clear>清除</button><span>也可在当天安排中选择终点</span></div><label class="map-avoid-pending"><input type="checkbox" data-avoid-pending>避开待核实范围</label></form><div class="map-condition-status" data-condition-status aria-live="polite"></div><div data-route-result aria-live="polite"><p>正在读取室外路网…</p></div></section><div class="map-canvas"><div data-loading class="map-loading" role="status">正在读取校园建筑图…</div><svg data-map aria-label="上海科技大学建筑地图，可用方向键平移、加减号缩放" tabindex="0" role="group"></svg><span class="map-north" aria-hidden="true">↑<small>北 N</small></span><button class="map-expand" type="button" data-expand aria-expanded="false">⤢ 展开地图</button><button type="button" class="map-condition-done" data-condition-done hidden>完成选取</button><span class="map-gesture-hint">拖动浏览 · 放大查看更多楼名</span><div class="map-zoom" aria-label="地图缩放"><button type="button" data-zoom="in" aria-label="放大地图">＋</button><button type="button" data-zoom="out" aria-label="缩小地图">−</button><button type="button" data-zoom="reset">全图</button></div><a class="map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">道路与绿地 © OpenStreetMap contributors</a></div>
    <div class="map-legend"><span class="map-key map-key-teaching">教学科研</span><span class="map-key map-key-sport">运动场馆</span><span class="map-key map-key-service">生活服务</span><span class="map-key map-key-road">道路</span><span class="map-key map-key-path">步行道</span></div><div class="map-gates" data-gates aria-label="校园出入口"></div><div data-detail class="map-detail" aria-live="polite"><h3>校园里的下一站</h3><p>选择一项安排，或搜索建筑名称。地图标记对应整栋建筑，教室与电梯的楼内位置见详情。</p></div><details class="map-maintenance"><summary>施工与通行维护</summary><div data-maintenance></div></details></section>
    <aside class="map-agenda"><div class="map-agenda-heading"><div><span class="map-eyebrow">YOUR DAY</span><h3>当天安排</h3></div><a href="#timetable">时间表 ↗</a></div><div class="map-date"><button class="button button-secondary" type="button" data-day="prev" aria-label="前一天">‹</button><input data-date type="date" aria-label="查看日期" value="${e(day)}"><button class="button button-secondary" type="button" data-day="next" aria-label="后一天">›</button><button class="button button-secondary" type="button" data-day="today">今天</button></div><div data-agenda aria-live="polite"></div></aside></div>
    <footer class="map-source">建筑底图与 5 处校门来自学校官方地图；道路、水系与绿地来自 OpenStreetMap · 基础资料收录 2026-10-17。博士公寓轮廓按官方设计公示图更新，尚未核验竣工实况；部分名称按使用者反馈更正，依据见地点详情。室外步行路线依据已收录道路计算，开放情况以现场为准；不含室内、地下路线。电梯资料覆盖 2 栋建筑、3 条位置说明。</footer>`;
  const svg = container.querySelector('[data-map]'), agenda = container.querySelector('[data-agenda]'), detail = container.querySelector('[data-detail]');
  const on = (node, name, handler) => node.addEventListener(name, handler, {signal:context.signal});
  const buildingById = id => data.buildings.find(item => item.id === id);
  const routePlaceLabel = building => buildingLabel(building)+(building.walking_approach?' · '+building.walking_approach.label:'');
  const entries = () => (schedule?.events || []).map((item, index) => ({item, index, match:matchLocation(item.location, data.buildings)}));
  function setView() {if(view){svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`);drawAnnotations();}}
  function resetView() {if (!projection) return;cancelGesture?.();view={x:0,y:0,w:projection.width,h:projection.height};setView();}
  function zoom(factor,anchor) {
    if (!view) return;
    cancelGesture?.();view=zoomView(view,projection,factor,anchor);setView();
  }
  function mapMarks() {
    const marks = new Map();
    if(layer === 'elevators') for(const item of data.elevators) marks.set(item.building_id, '↕');
    else if(layer==='day')for(const {index,match} of entries()) if(match.status === 'matched') {const id=match.buildings[0].id;marks.set(id, [...(marks.get(id)||[]),index+1]);}
    return marks;
  }
  const primaryNames = ['图书馆','教学中心','体育馆','生命学院','信息学院1号楼','信息学院2号楼','信息学院3号楼','创意与艺术学院','数学科学研究所','行政中心','创业与管理学院','体育场','游泳馆','会议中心','H1,校园服务中心,309室 IT服务中心','H2楼,学生科创中心','博士公寓11号楼','博士公寓12号楼','博士公寓13号楼'];
  function drawAnnotations() {
    const host=svg.querySelector('[data-annotations]');if(!host||!projection||!view)return;
    const restoreFocus=host.contains(document.activeElement);
    const size=svg.getBoundingClientRect(),marks=mapMarks(),zoomLevel=projection.width/view.w;
    const candidates=data.buildings.filter(b=>b.kind==='gate'||b.id===selected||marks.has(b.id)||primaryNames.includes(b.name)||zoomLevel>1.4).map(b=>({id:b.id,label:buildingLabel(b),point:projection.center(b.polygon),kind:b.kind||'building',marker:marks.has(b.id),priority:b.id===selected?100:b.kind==='gate'?90:marks.has(b.id)?85:primaryNames.includes(b.name)?60-primaryNames.indexOf(b.name):20}));
    const roadsByName=new Map();
    for(const road of data.basemap?.roads||[])if(road.name&&(!roadsByName.has(road.name)||road.points.length>roadsByName.get(road.name).points.length))roadsByName.set(road.name,road);
    for(const [name,road] of roadsByName)candidates.push({id:'road-'+road.id,label:name,point:projection.point(road.points[Math.floor(road.points.length/2)]),kind:'road',priority:1});
    const units=1/Math.min(size.width/view.w,size.height/view.h);
    const pins=[...marks].map(([id,mark])=>{const b=buildingById(id),[x,y]=projection.center(b.polygon),label=Array.isArray(mark)?mark.join('·'):mark;return `<g data-building="${e(id)}" class="map-pin${layer==='elevators'?' map-pin-elevator':''}" role="button" tabindex="0" aria-label="${e(b.name+(layer==='elevators'?'，有电梯位置资料':'，当天安排 '+label))}" transform="translate(${x},${y}) scale(${units})"><rect x="${-Math.max(14,label.length*5)}" y="-28" width="${Math.max(28,label.length*10)}" height="28" rx="14"/><text y="-9">${e(label)}</text></g>`;}).join('');
    host.innerHTML=pins+layoutLabels(candidates,view,size).map(item=>{
      const gate=item.kind==='gate',road=item.kind==='road',b=buildingById(item.id),x=item.box.w/2+(gate?7:0);
      const stemX=(item.point[0]-item.x)/item.units,stemY=(item.point[1]-item.y)/item.units;
      return `<g ${road?'':`data-building="${e(item.id)}" role="button" tabindex="0" aria-label="定位${e(b.name)}"`} class="map-label ${gate?'map-label-gate':road?'map-label-road':''}${selected===item.id?' is-selected':''}" transform="translate(${item.x},${item.y}) scale(${item.units})">${road?'':`<line class="map-label-stem" x1="${stemX}" y1="${stemY}" x2="${item.box.w/2}" y2="${item.box.h/2}"/><circle class="map-label-dot" cx="${stemX}" cy="${stemY}" r="${gate?4:2.3}"/>`}<rect class="map-label-bg" width="${item.box.w}" height="${item.box.h}" rx="${gate?14:5}"/>${gate?'<path class="map-gate-icon" d="M9 20V9h10v11 M12 15h11 m-3-3 3 3-3 3"/>':''}<text x="${x}" y="19">${item.lines.map((line,index)=>`<tspan x="${x}" dy="${index?19:0}">${e(line)}</tspan>`).join('')}</text></g>`;
    }).join('');
    if(route?.status==='ok') {
      const ends=route.length<2?[[route.start.point,'起 / 终','start']]:[[route.start.point,'起','start'],[route.end.point,'终','end']];
      host.innerHTML+=ends.map(([point,label,kind])=>{const [x,y]=projection.point(point);return `<g class="map-route-pin is-${kind}" transform="translate(${x},${y}) scale(${units})" aria-label="${label}点，室外道路"><circle r="15"/><text y="5">${label}</text></g>`;}).join('');
    }
    if(restoreFocus)svg.focus({preventScroll:true});
  }
  function drawMap() {
    if (!data) return;
    const restoreFocus=svg.contains(document.activeElement);
    const marks=mapMarks(),basemap=data.basemap||{roads:[],landscape:[]};
    const roadMarkup=basemap.roads.map(road=>`<polyline class="map-road ${road.type==='footway'?'is-footway':''}" points="${projection.polygon(road.points)}"/>`).join('');
    svg.innerHTML=`<polygon class="map-boundary" points="${projection.polygon(data.campus.polygon)}"/><g class="map-landscape">${basemap.landscape.map(item=>item.polygon?`<polygon class="map-land-${e(item.kind)}" points="${projection.polygon(item.polygon)}"/>`:`<polyline class="map-land-waterway" points="${projection.polygon(item.points)}"/>`).join('')}</g><g class="map-road-casings">${roadMarkup}</g><g class="map-road-surfaces">${roadMarkup}</g><g class="map-buildings">`+data.buildings.filter(b=>b.kind!=='gate').map(building=>`<g data-building="${e(building.id)}" role="button" tabindex="0" aria-label="${e(building.name)}" aria-pressed="${selected===building.id}" class="map-building category-${e(building.category)}${selected===building.id?' is-selected':''}${marks.has(building.id)?' is-marked':''}"><title>${e(building.name)}</title><polygon points="${projection.polygon(building.polygon)}"/></g>`).join('')+`</g>${maintenance?.overlay(projection,layer==='conditions')||''}${route?.status==='ok'?`<polyline class="map-route-outline" points="${projection.polygon(route.points)}"/><polyline class="map-route-line" points="${projection.polygon(route.points)}"><title>室外步行路线</title></polyline>`:''}<g data-annotations></g>`;
    container.querySelector('.map-canvas').classList.toggle('is-editing-conditions',!!maintenance?.mode);
    container.querySelector('[data-condition-done]').hidden=!maintenance?.mode;
    container.querySelector('.map-gesture-hint').textContent=maintenance?.mode==='edges'?'点选道路 · 再点可取消':maintenance?.mode==='area'?'点击施工范围的两个对角点':'拖动浏览 · 滚轮缩放';
    drawAnnotations();
    if(restoreFocus)svg.focus({preventScroll:true});
  }
  function renderAgenda() {
    if (!schedule) return;
    const items=entries();
    agenda.innerHTML = `${schedule.issues?.length ? `<p class="map-notice">${e(schedule.issues.join('；'))}</p>`:''}${schedule.status==='partial' ? '<p class="map-notice">部分来源尚未就绪，以下为当前可用安排。</p>':''}<p class="map-day-summary">${e(new Intl.DateTimeFormat('zh-CN',{weekday:'long',timeZone:'Asia/Shanghai'}).format(new Date(day+'T12:00:00+08:00')))} · ${items.length} 项安排 · ${items.filter(v=>v.match.status==='matched').length} 项已定位</p>${items.length ? '<ol class="map-events">'+items.map(({item,index,match})=>`<li><button type="button" data-event="${index}" class="map-event${selectedEvent===item.id?' is-active':''}"><span class="map-event-number${match.status==='matched'?'':' is-unlocated'}">${index+1}</span><span class="map-event-body"><span class="map-event-time">${e(eventTime(item))}</span><strong>${e(item.title||item.course_title||'未命名安排')}</strong><span>${e(item.location||'尚未提供地点')}</span><small>${e(kinds[item.event_type]||'安排')}${item.status==='rescheduled'?' · 调课后':''}${match.status==='matched'?' · 点击定位':' · '+e(notices[match.status])}</small></span></button>${match.status==='matched'?`<button class="map-walk-event" type="button" data-walk-event="${index}" aria-label="步行到${e(item.title||item.course_title||'这项安排')}">↗ 步行到这里</button>`:''}</li>`).join('')+'</ol>':`<div class="map-empty"><span aria-hidden="true">${schedule.available?'☀':'⌖'}</span><h3>${schedule.available?'这一天暂无安排':'日程暂不可用'}</h3><p>${schedule.available?'可以切换日期查看课程，或在校园地图中寻找地点。':'校园建筑与电梯资料仍可查看。可到设置检查时间表模块。'}</p></div>`}`;
  }
  function renderDetail(locationText='') {
    const building=buildingById(selected);
    if(!building) {detail.innerHTML='<h3>校园里的下一站</h3><p>选择一项安排，或搜索建筑名称。地图标记对应整栋建筑，教室与电梯的楼内位置见详情。</p>';return;}
    const elevators=data.elevators.filter(item=>item.building_id===selected);
    detail.innerHTML=`<div class="map-detail-heading"><div><span class="map-eyebrow">${building.kind==='gate'?'校园出入口':e(building.category_label)}</span><h3>${e(building.short_name||building.name)}</h3></div><a href="${e(building.source_url)}" target="_blank" rel="noopener noreferrer">官方地图 / 导航 ↗</a></div>${building.address?`<p class="map-room">${e(building.address)}</p>`:''}${building.walking_approach?`<p class="map-notice"><strong>入口提示 · ${e(building.walking_approach.source_label)}</strong><br>${e(building.walking_approach.note)}</p>`:''}${locationText?`<p class="map-room">教室 / 地点：<strong>${e(locationText)}</strong></p>`:''}<div class="map-place-actions"><button type="button" data-place-start="${e(building.id)}">设为起点</button><button type="button" data-place-end="${e(building.id)}">步行到这里</button></div><p class="map-detail-hint">${building.kind==='gate'?'校门位置来自学校官方地图，人员与车辆通行安排以现场管理为准。':'已定位到建筑。具体入口和楼内走法请以现场指引为准。'}</p>${elevators.length?'<div class="map-elevators"><h4>↕ 电梯位置说明</h4>'+elevators.map(item=>`<article><strong>${e(item.floor)} · ${e(item.name)}</strong><p>${e(item.location)}</p><a href="${e(item.source_url)}" target="_blank" rel="noopener noreferrer">${e(item.source_title)} ↗</a></article>`).join('')+'<p class="map-detail-hint">图上标记属于整栋建筑，楼内位置以文字说明为准；未核实当前开放状态。</p></div>':layer==='elevators'?'<p class="map-notice">这栋建筑暂未收录有出处的电梯位置资料。</p>':''}`;
    if(building.source_label)detail.querySelector('.map-detail-heading a').textContent=building.source_label;
    if(building.place_update)detail.querySelector('.map-detail-heading').insertAdjacentHTML('afterend',`<p class="map-notice"><strong>地点更新 · ${e(building.place_update.source_label)}</strong><br>${e(building.place_update.note)}</p>`);
  }
  function selectBuilding(id, locationText='', focus=true) {
    selected=id;const building=buildingById(id);if(!building)return;
    cancelGesture?.();
    if(focus) {const [x,y]=projection.center(building.polygon),w=projection.width/2,h=projection.height/2;view={x:x-w/2,y:y-h/2,w,h};setView();}
    drawMap();renderDetail(locationText);renderAgenda();
  }
  function selectEvent(index) {
    const entry=entries()[index];if(!entry)return;selectedEvent=entry.item.id;
    if(entry.match.status==='matched') selectBuilding(entry.match.buildings[0].id,entry.item.location);
    else {selected=undefined;drawMap();renderAgenda();detail.innerHTML=`<h3>${e(entry.item.title||'安排地点')}</h3><p>${e(entry.item.location||'尚未提供地点')}</p><p class="map-notice">${e(notices[entry.match.status])}</p>${entry.match.buildings.map(b=>`<button class="button button-secondary" data-candidate="${e(b.id)}" type="button">${e(b.name)}</button>`).join('')}`;}
    if(matchMedia('(max-width:1100px)').matches) container.querySelector(entry.match.status==='matched'?'.map-canvas':'.map-detail').scrollIntoView({block:'center'});
  }
  const routeStart=container.querySelector('[data-route-start]'),routeEnd=container.querySelector('[data-route-end]'),routeResult=container.querySelector('[data-route-result]');
  function renderRoute() {
    routeStart.value=startId;routeEnd.value=endId;
    const source=routeEvent?`<p class="map-route-course">课程终点 · ${e(routeEvent.title||routeEvent.course_title||'当天安排')}<br>${e(day)} ${e(eventTime(routeEvent))} · ${e(routeEvent.location)}</p>`:'';
    const messages={conditions_unavailable:'通行维护记录尚未就绪，暂不生成路线。',conditions_invalid:'部分已确认限制在当前底图中失去定位，请在维护页面复核后再规划。',restricted:'起点或终点受到当前通行限制，请选择其他地点。',missing:'选择起点和终点，或在当天安排中点“步行到这里”。',same:'起点和终点是同一地点，无需规划室外路线。',unmapped:'该地点附近尚未收录可用的室外步行道路，请选择其他地点。',disconnected:'这两个地点之间的已收录室外路网尚未连通，暂时无法规划路线。'};
    if(!graph){routeResult.innerHTML='<p>室外路网暂不可用，请重新打开校园地图重试。</p>';return;}
    if(route?.status!=='ok'){routeResult.innerHTML=source+`<p>${e(route?.message||messages[route?.status||'missing'])}</p>`;return;}
    const warnings=conditionState?routeConditionWarnings(route,conditionState):[];
    const conditionNotes=warnings.map(item=>`<p class="map-condition-warning"><strong>${e(item.state==='pending'?'途经待核实范围':'通行提醒')} · ${e(item.title)}</strong><br>${e(item.note)}</p>`).join('');
    const approachNotes=[buildingById(startId),buildingById(endId)].filter(b=>b.walking_approach).map(b=>`<p class="map-route-course"><strong>${e(b.name)}入口提示 · ${e(b.walking_approach.source_label)}</strong><br>${e(b.walking_approach.note)}</p>`).join('');
    routeResult.innerHTML=source+`<div class="map-route-summary"><strong>约 ${Math.max(0,Math.round(route.length/10)*10)} 米 <span>· ${route.minutes} 分钟</span></strong><button type="button" data-route-fit>查看全程 ↗</button></div><p class="map-route-endpoints">${e(routePlaceLabel(buildingById(startId)))} → ${e(routePlaceLabel(buildingById(endId)))}</p>${conditionNotes}${approachNotes}<p>起终点均在建筑 / 校门附近的室外道路。步行按 80 米/分钟估算，进楼与等候时间另计。${route.stairs?'本路线经过室外台阶。':''}</p><details class="map-route-steps"><summary>怎么走 · ${route.steps.length} 段道路</summary><ol>${route.steps.map(step=>`<li>${e(step.text)}<strong>约 ${Math.max(1,Math.round(step.length))} 米</strong></li>`).join('')}<li>到达${e(routePlaceLabel(buildingById(endId)))}的室外道路，请按现场指引进入。</li></ol></details><p class="map-route-limit">室外试用路线 · 通行以现场为准，未核实无障碍条件。</p>`;
  }
  function fitRoute() {
    if(route?.status!=='ok')return;
    cancelGesture?.();
    const points=route.points.map(projection.point),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const cx=(Math.max(...xs)+Math.min(...xs))/2,cy=(Math.max(...ys)+Math.min(...ys))/2;
    const w=Math.min(projection.width*1.1,Math.max(250,Math.max(...xs)-Math.min(...xs)+150,(Math.max(...ys)-Math.min(...ys)+150)*projection.width/projection.height));
    const h=w*projection.height/projection.width;view={x:cx-w/2,y:cy-h/2,w,h};setView();
  }
  function calculateRoute(focus=false) {
    conditionState=graph&&maintenance?.ready?compileConditions(graph,maintenance.snapshot.items,day,data.buildings,container.querySelector('[data-avoid-pending]').checked):undefined;
    const blocked=conditionState?.blockedPlaces.get(startId)||conditionState?.blockedPlaces.get(endId);
    if(!graph)route=undefined;
    else if(!maintenance?.ready)route={status:'conditions_unavailable'};
    else if(conditionState.invalid.length)route={status:'conditions_invalid'};
    else if(blocked)route={status:'restricted',message:(blocked.state==='pending'?'已选择避开待核实范围：':'该地点有已确认通行限制：')+blocked.title+'。请改选地点或在维护页面核实。'};
    else route=planWalk(conditionState.graph,buildingById(startId),buildingById(endId));
    container.querySelector('[data-route-submit]').disabled=!maintenance?.ready;
    maintenance?.status();
    renderRoute();drawMap();if(focus)fitRoute();
  }
  function setEndpoint(kind,id,item) {
    if(kind==='start')startId=id;else {endId=id;routeEvent=item;}
    calculateRoute(true);
  }
  on(container.querySelector('[data-route-form]'),'submit',event=>{event.preventDefault();calculateRoute(true);});
  on(container.querySelector('[data-avoid-pending]'),'change',()=>calculateRoute(true));
  on(routeStart,'change',event=>setEndpoint('start',event.target.value));
  on(routeEnd,'change',event=>setEndpoint('end',event.target.value));
  async function loadNetwork() {
    networkRequest=new AbortController();
    try {
      const network=await context.api('/walking-network',{signal:networkRequest.signal});if(context.signal.aborted)return;
      graph=buildWalkingGraph(network);
      const discoveryHost=document.createElement('div');discoveryHost.className='map-discovery';discoveryHost.dataset.discovery='';container.querySelector('.map-maintenance>summary').after(discoveryHost);
      maintenance=createMaintenance({context,host:container.querySelector('[data-maintenance]'),statusHost:container.querySelector('[data-condition-status]'),data,graph,getDay:()=>day,onUpdate:()=>calculateRoute(),focusMap:()=>container.querySelector('.map-canvas').scrollIntoView({block:'center'}),redraw:drawMap,onSaved:()=>void discovery?.load()});
      discovery=createDiscovery({context,host:discoveryHost,onReview:(lead,account)=>maintenance.reviewLead(lead,account),onAccountChange:()=>void maintenance.load(true),onUpdate:count=>maintenance.setDiscovered(count)});
      void discovery.load();
      const options='<option value="">请选择地点</option>'+['gate','building'].map(kind=>`<optgroup label="${kind==='gate'?'校门':'校园建筑'}">${data.buildings.filter(b=>(b.kind||'building')===kind).sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(b=>`<option value="${e(b.id)}">${e(buildingLabel(b))}</option>`).join('')}</optgroup>`).join('');
      for(const select of [routeStart,routeEnd]){select.innerHTML=options;select.disabled=false;}
      await maintenance.load();if(context.signal.aborted)return;calculateRoute();
    }catch(error){if(!context.signal.aborted){routeStart.innerHTML=routeEnd.innerHTML='<option value="">路网不可用</option>';renderRoute();}}
  }
  async function loadDay() {
    request?.abort();request=new AbortController();const ticket=++serial;
    schedule=undefined;selectedEvent=undefined;selected=undefined;
    if(routeEvent){routeEvent=undefined;endId='';route=undefined;renderRoute();}
    if(graph){calculateRoute();maintenance?.render();}
    drawMap();renderDetail();agenda.innerHTML='<p class="map-notice" role="status">正在读取当天安排…</p>';
    try {
      const value=await context.api('/day?date='+encodeURIComponent(day),{signal:request.signal});
      if(context.signal.aborted||ticket!==serial)return;
      schedule=value;renderAgenda();drawMap();
      const target=params.get('event');if(target){const index=entries().findIndex(v=>v.item.id===target);if(index>=0)selectEvent(index);params.delete('event');}
    } catch(error) {if(context.signal.aborted||ticket!==serial)return;agenda.innerHTML=`<p class="map-notice">${e(error.message||'当天安排读取失败')}</p><button class="button button-secondary" type="button" data-retry>重新读取</button>`;}
  }
  on(container,'click',event=>{
    if(!data)return;
    if(maintenance?.mode&&svg.contains(event.target))return;
    const button=event.target.closest('button,a,[data-building]');if(!button)return;
    if(button.hasAttribute('data-condition-done'))maintenance?.finish();
    if(button.hasAttribute('data-route-swap')){[startId,endId]=[endId,startId];routeEvent=undefined;calculateRoute(true);}
    if(button.hasAttribute('data-route-clear')){startId='';endId='';routeEvent=undefined;route=undefined;renderRoute();drawMap();}
    if(button.hasAttribute('data-route-fit'))fitRoute();
    if(button.dataset.placeStart)setEndpoint('start',button.dataset.placeStart);
    if(button.dataset.placeEnd)setEndpoint('end',button.dataset.placeEnd);
    if(button.hasAttribute('data-walk-event')) {
      const entry=entries()[Number(button.dataset.walkEvent)];
      if(entry?.match.status==='matched'){selectedEvent=entry.item.id;selected=entry.match.buildings[0].id;setEndpoint('end',selected,entry.item);renderDetail(entry.item.location);renderAgenda();container.querySelector('.map-routing').scrollIntoView({block:'start'});if(!startId)routeStart.focus({preventScroll:true});}
    }
    if(button.dataset.layer){layer=button.dataset.layer;container.querySelectorAll('[data-layer]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));drawMap();if(layer==='gates'){selectedEvent=undefined;resetView();selectBuilding(data.buildings.find(b=>b.kind==='gate').id,'',false);}else if(layer==='elevators'&&!selected)selectBuilding(data.elevators[0].building_id,'',false);else renderDetail();}
    if(button.hasAttribute('data-expand')){const expanded=container.classList.toggle('map-expanded');button.setAttribute('aria-expanded',String(expanded));button.textContent=expanded?'⤡ 收起地图':'⤢ 展开地图';}
    if(button.dataset.gate){selectedEvent=undefined;selectBuilding(button.dataset.gate);}
    if(button.dataset.zoom){if(button.dataset.zoom==='reset')resetView();else zoom(button.dataset.zoom==='in'?.75:1.333);}
    if(button.hasAttribute('data-event'))selectEvent(Number(button.dataset.event));
    // Pointer taps are handled once on release; detail=0 retains assistive activation.
    if(button.dataset.building&&event.detail===0){selectedEvent=undefined;selectBuilding(button.dataset.building,'',false);}
    if(button.dataset.candidate){selectedEvent=undefined;selectBuilding(button.dataset.candidate);container.querySelector('[data-results]').hidden=true;}
    if(button.dataset.day){day=button.dataset.day==='today'?today():shiftDay(day,button.dataset.day==='prev'?-1:1);container.querySelector('[data-date]').value=day;void loadDay();}
    if(button.hasAttribute('data-retry'))void loadDay();
  });
  on(container.querySelector('[data-date]'),'change',event=>{if(data&&validDay(event.target.value)){day=event.target.value;void loadDay();}else event.target.value=day;});
  on(container.querySelector('[data-search]'),'input',event=>{
    if(!data)return;const query=event.target.value.trim().normalize('NFKC').toLowerCase(),host=container.querySelector('[data-results]');host.hidden=!query;if(!query)return;
    const matched=matchLocation(query,data.buildings).buildings;
    const options=data.buildings.filter(b=>matched.includes(b)||b.aliases.some(alias=>alias.toLowerCase().includes(query))).slice(0,12);
    host.innerHTML=options.length?options.map(b=>`<button type="button" data-candidate="${e(b.id)}"><strong>${e(b.name)}</strong><small>${e(b.category_label)}</small></button>`).join(''):'<p>未找到明确建筑，可尝试完整楼名；室内教室仅能定位到所属建筑。</p>';
  });
  on(svg,'keydown',event=>{
    if(!view)return;
    if(['Enter',' ','+','=','-','0','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))cancelGesture?.();
    if(maintenance?.mode&&['Enter',' '].includes(event.key)){const road=event.target.closest('[data-maint-road]');if(road){event.preventDefault();maintenance.mapClick(null,road.dataset.maintRoad);}return;}
    const building=event.target.closest('[data-building]');
    if(building&&['Enter',' '].includes(event.key)){event.preventDefault();selectedEvent=undefined;selectBuilding(building.dataset.building,'',false);return;}
    if(['+','=','-','0','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();if(['+','='].includes(event.key))zoom(.75);else if(event.key==='-')zoom(1.333);else if(event.key==='0')resetView();else {view.x+=({'ArrowLeft':-1,'ArrowRight':1}[event.key]||0)*view.w*.08;view.y+=({'ArrowUp':-1,'ArrowDown':1}[event.key]||0)*view.h*.08;setView();}}
  });
  cancelGesture=bindMapGestures(svg,{signal:context.signal,getView:()=>view,setView:next=>{view=next;setView();},onZoom:zoom,onTap:({building:id,road,point})=>{
    if(maintenance?.mode){if(point)maintenance.mapClick(projection.unproject([point.x,point.y]),road);return;}
    if(id){selectedEvent=undefined;selectBuilding(id,'',false);}
  }});
  observer=new ResizeObserver(()=>drawAnnotations());observer.observe(svg);
  try {
    data=await context.api('/places');if(context.signal.aborted)return cleanup;
    container.querySelector('[data-gates]').innerHTML='<span>校门</span>'+data.buildings.filter(b=>b.kind==='gate').map(b=>`<button type="button" data-gate="${e(b.id)}" title="${e(b.address)}">${e(b.short_name)} <span>↗</span></button>`).join('');
    projection=projectCampus(data);resetView();drawMap();container.querySelector('[data-loading]').hidden=true;
    await Promise.all([loadDay(),loadNetwork()]);if(context.signal.aborted)return cleanup;
    const locationText=params.get('location'),match=matchLocation(locationText,data.buildings);if(match.status==='matched')selectBuilding(match.buildings[0].id,locationText);
  } catch(error){if(!context.signal.aborted)container.querySelector('[data-loading]').textContent=error.message||'地图读取失败，请重新打开页面。';}
  return cleanup;
}
