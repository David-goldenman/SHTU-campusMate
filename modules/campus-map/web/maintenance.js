import {today,shiftDay,buildingLabel} from './locations.js';
import {conditionPhase,phaseLabels,conditionHitsEdge,conditionPlaceIds} from './conditions.js';

const sourceLabels={official:'校方通知',onsite:'现场核实',report:'使用者线索'};
export function createMaintenance({context,host,statusHost,data,graph,getDay,onUpdate,focusMap,redraw}) {
  const e=context.ui.escape,on=(node,type,fn)=>node.addEventListener(type,fn,{signal:context.signal});
  let snapshot,ready=false,loading=false,busy=false,draft,editing,mode,corner,showRetired=false,message='',controller,ticket=0;
  context.signal.addEventListener('abort',()=>controller?.abort(),{once:true});
  const place=id=>data.buildings.find(b=>b.id===id);
  const fields=['title','state','effect','scope','place_id','edge_keys','bounds','starts_on','expected_end','review_on','source_kind','source_title','source_date','source_url','note'];
  const targetLabel=item=>item.scope==='place'?(place(item.place_id)?buildingLabel(place(item.place_id)):'地点已变化'):item.scope==='edges'?`${item.edge_keys.length} 段道路`:'圈选区域';
  const selectOptions=(values,current)=>Object.entries(values).map(([value,label])=>`<option value="${e(value)}"${value===current?' selected':''}>${e(label)}</option>`).join('');
  function newDraft() {return {title:'',state:'pending',effect:'blocked',scope:'place',place_id:'',edge_keys:[],bounds:[],starts_on:today(),expected_end:null,review_on:shiftDay(today(),7),source_kind:'report',source_title:'',source_date:today(),source_url:'',note:''};}
  function status() {
    if(!ready){statusHost.innerHTML=`<p>${loading?'正在读取通行维护记录…':'通行维护记录暂不可用，暂不生成路线。'}${loading?'':' <button type="button" data-condition-reload>重试</button>'}</p>`;return;}
    const rows=snapshot.items.map(item=>({item,phase:conditionPhase(item,getDay())}));
    const confirmed=rows.filter(r=>['confirmed','review_due'].includes(r.phase)&&r.item.effect==='blocked').length;
    const pending=rows.filter(r=>r.phase.startsWith('pending')).length,due=rows.filter(r=>r.phase.endsWith('due')).length;
    statusHost.innerHTML=`<p><strong>通行信息 · ${e(getDay())}</strong><span>已确认限制 ${confirmed} · 待核实 ${pending}${due?' · 需复核 '+due:''}</span><button type="button" data-condition-open>维护 / 复核 ↗</button></p><small>依据已收录信息规划；没有记录不代表已确认畅通。</small>`;
  }
  function editor() {
    if(!draft)return '<button class="button" type="button" data-condition-new>＋ 记录施工或通行情况</button>';
    const impacts=draft.scope==='place'?0:graph.edges.filter(edge=>conditionHitsEdge(draft,edge)).length;
    const affectedPlaces=conditionPlaceIds(draft,data.buildings).length;
    const input=(name,label,type='text',extra='')=>`<label>${label}<input name="${name}" type="${type}" value="${e(draft[name]||'')}" ${extra}></label>`;
    return `<form data-condition-form><fieldset ${busy?'disabled':''}><legend>${editing?'编辑 / 复核记录':'新增通行记录'}</legend><div class="map-condition-fields">${input('title','标题','text','required maxlength="80"')}<label>状态<select aria-label="状态" name="state">${selectOptions({pending:'待核实线索',confirmed:'已确认限制',resolved:'已确认恢复',withdrawn:'撤回错误记录'},draft.state)}</select></label><label>步行影响<select aria-label="步行影响" name="effect">${selectOptions({blocked:'封闭 / 不能步行通行',caution:'提醒注意，仍可通行'},draft.effect)}</select></label><label>影响范围<select aria-label="影响范围" name="scope">${selectOptions({place:'校门或建筑',edges:'地图选择路段',area:'地图圈选区域'},draft.scope)}</select></label></div>
      ${draft.scope==='place'?`<label>选择校门 / 建筑<select aria-label="选择校门 / 建筑" name="place_id" required><option value="">请选择</option>${data.buildings.map(b=>`<option value="${e(b.id)}"${b.id===draft.place_id?' selected':''}>${e(buildingLabel(b))}</option>`).join('')}</select></label><p class="map-condition-hint">限制该地点作为起终点；周边道路施工请选路段或圈选区域。</p>`:`<div class="map-condition-pick"><button type="button" data-condition-pick>${draft.scope==='edges'?'在地图选择路段':'在地图圈选区域'}</button><button type="button" data-condition-finish>结束选取</button><button type="button" data-condition-clear-target>清空范围</button><span>${draft.scope==='edges'?`已选 ${draft.edge_keys.length} 段道路`:draft.bounds.length?'已圈选区域':'尚未圈选'} · 影响 ${impacts} 段道路 / ${affectedPlaces} 处地点</span></div>`}
      <p class="map-condition-hint">${mode==='edges'?'点选地图中的道路，可再次点击取消；完成后点“结束选取”。':mode==='area'?(corner?'再点选矩形范围的另一角。':'在地图点击施工范围的两个对角点。'):'保存后才会影响路线。只记录对行人的影响，不把机动车管制当作步行封闭。'}</p>
      <div class="map-condition-fields">${input('starts_on','开始日期','date','required')}${input('expected_end','预计结束（可空）','date')}${input('review_on','下次复核日期','date','required')}<label>依据类型<select aria-label="依据类型" name="source_kind">${selectOptions(sourceLabels,draft.source_kind)}</select></label>${input('source_title','通知标题 / 核实说明','text','required maxlength="160"')}${input('source_date','来源日期','date','required')}${input('source_url','原文链接（校方通知必填）','url','maxlength="1500"')}</div>
      <label>位置、行人影响与复核依据<textarea aria-label="位置、行人影响与复核依据" name="note" rows="3" maxlength="800" required>${e(draft.note)}</textarea></label><p class="map-condition-hint">预计结束日不会自动解除已确认封闭；确认恢复时填写新的现场或通知依据。</p><div class="map-condition-actions"><button class="button" type="submit">${busy?'正在保存…':'保存记录'}</button><button type="button" data-condition-cancel>取消编辑</button></div></fieldset></form>`;
  }
  function render() {
    status();
    const allItems=snapshot?.items||[],items=allItems.filter(item=>showRetired||!['resolved','withdrawn'].includes(item.state));
    host.innerHTML=`<p class="map-condition-intro">维护施工、封路与入口情况，记录保存在本机当前账号。黄色为待核实，红色为已确认限制；复核到期不会自动宣布恢复通行。</p>${message?`<p class="map-condition-message" role="status">${e(message)}</p>`:''}<div class="map-condition-toolbar"><button type="button" data-condition-reload ${busy?'disabled':''}>刷新记录</button><button type="button" data-condition-undo ${!snapshot?.undo_available||busy?'disabled':''}>撤销上次修改</button></div>${ready?editor():''}<label class="map-condition-show-retired"><input type="checkbox" data-condition-retired ${showRetired?'checked':''}>显示已恢复 / 撤回记录（${allItems.filter(i=>['resolved','withdrawn'].includes(i.state)).length}）</label><div class="map-condition-list">${items.map(item=>{
      const phase=conditionPhase(item,getDay()),retired=['resolved','withdrawn'].includes(phase),color=item.state==='pending'?'pending':retired?'retired':item.effect==='caution'?'caution':'confirmed';
      return `<article class="map-condition-item is-${color}"><div><strong>${e(item.title)}</strong><span>${e(phase==='review_due'&&item.effect==='caution'?'需复核 · 保持提醒':phaseLabels[phase])}</span></div><p>${e(targetLabel(item))} · ${item.effect==='blocked'?(item.state==='pending'?'疑似步行限制':'步行限制'):'通行提醒'} · 开始 ${e(item.starts_on)} · 复核 ${e(item.review_on)}${item.expected_end?' · 预计结束 '+e(item.expected_end):''}</p><p>${e(item.note)}</p><small>${e(sourceLabels[item.source_kind])} · ${e(item.source_title)} · ${e(item.source_date)}${item.source_url?` · <a href="${e(item.source_url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>`:''}</small><button type="button" data-condition-edit="${e(item.id)}" ${busy?'disabled':''}>编辑 / 复核</button></article>`;
    }).join('')||'<p>暂无通行记录；这不代表校园各处已经核实开放。</p>'}</div><details class="map-condition-history"><summary>修改记录（最近 ${snapshot?.history.length||0} 次，最多保留 200 次）</summary><ol>${(snapshot?.history||[]).map(h=>`<li>${e(h.at.slice(0,16).replace('T',' '))} · ${e(h.action)} · ${e(h.title)}</li>`).join('')}</ol></details>`;
  }
  async function load() {
    controller?.abort();controller=new AbortController();const current=++ticket;loading=true;ready=false;render();onUpdate();
    try {const value=await context.api('/conditions',{signal:controller.signal});if(context.signal.aborted||current!==ticket)return;snapshot=value;ready=true;message=draft?'记录已刷新，当前表单已保留；请对照新记录确认后再保存。':'';}
    catch(error){if(context.signal.aborted||current!==ticket)return;message=error.message||'维护记录读取失败。';}
    if(context.signal.aborted||current!==ticket)return;loading=false;render();onUpdate();
  }
  async function write(path,method,item) {
    if(!ready||busy)return;busy=true;message='';render();
    try {
      const value=await context.api(path,{method,body:{version:snapshot.version,account_revision:snapshot.account_revision,...(item?{item}:{})}});
      if(context.signal.aborted)return;snapshot=value;draft=editing=mode=corner=undefined;message='已保存，路线已按最新通行记录更新。';
    } catch(error){if(context.signal.aborted)return;message=(error.message||'保存失败。')+' 当前表单已保留；版本冲突时请先刷新记录。';}
    if(context.signal.aborted)return;busy=false;render();onUpdate();
  }
  function finish() {mode=corner=undefined;render();redraw();host.querySelector('form')?.scrollIntoView({block:'start'});}
  function open() {host.closest('details').open=true;host.scrollIntoView({block:'start'});}
  async function click(event) {
    const button=event.target.closest('button');if(!button)return;
    if(button.hasAttribute('data-condition-open'))open();
    if(button.hasAttribute('data-condition-reload'))void load();
    if(button.hasAttribute('data-condition-new')){draft=newDraft();editing=mode=corner=undefined;message='';render();}
    if(button.dataset.conditionEdit){const item=snapshot.items.find(i=>i.id===button.dataset.conditionEdit);draft=Object.fromEntries(fields.map(key=>[key,structuredClone(item[key])]));editing=item.id;mode=corner=undefined;message='';render();host.querySelector('form').scrollIntoView({block:'start'});}
    if(button.hasAttribute('data-condition-cancel')){draft=editing=mode=corner=undefined;message='';render();redraw();}
    if(button.hasAttribute('data-condition-pick')&&draft){mode=draft.scope;corner=undefined;if(mode==='area')draft.bounds=[];render();redraw();focusMap();}
    if(button.hasAttribute('data-condition-finish'))finish();
    if(button.hasAttribute('data-condition-clear-target')&&draft){draft.edge_keys=[];draft.bounds=[];corner=undefined;render();redraw();}
    if(button.hasAttribute('data-condition-undo'))void write('/conditions/undo','POST');
  }
  on(host,'click',click);on(statusHost,'click',click);
  on(host,'input',event=>{
    const field=event.target.name;if(!draft||!fields.includes(field))return;
    draft[field]=field==='expected_end'?(event.target.value||null):event.target.value;
  });
  on(host,'change',event=>{
    if(event.target.hasAttribute('data-condition-retired')){showRetired=event.target.checked;render();return;}
    if(!draft)return;
    if(event.target.name==='scope'){draft.scope=event.target.value;draft.place_id='';draft.edge_keys=[];draft.bounds=[];mode=corner=undefined;render();redraw();}
  });
  on(host,'submit',event=>{if(!event.target.matches('[data-condition-form]'))return;event.preventDefault();void write(editing?'/conditions/'+encodeURIComponent(editing):'/conditions',editing?'PUT':'POST',draft);});
  function mapClick(point,key) {
    if(!draft||!mode)return;
    if(mode==='edges'&&key){draft.edge_keys=draft.edge_keys.includes(key)?draft.edge_keys.filter(k=>k!==key):[...draft.edge_keys,key].slice(0,100);}
    else if(mode==='area') {if(!corner)corner=point;else {draft.bounds=[Math.min(corner[0],point[0]),Math.min(corner[1],point[1]),Math.max(corner[0],point[0]),Math.max(corner[1],point[1])];mode=corner=undefined;}}
    render();redraw();
  }
  function overlay(projection,showPending=false) {
    const rows=(snapshot?.items||[]).filter(item=>!['scheduled','resolved','withdrawn'].includes(conditionPhase(item,getDay()))&&(showPending||item.state==='confirmed'));
    function shape(item,extra='') {
      const kind=item.state==='pending'?'pending':item.effect==='caution'?'caution':'confirmed',className='map-condition-shape is-'+kind+' '+extra;
      if(item.scope==='place'){const b=place(item.place_id);return b?`<polygon class="${className}" points="${projection.polygon(b.polygon)}"><title>${e(item.title)}</title></polygon>`:'';}
      if(item.scope==='area'&&item.bounds.length===4){const [a,b,c,d]=item.bounds;return `<polygon class="${className}" points="${projection.polygon([[a,b],[c,b],[c,d],[a,d]])}"><title>${e(item.title)}</title></polygon>`;}
      return item.scope==='edges'?graph.edges.filter(edge=>item.edge_keys.includes(edge.key)).map(edge=>`<polyline class="${className} is-road" points="${projection.polygon([edge.p,edge.q])}"><title>${e(item.title)}</title></polyline>`).join(''):'';
    }
    let html=rows.map(item=>shape(item)).join('');
    if(draft)html+=shape({...draft,state:'pending',title:'正在编辑的范围'},'is-preview');
    if(mode==='edges')html+=graph.edges.map(edge=>`<polyline data-maint-road="${e(edge.key)}" role="button" tabindex="0" aria-label="选择${e(edge.tags.name||'校内道路')}，约${Math.round(edge.length)}米" class="map-condition-pick-road${draft.edge_keys.includes(edge.key)?' is-picked':''}" points="${projection.polygon([edge.p,edge.q])}"/>`).join('');
    if(corner){const [x,y]=projection.point(corner);html+=`<circle class="map-condition-corner" cx="${x}" cy="${y}" r="6"/>`;}
    return html;
  }
  render();
  return {load,render,status,overlay,mapClick,open,finish,get mode(){return mode;},get ready(){return ready;},get snapshot(){return snapshot;}};
}
