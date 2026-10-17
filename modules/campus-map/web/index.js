import {today, shiftDay, validDay, matchLocation, eventTime, projectCampus, buildingLabel, layoutLabels} from './locations.js';

const kinds = {class:'课程', deadline:'作业截止', exam:'考试', quiz:'Quiz', tutorial:'习题课', study:'学习', presentation:'展示', activity:'活动', lecture:'讲座', calendar:'校历'};
const notices = {missing:'尚未提供地点', unknown:'地点待确认，未在图上标记', ambiguous:'包含多个建筑，请选择具体地点'};

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css', import.meta.url), context.signal);
  let request, serial = 0, data, projection, schedule, selected, selectedEvent, layer = 'day', drag, moved = false, observer;
  const cleanup = () => {request?.abort();observer?.disconnect();removeStyle();container.classList.remove('campus-map','map-expanded');};
  context.signal.addEventListener('abort', cleanup, {once:true});
  container.classList.add('campus-map');
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  let day = validDay(params.get('date')) ? params.get('date') : today();
  let view;
  container.innerHTML = `<header class="map-heading"><div><span class="map-eyebrow">SHANGHAITECH · CAMPUS</span><h2>今天，去哪儿</h2><p>把每天的安排，放回校园里。</p></div><a class="button" href="https://map.shanghaitech.edu.cn/" target="_blank" rel="noopener noreferrer">学校官方地图 ↗</a></header>
    <div class="map-layout"><section class="map-panel" aria-label="校园建筑地图"><div class="map-tools"><div class="map-layers" aria-label="地图图层"><button type="button" data-layer="day" aria-pressed="true">当天地点</button><button type="button" data-layer="elevators" aria-pressed="false">电梯位置</button><button type="button" data-layer="gates" aria-pressed="false">出入口</button></div><label class="map-search-label"><span class="map-sr-only">搜索建筑或教室</span><input data-search type="search" placeholder="搜索建筑 / 教室，如信息学院1D-102" autocomplete="off"></label></div><div data-results class="map-search-results" hidden></div>
    <div class="map-canvas"><div data-loading class="map-loading" role="status">正在读取校园建筑图…</div><svg data-map aria-label="上海科技大学建筑地图，可用方向键平移、加减号缩放" tabindex="0" role="group"></svg><span class="map-north" aria-hidden="true">↑<small>北 N</small></span><button class="map-expand" type="button" data-expand aria-expanded="false">⤢ 展开地图</button><span class="map-gesture-hint">拖动浏览 · 放大查看更多楼名</span><div class="map-zoom" aria-label="地图缩放"><button type="button" data-zoom="in" aria-label="放大地图">＋</button><button type="button" data-zoom="out" aria-label="缩小地图">−</button><button type="button" data-zoom="reset">全图</button></div><a class="map-attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">道路与绿地 © OpenStreetMap contributors</a></div>
    <div class="map-legend"><span class="map-key map-key-teaching">教学科研</span><span class="map-key map-key-sport">运动场馆</span><span class="map-key map-key-service">生活服务</span><span class="map-key map-key-road">道路</span><span class="map-key map-key-path">步行道</span></div><div class="map-gates" data-gates aria-label="校园出入口"></div><div data-detail class="map-detail" aria-live="polite"><h3>校园里的下一站</h3><p>选择一项安排，或搜索建筑名称。地图标记对应整栋建筑，教室与电梯的楼内位置见详情。</p></div></section>
    <aside class="map-agenda"><div class="map-agenda-heading"><div><span class="map-eyebrow">YOUR DAY</span><h3>当天安排</h3></div><a href="#timetable">时间表 ↗</a></div><div class="map-date"><button class="button" type="button" data-day="prev" aria-label="前一天">‹</button><input data-date type="date" aria-label="查看日期" value="${e(day)}"><button class="button" type="button" data-day="next" aria-label="后一天">›</button><button class="button" type="button" data-day="today">今天</button></div><div data-agenda aria-live="polite"></div></aside></div>
    <footer class="map-source">建筑与 5 处校门来自学校官方地图；道路、水系与绿地来自 OpenStreetMap · 资料收录 2026-10-17。道路仅供方位参考，开放情况以现场为准。电梯资料覆盖 2 栋建筑、3 条位置说明。</footer>`;
  const svg = container.querySelector('[data-map]'), agenda = container.querySelector('[data-agenda]'), detail = container.querySelector('[data-detail]');
  const on = (node, name, handler) => node.addEventListener(name, handler, {signal:context.signal});
  const buildingById = id => data.buildings.find(item => item.id === id);
  const entries = () => (schedule?.events || []).map((item, index) => ({item, index, match:matchLocation(item.location, data.buildings)}));
  function setView() {if(view){svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`);drawAnnotations();}}
  function resetView() {if (!projection) return;view={x:0,y:0,w:projection.width,h:projection.height};setView();}
  function zoom(factor) {
    if (!view) return;
    const w = Math.min(projection.width*1.2, Math.max(projection.width/5,view.w*factor)), h = w*projection.height/projection.width;
    view={x:view.x+(view.w-w)/2,y:view.y+(view.h-h)/2,w,h};setView();
  }
  function mapMarks() {
    const marks = new Map();
    if(layer === 'elevators') for(const item of data.elevators) marks.set(item.building_id, '↕');
    else if(layer==='day')for(const {index,match} of entries()) if(match.status === 'matched') {const id=match.buildings[0].id;marks.set(id, [...(marks.get(id)||[]),index+1]);}
    return marks;
  }
  const primaryNames = ['图书馆','教学中心','体育馆','生命学院','信息学院1号楼','信息学院2号楼','信息学院3号楼','创意与艺术学院','数学科学研究所','行政中心','创业与管理学院','体育场','游泳馆','会议中心','H1,校园服务中心,309室 IT服务中心','H2楼,学生科创中心'];
  function drawAnnotations() {
    const host=svg.querySelector('[data-annotations]');if(!host||!projection||!view)return;
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
  }
  function drawMap() {
    if (!data) return;
    const marks=mapMarks(),basemap=data.basemap||{roads:[],landscape:[]};
    const roadMarkup=basemap.roads.map(road=>`<polyline class="map-road ${road.type==='footway'?'is-footway':''}" points="${projection.polygon(road.points)}"/>`).join('');
    svg.innerHTML=`<polygon class="map-boundary" points="${projection.polygon(data.campus.polygon)}"/><g class="map-landscape">${basemap.landscape.map(item=>item.polygon?`<polygon class="map-land-${e(item.kind)}" points="${projection.polygon(item.polygon)}"/>`:`<polyline class="map-land-waterway" points="${projection.polygon(item.points)}"/>`).join('')}</g><g class="map-road-casings">${roadMarkup}</g><g class="map-road-surfaces">${roadMarkup}</g><g class="map-buildings">`+data.buildings.filter(b=>b.kind!=='gate').map(building=>`<g data-building="${e(building.id)}" role="button" tabindex="0" aria-label="${e(building.name)}" aria-pressed="${selected===building.id}" class="map-building category-${e(building.category)}${selected===building.id?' is-selected':''}${marks.has(building.id)?' is-marked':''}"><title>${e(building.name)}</title><polygon points="${projection.polygon(building.polygon)}"/></g>`).join('')+'</g><g data-annotations></g>';
    drawAnnotations();
  }
  function renderAgenda() {
    if (!schedule) return;
    const items=entries();
    agenda.innerHTML = `${schedule.issues?.length ? `<p class="map-notice">${e(schedule.issues.join('；'))}</p>`:''}${schedule.status==='partial' ? '<p class="map-notice">部分来源尚未就绪，以下为当前可用安排。</p>':''}<p class="map-day-summary">${e(new Intl.DateTimeFormat('zh-CN',{weekday:'long',timeZone:'Asia/Shanghai'}).format(new Date(day+'T12:00:00+08:00')))} · ${items.length} 项安排 · ${items.filter(v=>v.match.status==='matched').length} 项已定位</p>${items.length ? '<ol class="map-events">'+items.map(({item,index,match})=>`<li><button type="button" data-event="${index}" class="map-event${selectedEvent===item.id?' is-active':''}"><span class="map-event-number${match.status==='matched'?'':' is-unlocated'}">${index+1}</span><span class="map-event-body"><span class="map-event-time">${e(eventTime(item))}</span><strong>${e(item.title||item.course_title||'未命名安排')}</strong><span>${e(item.location||'尚未提供地点')}</span><small>${e(kinds[item.event_type]||'安排')}${item.status==='rescheduled'?' · 调课后':''}${match.status==='matched'?' · 点击定位':' · '+e(notices[match.status])}</small></span></button></li>`).join('')+'</ol>':`<div class="map-empty"><span aria-hidden="true">${schedule.available?'☀':'⌖'}</span><h3>${schedule.available?'这一天暂无安排':'日程暂不可用'}</h3><p>${schedule.available?'可以切换日期查看课程，或在校园地图中寻找地点。':'校园建筑与电梯资料仍可查看。可到设置检查时间表模块。'}</p></div>`}`;
  }
  function renderDetail(locationText='') {
    const building=buildingById(selected);
    if(!building) {detail.innerHTML='<h3>校园里的下一站</h3><p>选择一项安排，或搜索建筑名称。地图标记对应整栋建筑，教室与电梯的楼内位置见详情。</p>';return;}
    const elevators=data.elevators.filter(item=>item.building_id===selected);
    detail.innerHTML=`<div class="map-detail-heading"><div><span class="map-eyebrow">${building.kind==='gate'?'校园出入口':e(building.category_label)}</span><h3>${e(building.short_name||building.name)}</h3></div><a href="${e(building.source_url)}" target="_blank" rel="noopener noreferrer">官方地图 / 导航 ↗</a></div>${building.address?`<p class="map-room">${e(building.address)}</p>`:''}${locationText?`<p class="map-room">教室 / 地点：<strong>${e(locationText)}</strong></p>`:''}<p class="map-detail-hint">${building.kind==='gate'?'校门位置来自学校官方地图，人员与车辆通行安排以现场管理为准。':'已定位到建筑。具体入口和楼内走法请以现场指引为准。'}</p>${elevators.length?'<div class="map-elevators"><h4>↕ 电梯位置说明</h4>'+elevators.map(item=>`<article><strong>${e(item.floor)} · ${e(item.name)}</strong><p>${e(item.location)}</p><a href="${e(item.source_url)}" target="_blank" rel="noopener noreferrer">${e(item.source_title)} ↗</a></article>`).join('')+'<p class="map-detail-hint">图上标记属于整栋建筑，楼内位置以文字说明为准；未核实当前开放状态。</p></div>':layer==='elevators'?'<p class="map-notice">这栋建筑暂未收录有出处的电梯位置资料。</p>':''}`;
  }
  function selectBuilding(id, locationText='', focus=true) {
    selected=id;const building=buildingById(id);if(!building)return;
    if(focus) {const [x,y]=projection.center(building.polygon),w=projection.width/2,h=projection.height/2;view={x:x-w/2,y:y-h/2,w,h};setView();}
    drawMap();renderDetail(locationText);renderAgenda();
  }
  function selectEvent(index) {
    const entry=entries()[index];if(!entry)return;selectedEvent=entry.item.id;
    if(entry.match.status==='matched') selectBuilding(entry.match.buildings[0].id,entry.item.location);
    else {selected=undefined;drawMap();renderAgenda();detail.innerHTML=`<h3>${e(entry.item.title||'安排地点')}</h3><p>${e(entry.item.location||'尚未提供地点')}</p><p class="map-notice">${e(notices[entry.match.status])}</p>${entry.match.buildings.map(b=>`<button class="button" data-candidate="${e(b.id)}" type="button">${e(b.name)}</button>`).join('')}`;}
    if(matchMedia('(max-width:1100px)').matches) container.querySelector(entry.match.status==='matched'?'.map-canvas':'.map-detail').scrollIntoView({block:'center'});
  }
  async function loadDay() {
    request?.abort();request=new AbortController();const ticket=++serial;
    schedule=undefined;selectedEvent=undefined;selected=undefined;
    drawMap();renderDetail();agenda.innerHTML='<p class="map-notice" role="status">正在读取当天安排…</p>';
    try {
      const value=await context.api('/day?date='+encodeURIComponent(day),{signal:request.signal});
      if(context.signal.aborted||ticket!==serial)return;
      schedule=value;renderAgenda();drawMap();
      const target=params.get('event');if(target){const index=entries().findIndex(v=>v.item.id===target);if(index>=0)selectEvent(index);params.delete('event');}
    } catch(error) {if(context.signal.aborted||ticket!==serial)return;agenda.innerHTML=`<p class="map-notice">${e(error.message||'当天安排读取失败')}</p><button class="button" type="button" data-retry>重新读取</button>`;}
  }
  on(container,'click',event=>{
    if(!data)return;
    const button=event.target.closest('button,a,[data-building]');if(!button)return;
    if(button.dataset.layer){layer=button.dataset.layer;container.querySelectorAll('[data-layer]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));drawMap();if(layer==='gates'){selectedEvent=undefined;resetView();selectBuilding(data.buildings.find(b=>b.kind==='gate').id,'',false);}else if(layer==='elevators'&&!selected)selectBuilding(data.elevators[0].building_id,'',false);else renderDetail();}
    if(button.hasAttribute('data-expand')){const expanded=container.classList.toggle('map-expanded');button.setAttribute('aria-expanded',String(expanded));button.textContent=expanded?'⤡ 收起地图':'⤢ 展开地图';}
    if(button.dataset.gate){selectedEvent=undefined;selectBuilding(button.dataset.gate);}
    if(button.dataset.zoom){if(button.dataset.zoom==='reset')resetView();else zoom(button.dataset.zoom==='in'?.75:1.333);}
    if(button.hasAttribute('data-event'))selectEvent(Number(button.dataset.event));
    if(button.dataset.building&&!moved){selectedEvent=undefined;selectBuilding(button.dataset.building,'',false);}
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
    const building=event.target.closest('[data-building]');
    if(building&&['Enter',' '].includes(event.key)){event.preventDefault();selectedEvent=undefined;selectBuilding(building.dataset.building,'',false);return;}
    if(['+','=','-','0','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();if(['+','='].includes(event.key))zoom(.75);else if(event.key==='-')zoom(1.333);else if(event.key==='0')resetView();else {view.x+=({'ArrowLeft':-1,'ArrowRight':1}[event.key]||0)*view.w*.08;view.y+=({'ArrowUp':-1,'ArrowDown':1}[event.key]||0)*view.h*.08;setView();}}
  });
  on(svg,'pointerdown',event=>{if(!view||event.button!==0)return;moved=false;drag={id:event.pointerId,x:event.clientX,y:event.clientY,view:{...view},building:event.target.closest('[data-building]')?.dataset.building};svg.setPointerCapture(event.pointerId);});
  on(svg,'pointermove',event=>{if(!drag||drag.id!==event.pointerId)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(Math.hypot(dx,dy)>4)moved=true;const rect=svg.getBoundingClientRect(),scale=Math.max(drag.view.w/rect.width,drag.view.h/rect.height);view={...drag.view,x:drag.view.x-dx*scale,y:drag.view.y-dy*scale};setView();});
  const release=event=>{if(drag?.id===event.pointerId){const id=drag.building;if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);drag=undefined;if(id&&!moved&&event.type==='pointerup'){selectedEvent=undefined;selectBuilding(id,'',false);}}};
  on(svg,'pointerup',release);on(svg,'pointercancel',release);
  observer=new ResizeObserver(()=>drawAnnotations());observer.observe(svg);
  try {
    data=await context.api('/places');if(context.signal.aborted)return cleanup;
    container.querySelector('[data-gates]').innerHTML='<span>校门</span>'+data.buildings.filter(b=>b.kind==='gate').map(b=>`<button type="button" data-gate="${e(b.id)}" title="${e(b.address)}">${e(b.short_name)} <span>↗</span></button>`).join('');
    projection=projectCampus(data);resetView();drawMap();container.querySelector('[data-loading]').hidden=true;
    await loadDay();if(context.signal.aborted)return cleanup;
    const locationText=params.get('location'),match=matchLocation(locationText,data.buildings);if(match.status==='matched')selectBuilding(match.buildings[0].id,locationText);
  } catch(error){if(!context.signal.aborted)container.querySelector('[data-loading]').textContent=error.message||'地图读取失败，请重新打开页面。';}
  return cleanup;
}
