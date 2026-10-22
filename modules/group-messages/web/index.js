import {qqConnection} from './qq-connection.js';

const names = {wechat:'微信', qq:'QQ'};
const kinds = {assignment:'作业',quiz:'Quiz',exam:'考试',class_change:'课程变更',activity:'活动',material:'资料',notice:'通知'};
const statuses = {pending:'待核实',accepted:'已确认',applied:'已更新',dismissed:'已忽略'};
const phases = {working:'处理中',copying:'读取本机副本',decrypting:'校验并解密',selecting_groups:'整理所选群'};

export async function mount(container, context) {
  const e = context.ui.escape, signal = context.signal;
  const removeStyle = context.ui.useStyle(new URL('./styles.css', import.meta.url), signal);
  let timer, stopped=false, serial=0, state, courses=[], courseMatches={}, catalogSignature='', courseMessage='', items=[], itemSignature='', filter='pending';
  let qqAddress;
  const drafts = new Map(), dirty = new Set(), rendered = new Map(), coverageRendered = new Map();
  const saving = new Set(), selectionFeedback = new Map();
  const dialog = document.createElement('dialog');
  dialog.className='group-dialog';
  const cleanup=()=>{stopped=true;serial++;clearTimeout(timer);dialog.close();dialog.remove();removeStyle();container.classList.remove('group-messages');};
  signal.addEventListener('abort',cleanup,{once:true});
  container.classList.add('group-messages');
  container.innerHTML=`<header class="gm-header"><div><h2>来源与选群</h2><p>只同步本学期课程群。自动匹配课程名称，关联结果可自行修正。</p></div><div class="gm-header-actions"><button type="button" class="button button-secondary" data-refresh>刷新</button><button type="button" class="button button-secondary" data-stop hidden>停止当前处理</button></div></header>
    <p class="gm-feedback" role="status" aria-live="polite" data-feedback></p>
    <div class="gm-overview" data-overview></div>
    <div class="gm-sources"><section class="gm-source panel" data-source="wechat"></section><section class="gm-source panel" data-source="qq"></section></div>
    <section class="gm-results"><div class="gm-results-heading"><div><p class="gm-eyebrow">有依据，也可以撤销</p><h2>提取的事项</h2></div><a href="#notifications">通知中心 ↗</a></div>
      <div class="gm-filters" role="group" aria-label="事项状态">${['pending','accepted','applied','dismissed','all'].map(value=>`<button type="button" data-filter="${value}" aria-pressed="${value===filter}">${statuses[value]||'全部'}</button>`).join('')}</div><div data-items></div></section>
    <footer class="gm-footnote">本机服务运行时持续检查，电脑休眠或服务退出期间无法采集。每次同步更新近 7／30 天的聊天窗口；已提取事项及引用保留至清除模块数据。图片、语音和附件正文暂未读取。</footer>`;
  container.append(dialog);
  const api=(path,options={})=>context.api(path,{...options,signal});
  const on=(target,event,handler)=>target.addEventListener(event,handler,{signal});
  const date=value=>value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'尚未同步';
  const feedback=(text,error=false)=>{if(stopped)return;const node=container.querySelector('[data-feedback]');node.textContent=text;node.classList.toggle('gm-error',error);};
  const card=source=>container.querySelector(`[data-source="${source}"]`);
  const call=async(fn)=>{try{await fn();}catch(error){if(!signal.aborted)feedback(error.message||'操作未完成，请重试。',true);}};

  function draftFor(source) {
    if(!drafts.has(source))drafts.set(source,new Map((state.sources[source].selected||[]).map(row=>[row.id,structuredClone(row)])));
    return drafts.get(source);
  }
  function groupOptions(value) {
    const missing=value&&!courses.some(row=>row.id===value);
    return `<option value="">请选择本学期课程</option>${missing?`<option value="${e(value)}" selected disabled>原关联失效，请重新选择</option>`:''}${courses.map(row=>`<option value="${e(row.id)}" ${row.id===value?'selected':''}>${e(row.title)}${row.code?' · '+e(row.code):''}</option>`).join('')}`;
  }
  function updateSelection(source) {
    const root=card(source), form=root.querySelector('[data-selection]');
    if(!form)return;
    const changed=dirty.has(source), busy=saving.has(source), count=draftFor(source).size;
    const message=selectionFeedback.get(source), status=form.querySelector('[data-save-status]');
    status.textContent=busy?'正在保存…':message?.text||(changed?`有未保存的修改 · 已选 ${count} 个群`:`已保存 ${count} 个群的关联`);
    status.classList.toggle('gm-error',!!message?.error);
    status.classList.toggle('gm-unsaved',changed&&!message?.error);
    const save=form.querySelector('[data-save-selection]');
    save.disabled=busy||(!changed&&(!count||state.sources[source].enabled));
    save.textContent=busy?'正在保存…':!changed&&count&&!state.sources[source].enabled?'开启同步':'保存关联';
    form.querySelector('[data-reset-selection]').hidden=!changed;
    form.querySelector('[data-reset-selection]').disabled=busy;
    form.querySelector('[data-selection-fields]').disabled=busy;
    for(const button of form.querySelectorAll('[data-pause],[data-sync]'))button.disabled=changed;
    for(const row of form.querySelectorAll('[data-gid]')){
      const selected=draftFor(source).get(row.dataset.gid), valid=!selected||courses.some(course=>course.id===selected.course_id);
      row.classList.toggle('gm-selected',!!selected);
      row.querySelector('[data-course]').disabled=!selected;
      row.querySelector('[data-course]').setAttribute('aria-invalid',String(!valid));
      row.querySelector('[data-group-settings]').disabled=!selected;
      // Raw-message actions operate on the saved selection, never on a draft.
      const saved=state.sources[source].selected?.some(value=>value.id===row.dataset.gid);
      for(const button of row.querySelectorAll('[data-senders],[data-messages],[data-extract]')){
        button.disabled=!saved||changed;
        button.title=!saved||changed?'请先保存关联，再使用此操作':'';
      }
    }
  }
  function markDirty(source) {
    dirty.add(source);selectionFeedback.delete(source);updateSelection(source);
  }
  async function saveSelection(source, form) {
    if(saving.has(source))return;
    const groups=[...draftFor(source).values()].map(({id,course_id,trusted_senders,auto_extract,auto_apply})=>({id,course_id,trusted_senders,auto_extract,auto_apply}));
    const invalid=groups.filter(row=>!courses.some(course=>course.id===row.course_id));
    if(invalid.length){
      selectionFeedback.set(source,{text:`还有 ${invalid.length} 个已选群未关联本学期课程，请选择课程后保存。`,error:true});
      updateSelection(source);form.querySelector('[data-course][aria-invalid=true]')?.focus();return;
    }
    const body={expected_revision:rendered.get(source),groups,enabled:groups.length>0,
      interval_seconds:Number(form.elements.interval_seconds.value),history_days:Number(form.elements.history_days.value),allow_ai:form.elements.allow_ai.checked,
      confirm_compatible:!!form.elements.confirm_compatible?.checked};
    if(groups.some(row=>row.auto_extract)&&!body.allow_ai){
      selectionFeedback.set(source,{text:'开启自动提取前，请在“同步频率与 AI 设置”中确认正文发送范围。',error:true});
      form.querySelector('.gm-sync-settings').open=true;updateSelection(source);form.elements.allow_ai.focus();return;
    }
    const owner=state.account_revision;
    let written=false;
    saving.add(source);updateSelection(source);
    try{
      await api(`/sources/${source}`,{method:'PUT',body});
      written=true;
      if(stopped||owner!==state.account_revision)return;
      dirty.delete(source);
      selectionFeedback.set(source,{text:groups.length?`已保存 ${groups.length} 个群的关联，已开启同步。`:'已保存，已停止同步所有群。'});
      await refresh(true);
    }catch(error){
      if(!stopped&&owner===state.account_revision){
        selectionFeedback.set(source,{text:written?'关联已保存，状态暂时无法刷新，请稍后刷新核对。':`保存未完成：${error.message||'请重试。'} 你的修改仍保留在此页面。`,error:true});
        // A failed write must retain the user's draft for a retry.
        if(dirty.has(source))updateSelection(source);
      }
    }finally{
      saving.delete(source);if(!stopped)updateSelection(source);
    }
  }
  function renderGroups(source) {
    const root=card(source), config=state.sources[source], draftsForSource=draftFor(source);
    const expanded=new Set([...root.querySelectorAll('[data-gid] details[open]')].map(node=>node.closest('[data-gid]').dataset.gid));
    const scroll=root.querySelector('[data-groups]').scrollTop;
    const query=(root.querySelector('[data-group-search]')?.value||'').trim().toLowerCase();
    const showAll=root.querySelector('[data-show-all]')?.checked;
    const groups=(config.groups||[]).filter(row=>{
      const match=courseMatches[source]?.[row.id];
      return (showAll||draftsForSource.has(row.id)||['automatic','ambiguous'].includes(match?.status))&&(!query||row.name.toLowerCase().includes(query)||row.id.toLowerCase().includes(query));
    });
    groups.sort((a,b)=>Number(draftsForSource.has(b.id))-Number(draftsForSource.has(a.id)));
    root.querySelector('[data-groups]').innerHTML=groups.slice(0,100).map(row=>{
      const selected=draftsForSource.get(row.id), match=courseMatches[source]?.[row.id];
      const value=selected||{course_id:match?.course_id||''};
      const coverage=config.coverage?.[row.id];
      return `<article class="gm-group" data-gid="${e(row.id)}"><div class="gm-group-row"><label class="gm-check gm-group-title"><input type="checkbox" data-selected ${selected?'checked':''}><span><strong>${e(row.name)}</strong><small data-match-hint>${e(match?.reason||'可手动关联本学期课程')}</small></span></label>
        <label class="gm-course">关联课程<select data-course aria-label="${e(row.name)}的关联课程" ${selected?'':'disabled'}>${groupOptions(value.course_id)}</select></label></div>
        ${match?.status==='ambiguous'?`<p class="gm-hint">可能对应：${e(match.candidates.map(item=>item.title).join('、'))}</p>`:''}
        <details class="gm-group-details" ${expanded.has(row.id)?'open':''}><summary>自动整理与消息${value.auto_extract?' · 已启用自动提取':''}</summary><fieldset data-group-settings ${selected?'':'disabled'}><div class="gm-policy"><label class="gm-check"><input type="checkbox" data-auto-extract ${value.auto_extract?'checked':''}>自动提取相关信息</label><label class="gm-check"><input type="checkbox" data-auto-apply ${value.auto_apply?'checked':''}>符合规则时自动更新</label></div><div class="gm-group-actions"><button type="button" class="button button-secondary" data-senders>可信发送者 (${value.trusted_senders?.length||0})</button><button type="button" class="button button-secondary" data-messages>查看已同步消息</button><button type="button" class="button button-secondary" data-extract>整理一次</button></div><p class="gm-hint">群关联修改后，先保存再查看消息或整理。</p></fieldset>
        ${coverage?`<p class="gm-coverage ${coverage.possible_gap||coverage.error?'gm-warning':''}">${e(coverage.error|| (source==='qq'?(coverage.possible_gap?'历史可能有缺口；每轮补抓最近最多 100 条。':'已读取最近窗口，每轮最多 100 条；不代表完整历史。'):`范围为近 ${config.history_days} 天已落到本机的消息。`))}</p>`:''}</details></article>`;
    }).join('')||'<p class="gm-empty">没有匹配的群。</p>';
    root.querySelector('[data-group-count]').textContent=courseMessage||`本学期 ${courses.length} 门课程 · 已选 ${draftsForSource.size} 个群 · 显示 ${groups.length} 个${groups.length>100?'，请搜索缩小范围':''}`;
    coverageRendered.set(source,JSON.stringify(config.coverage));
    root.querySelector('[data-groups]').scrollTop=scroll;
    updateSelection(source);
  }
  function renderSource(source) {
    const root=card(source), config=state.sources[source];
    const search=root.querySelector('[data-group-search]')?.value||'', showAll=root.querySelector('[data-show-all]')?.checked;
    drafts.delete(source);
    const connection=source==='wechat'?`<form data-connect="wechat"><button type="button" class="button button-secondary" data-discover>检测本机微信</button><p class="gm-hint">Windows 本机实验读取，首次仅扫描你选定的本人微信实例；密钥由系统加密保存。</p><label>微信数据目录<input name="database_dir" autocomplete="off" placeholder="选择本人账号的 db_storage 文件夹" value="${e(config.database_dir||'')}"></label><div data-folders></div><label>微信主实例<select name="pid" required><option value="">先检测本机微信</option></select></label><label class="gm-check"><input name="consent" type="checkbox" required>我授权只读访问本人微信，用于整理随后选择的群聊；了解本机非官方读取可能受版本变化影响。</label><button class="button button-primary" type="submit">授权并读取群列表</button></form><details class="gm-snapshot"><summary>导入已有可读快照</summary><form data-snapshot><label>快照目录<input name="path" autocomplete="off" placeholder="包含 message/message_*.db 的目录" required></label><p class="gm-hint">接受已完成导出的微信 4 可读快照。选择后仅同步快照内的数据。</p><button class="button button-secondary" type="submit">检查并读取群列表</button></form></details>`:
      qqConnection({...config,base_url:qqAddress??config.base_url},e);
    root.innerHTML=`<div class="gm-source-heading"><h3>${names[source]}</h3><span class="gm-badge" data-source-state></span></div><p class="gm-hint" data-source-status></p><p class="gm-error" data-source-error></p><p class="gm-warning" data-course-warning hidden></p>
      <details class="gm-connect" ${config.connected?'':'open'}><summary>${config.connected?'重新连接 / 更换账号':'连接消息来源'}</summary>${connection}</details>
      ${config.connected?`<form data-selection="${source}"><div class="gm-save-bar"><div><strong data-save-status role="status" aria-live="polite"></strong><small>勾选群聊并核对课程，保存后开始同步所选群。</small></div><div class="gm-save-actions"><button type="button" class="button button-secondary" data-reset-selection hidden>撤销修改</button><button class="button button-primary" type="submit" data-save-selection>保存关联</button></div></div><fieldset data-selection-fields><div class="gm-selection-toolbar"><label class="gm-search">选择本学期课程群<input type="search" data-group-search placeholder="搜索群名称" autocomplete="off" value="${e(search)}"></label><button type="button" class="button button-secondary" data-select-matched>勾选已匹配课程群</button></div><div class="gm-list-meta"><p class="gm-hint" data-group-count></p><label class="gm-check"><input type="checkbox" data-show-all ${showAll?'checked':''}>显示其他群，手动关联</label></div><div class="gm-group-list" data-groups></div>
        <details class="gm-sync-settings" ${config.pending_version?'open':''}><summary>同步频率与 AI 设置</summary>
        <div class="gm-settings"><label>同步间隔<select name="interval_seconds">${(source==='wechat'?[300,900,1800]:[20,60,300,900]).map(value=>`<option value="${value}" ${value==config.interval_seconds?'selected':''}>${value<60?value+' 秒':value/60+' 分钟'}</option>`).join('')}</select></label><label>近期消息范围<select name="history_days"><option value="7" ${config.history_days===7?'selected':''}>7 天</option><option value="30" ${config.history_days===30?'selected':''}>30 天</option></select></label></div>
        <label class="gm-check"><input name="allow_ai" type="checkbox" ${config.allow_ai?'checked':''}>允许把所选群中需要整理的正文及相关前文发送至当前 AI 服务。</label><p class="gm-hint">自动更新仅适用于指定可信发送者、时间明确且无冲突的事项。活动需要确认参加，手动修改优先保留。</p>
        ${config.pending_version?`<p class="gm-warning">微信版本 ${e(config.pending_version)}：${config.compatible?'读取检查通过，等待确认恢复。':'尚未通过兼容性检查。'}</p>${config.compatible?'<label class="gm-check"><input name="confirm_compatible" type="checkbox">确认当前版本与所选群，恢复同步</label>':''}<button type="button" class="button button-secondary" data-compatibility>重新检查兼容性</button>`:''}
        </details><div class="gm-source-actions"><button type="button" class="button button-secondary" data-pause>暂停同步</button><button type="button" class="button button-secondary" data-sync>同步一次</button></div></fieldset></form><details class="gm-remove"><summary>连接管理</summary><p class="gm-hint">移除连接会停止读取并删除本模块的连接密钥，已生成的待办和日程仍可在对应页面管理。</p><button type="button" class="button button-secondary" data-forget>移除连接</button></details>`:''}`;
    rendered.set(source,config.revision||'empty');
    if(config.connected)renderGroups(source);
    updateSourceStatus(source);
  }
  function updateSourceStatus(source) {
    const config=state.sources[source], root=card(source);
    const blockedScope=config.course_scope&&!config.course_scope.active_group_ids.length;
    root.querySelector('[data-source-state]').textContent=!config.connected?'未连接':config.enabled?(blockedScope?'等待课程关联':'自动同步中'):'已暂停';
    root.querySelector('[data-source-status]').textContent=config.connected?`${config.account_label||names[source]} · 最近同步 ${date(config.last_synced_at)}${config.approved_version?' · 微信 '+config.approved_version:''}`:'选择自己的账号与需要整理的群，默认不读取任何群。';
    root.querySelector('[data-source-error]').textContent=config.error||'';
    const blocked=config.course_scope?.blocked_groups||[],warning=root.querySelector('[data-course-warning]');
    warning.hidden=!blocked.length;
    warning.textContent=blocked.length?`${blocked.length} 个已选群未关联可用的本学期课程，已暂停读取。请在下方修正关联或取消勾选。`:'';
    const connectionFeedback=root.querySelector('[data-connection-feedback]');
    if(connectionFeedback){
      const connecting=state.running?.source===source&&state.running?.kind==='connect';
      connectionFeedback.textContent=connecting?'正在验证连接口令和 QQ 登录状态…':config.error|| (config.connected?'已连接，请选择下方需要同步的群聊。':'连接时先验证 QQ 账号并读取群列表，保存选群后才开始同步。');
      connectionFeedback.classList.toggle('gm-error',!connecting&&!!config.error);
    }
    if(config.connected&&!dirty.has(source)&&coverageRendered.get(source)!==JSON.stringify(config.coverage))renderGroups(source);
  }
  function renderItems() {
    const opened=new Set([...container.querySelectorAll('[data-item] details[open]')].map(node=>node.closest('[data-item]').dataset.item));
    const visible=items.filter(item=>filter==='all'||item.status===filter);
    container.querySelector('[data-items]').innerHTML=visible.map(item=>{
      const canApply=!['question','uncertain'].includes(item.action), calendar=['quiz','exam','activity'].includes(item.kind)&&item.starts_at;
      return `<article class="gm-item panel" data-item="${e(item.id)}"><div class="gm-item-meta"><span class="gm-badge">${e(kinds[item.kind]||item.kind)}</span><span>${e(item.course?.title||'课程待关联')} · ${e(item.group_name)}</span><strong>${e(statuses[item.status])}</strong></div><h4>${e(item.title)}</h4><p class="gm-summary">${e(item.summary)}</p>
        ${item.due_at||item.starts_at||item.date?`<p class="gm-item-time">${item.due_at?'截止':item.starts_at?'开始':'日期'}：${e(item.due_at||item.starts_at?date(item.due_at||item.starts_at):item.date+'（具体时间待确认）')}${item.time_verified?'':' · 时间依据待核实'}</p>`:''}
        <p class="gm-hint">${e(item.reason||'')}${item.kind==='class_change'?' 课程变更可先加入待办，请在时间表核对具体课程与节次。':''}</p>
        ${item.apply_error||item.publish_error?`<p class="gm-warning">${e(item.apply_error||item.publish_error)}</p>`:''}
        <details ${opened.has(item.id)?'open':''}><summary>查看原文依据 (${item.citations.length})</summary>${item.citations.map(ref=>`<blockquote><p>${e(ref.quote)}</p><footer>${e(ref.sender_name||'发送者未知')} · ${ref.sent_at?e(date(ref.sent_at)):'原发送时间未知'}</footer></blockquote>`).join('')}</details>
        <div class="gm-item-actions">${item.status!=='dismissed'&&item.status!=='applied'?`<button type="button" class="button button-primary" data-decision="apply" ${canApply?'':'disabled'}>${item.kind==='activity'?'参加并加入日程':calendar?'确认并加入日程':['notice','material'].includes(item.kind)?'确认信息':'确认并加入待办'}</button>${!['notice','material'].includes(item.kind)?'<button type="button" class="button button-secondary" data-decision="accept">仅确认信息</button>':''}`:''}
        ${item.receipt?'<button type="button" class="button button-secondary" data-decision="undo">撤销上次更新</button>':''}${item.status!=='dismissed'?'<button type="button" class="button button-secondary" data-decision="dismiss">忽略</button>':''}<a href="${calendar?'#timetable':'#dashboard'}">${calendar?'时间表':'学习事务'} ↗</a></div></article>`;
    }).join('')||`<div class="gm-empty panel"><h4>${items.length?'这个分类暂无事项':'从一个课程群开始'}</h4><p>${items.length?'可切换其他状态查看。':'连接来源并保存选群后，先同步聊天，再开启自动整理或点击“整理一次”。'}</p></div>`;
  }
  function overview() {
    const configs=Object.values(state.sources), count=configs.reduce((sum,row)=>sum+(row.selected?.length||0),0);
    container.querySelector('[data-overview]').innerHTML=`<div><strong>${count}</strong><span>已选择的群</span></div><div><strong>${items.filter(row=>row.status==='pending').length}</strong><span>待核实事项</span></div><div><strong>${e(state.ai.enabled?(state.ai.model||'已启用'):'未启用')}</strong><span>当前 AI 服务</span></div><div class="gm-progress"><strong>${state.running?e(phases[state.running.phase]||'处理中'):'就绪'}</strong><span>${state.running?e(names[state.running.source]||'更新结果'):'只处理发生变化的消息'}</span></div>`;
    container.querySelector('[data-stop]').hidden=!state.running&&!state.queued;
  }
  async function refresh(force=false) {
    const token=++serial;
    const values=await Promise.all([api('/status'),api('/items')]);
    if(stopped||token!==serial)return;
    const oldOwner=state?.account_revision;
    if(values[0].account_revision!==values[1].account_revision)return;
    state=values[0];items=values[1].items;
    if(oldOwner&&oldOwner!==state.account_revision){
      dirty.clear();drafts.clear();rendered.clear();selectionFeedback.clear();dialog.close();courses=[];courseMatches={};catalogSignature='';qqAddress=undefined;
      feedback('账号已变化，请重新核对连接与选群。');
    }
    const nextCatalogSignature=JSON.stringify([state.account_revision,...Object.values(state.sources).map(row=>[row.connection,row.revision])]);
    if(force||catalogSignature!==nextCatalogSignature){
      const catalog=await api('/courses');if(stopped||token!==serial)return;
      if(catalog.account_revision!==state.account_revision)return;
      courses=catalog.items;courseMatches=catalog.matches||{};courseMessage=catalog.message||'';catalogSignature=nextCatalogSignature;
    }
    for(const source of Object.keys(names)){
      if((force||rendered.get(source)!==(state.sources[source].revision||'empty'))&&!dirty.has(source))renderSource(source);
      else updateSourceStatus(source);
    }
    const signature=JSON.stringify(items);
    if(signature!==itemSignature||force){itemSignature=signature;renderItems();}
    overview();
  }
  async function poll() {
    try{await refresh();}catch(error){if(!stopped)feedback(error.message||'状态暂时不可用。',true);}
    if(!stopped)timer=setTimeout(poll,5000);
  }
  function openDialog(title,body) {
    dialog.setAttribute('aria-label',title);
    dialog.innerHTML=`<div class="gm-dialog-heading"><h3>${e(title)}</h3><button type="button" class="icon-button" data-close aria-label="关闭">×</button></div>${body}`;
    if(!dialog.open)dialog.showModal();
  }
  on(dialog,'click',event=>{if(event.target.closest('[data-close]')||event.target===dialog)dialog.close();});
  on(container,'input',event=>{
    const source=event.target.closest('[data-source]')?.dataset.source;
    if(!source)return;
    if(source==='qq'&&event.target.name==='base_url')qqAddress=event.target.value;
    if(event.target.matches('[data-group-search]')){renderGroups(source);return;}
    if(event.target.matches('[data-show-all]'))return;
    markDirty(source);
  });
  on(container,'change',event=>{
    const row=event.target.closest('[data-gid]'), source=event.target.closest('[data-source]')?.dataset.source;
    if(source&&event.target.matches('[data-show-all]')){renderGroups(source);return;}
    if(source&&event.target.closest('[data-selection]')&&!row){markDirty(source);return;}
    if(!row||!source)return;
    const values=draftFor(source), gid=row.dataset.gid;
    if(row.querySelector('[data-selected]').checked){
      values.set(gid,{id:gid,course_id:row.querySelector('[data-course]').value,trusted_senders:values.get(gid)?.trusted_senders||[],auto_extract:row.querySelector('[data-auto-extract]').checked,auto_apply:row.querySelector('[data-auto-apply]').checked});
    }else values.delete(gid);
    row.querySelector('[data-group-settings]').disabled=!values.has(gid);
    if(event.target.matches('[data-course]'))row.querySelector('[data-match-hint]').textContent='已手动修改，保存后生效';
    card(source).querySelector('[data-group-count]').textContent=`已选 ${values.size} 个群`;
    markDirty(source);
  });
  on(container,'submit',event=>{
    event.preventDefault();
    const form=event.target, source=form.closest('[data-source]')?.dataset.source;
    if(!source)return;
    call(async()=>{
      if(form.matches('[data-connect]')){
        const body=source==='wechat'?{database_dir:form.elements.database_dir.value.trim(),pid:Number(form.elements.pid.value),acknowledge_local_read:form.elements.consent.checked}:
          {base_url:form.elements.base_url.value.trim(),access_token:form.elements.access_token.value,acknowledge_local_read:form.elements.consent.checked};
        try{await api(`/${source}/connect`,{method:'POST',body});}finally{
          if(form.elements.access_token){
            form.elements.access_token.value='';form.elements.access_token.type='password';
            const toggle=form.querySelector('[data-toggle-token]');toggle.textContent='显示口令';toggle.setAttribute('aria-pressed','false');
          }
          form.elements.consent.checked=false;
        }
        dirty.delete(source);feedback('正在验证本人连接，完成后请选择需要同步的群。');
      }else if(form.matches('[data-snapshot]')){
        await api('/wechat/snapshot',{method:'POST',body:{path:form.elements.path.value.trim()}});dirty.delete(source);feedback('正在检查快照和群列表。');
      }else if(form.matches('[data-selection]')){
        await saveSelection(source,form);return;
      }
      await refresh(true);
    });
  });
  on(container,'click',event=>{
    const button=event.target.closest('button');if(!button)return;
    const source=button.closest('[data-source]')?.dataset.source, gid=button.closest('[data-gid]')?.dataset.gid;
    call(async()=>{
      if(button.hasAttribute('data-toggle-token')){
        const input=button.closest('form').elements.access_token, visible=input.type==='password';
        input.type=visible?'text':'password';button.textContent=visible?'隐藏口令':'显示口令';button.setAttribute('aria-pressed',String(visible));return;
      }
      if(button.hasAttribute('data-refresh')){await refresh(true);return;}
      if(button.hasAttribute('data-reset-selection')){
        dirty.delete(source);selectionFeedback.delete(source);renderSource(source);return;
      }
      if(button.hasAttribute('data-select-matched')){
        const values=draftFor(source);
        for(const row of state.sources[source].groups||[]){
          const match=courseMatches[source]?.[row.id];
          if(!values.has(row.id)&&match?.status==='automatic')values.set(row.id,{id:row.id,course_id:match.course_id,trusted_senders:[],auto_extract:false,auto_apply:false});
        }
        markDirty(source);renderGroups(source);return;
      }
      if(button.hasAttribute('data-stop')){await api('/stop',{method:'POST'});feedback('已请求停止，正在结束当前处理。');await refresh();return;}
      if(button.dataset.filter){filter=button.dataset.filter;for(const node of container.querySelectorAll('[data-filter]'))node.setAttribute('aria-pressed',String(node.dataset.filter===filter));renderItems();return;}
      if(button.hasAttribute('data-discover')){
        const value=await api('/wechat/discovery');if(stopped)return;
        const root=card('wechat'), form=root.querySelector('[data-connect]');
        form.elements.pid.innerHTML='<option value="">请选择本人微信主实例</option>'+value.processes.map(row=>`<option value="${e(String(row.pid))}">${e(row.name||'微信主实例')} · ${e(String(row.pid))}</option>`).join('');
        if(value.processes.length===1)form.elements.pid.value=String(value.processes[0].pid);
        if(value.folders.length===1)form.elements.database_dir.value=value.folders[0];
        root.querySelector('[data-folders]').innerHTML=value.folders.length>1?`<label>已检测目录<select data-folder><option value="">请选择本人账号目录</option>${value.folders.map(path=>`<option value="${e(path)}">${e(path)}</option>`).join('')}</select></label>`:'';
        const picker=root.querySelector('[data-folder]');if(picker)on(picker,'change',()=>{form.elements.database_dir.value=picker.value;});
        feedback(!value.available?'当前环境不支持本机读取，可以导入已有快照。':value.processes.length?`检测到 ${value.processes.length} 个微信主实例，请核对本人目录和实例。`:'未检测到可读取的本人微信主实例，请先登录微信后重试。');return;
      }
      if(button.hasAttribute('data-senders')){
        const result=await api('/senders?'+new URLSearchParams({source,group_id:gid}));if(stopped)return;
        const selected=new Set(draftFor(source).get(gid).trusted_senders||[]);
        const people=[...result.items,...[...selected].filter(id=>!result.items.some(row=>row.id===id)).map(id=>({id,name:id}))];
        openDialog('指定可信的老师或助教',`<p class="gm-hint">按稳定账号标识保存，昵称相同不会自动获得信任。先同步一次，才能看到发言者。</p><form data-trust-form>${people.map(row=>`<label class="gm-check"><input type="checkbox" name="sender" value="${e(row.id)}" ${selected.has(row.id)?'checked':''}><span>${e(row.name)}<small>${e(row.id)}</small></span></label>`).join('')||'<p>暂无已同步的发言者。</p>'}<button class="button button-primary" type="submit">保存到选群设置</button></form>`);
        on(dialog.querySelector('form'),'submit',ev=>{ev.preventDefault();ev.stopPropagation();draftFor(source).get(gid).trusted_senders=[...dialog.querySelectorAll('[name=sender]:checked')].map(node=>node.value);markDirty(source);dialog.close();renderGroups(source);});return;
      }
      if(button.hasAttribute('data-messages')){
        const result=await api('/messages?'+new URLSearchParams({source,group_id:gid,limit:'50'}));if(stopped)return;
        openDialog('已同步消息',`<p class="gm-hint">最近 ${result.items.length} 条 / 本地共 ${result.total} 条；仅在本机查看。</p><div class="gm-message-list">${result.items.map(row=>`<article><strong>${e(row.sender_name||row.sender_id||'发送者未知')}</strong><small>${row.sent_at?e(date(row.sent_at)):'原发送时间未知'}</small><p>${e(row.text)}</p></article>`).join('')||'<p>尚无消息，请先同步一次。</p>'}</div>`);return;
      }
      if(button.hasAttribute('data-extract')){
        openDialog('整理所选群',`<p>将这个群本轮新增消息及相关前文发送至当前 AI 服务 <strong>${e(state.ai.model||'尚未配置')}</strong>。提取结果保留原文依据。</p><p class="gm-hint">未开启按群自动更新时，结果先进入待核实。</p><button type="button" class="button button-primary" data-confirm-extract>确认并整理</button>`);
        on(dialog.querySelector('[data-confirm-extract]'),'click',()=>call(async()=>{await api('/extract',{method:'POST',body:{source,group_id:gid,allow_ai:true}});dialog.close();feedback('已开始整理，可在下方查看结果。');await refresh();}));return;
      }
      if(button.hasAttribute('data-pause')){await api(`/sources/${source}/pause`,{method:'POST'});dirty.delete(source);selectionFeedback.delete(source);feedback('已暂停后续同步与自动整理。');await refresh(true);return;}
      if(button.hasAttribute('data-sync')){await api(`/sources/${source}/sync`,{method:'POST'});feedback('已请求同步一次。');await refresh();return;}
      if(button.hasAttribute('data-compatibility')){await api('/wechat/compatibility',{method:'POST'});feedback('已暂停并开始兼容性检查。');await refresh();return;}
      if(button.hasAttribute('data-forget')){
        openDialog('移除'+names[source]+'连接',`<p>停止读取并删除本模块的连接密钥。已有事项及日程保留。</p><button type="button" class="button button-danger" data-confirm-forget>移除连接</button>`);
        on(dialog.querySelector('[data-confirm-forget]'),'click',()=>call(async()=>{await api(`/sources/${source}`,{method:'DELETE'});dirty.delete(source);if(source==='qq')qqAddress=undefined;dialog.close();await refresh(true);feedback('连接已移除。');}));return;
      }
      if(button.dataset.decision){
        const item=items.find(row=>row.id===button.closest('[data-item]').dataset.item);
        button.disabled=true;
        try{await api(`/items/${encodeURIComponent(item.id)}/decision`,{method:'POST',body:{expected_revision:item.revision,action:button.dataset.decision}});feedback('已保存处理结果。');await refresh(true);}finally{if(button.isConnected)button.disabled=false;}
      }
    });
  });
  await refresh(true);
  if(!stopped)timer=setTimeout(poll,5000);
  return cleanup;
}
