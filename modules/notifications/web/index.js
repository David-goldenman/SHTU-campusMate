import {link,time} from '/assets/campus.js';
import {renderMarkdown} from '/assets/markdown.js';

export async function mount(container,context) {
  const e=context.ui.escape,removeStyle=context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('notice-center');
  let timer, filter='unread';
  const expanded=new Set();
  const cleanup=()=>{clearTimeout(timer);container.querySelector('.notice-automation')?.close();removeStyle();};
  context.signal.addEventListener('abort',cleanup,{once:true});
  container.innerHTML=`<header class="notice-header"><p>学习待办、重要更新与活动邀请</p><button class="button button-secondary" data-open-settings type="button">整理设置</button></header><dialog class="notice-automation" aria-labelledby="notice-settings-title"><div class="dialog-heading"><h2 id="notice-settings-title">通知与自动整理</h2><button class="icon-button" data-close-settings type="button" aria-label="关闭通知设置">×</button></div><div class="notice-automation-body"><h3>校园后台助手</h3><p data-agent-status class="field-hint" role="status"></p><label class="checkbox-label"><input data-agent-enabled type="checkbox">资料更新后检查</label><button type="button" class="button button-secondary" data-check>检查最近资料</button><hr><h3>学习待办</h3><label class="checkbox-label"><input data-auto type="checkbox">定期提炼学习待办</label><button class="button button-secondary" data-generate type="button">汇总当前学习待办</button><p class="field-hint">活动经你确认参加后加入时间表。</p><div class="form-actions"><a href="#mail">邮件分类偏好</a><a href="#settings?tab=ai">AI 设置</a></div></div></dialog><p data-error role="status" class="danger-text"></p><nav class="notice-filters" data-notice-filters aria-label="通知筛选"></nav><div class="notice-list" data-notices></div>`;
  const settings=container.querySelector('.notice-automation');
  container.querySelector('[data-open-settings]').onclick=()=>settings.showModal();
  container.querySelector('[data-close-settings]').onclick=()=>settings.close();
  settings.onclick=event=>{if(event.target===settings)settings.close();};
  async function refresh(){
    clearTimeout(timer);
    const [value,agent]=await Promise.all([context.api('/snapshot'),context.api('/agent/status')]);
    if(context.signal.aborted)return;
    container.querySelector('[data-auto]').checked=value.auto_generate;
    container.querySelector('[data-agent-enabled]').checked=!!agent.enabled;
    container.querySelector('[data-agent-enabled]').disabled=!agent.available;
    container.querySelector('[data-check]').disabled=!agent.available||!agent.enabled||agent.running;
    const checked=agent.last_run?.completed_at||agent.last_checked;
    container.querySelector('[data-agent-status]').textContent=agent.available?(agent.running?'正在检查更新的资料…':agent.summary)+(checked?' · 最近检查 '+time(checked):''):'在设置中启用校园后台助手后可自动检查。';
    container.querySelector('[data-error]').textContent=[value.error,agent.error].filter(Boolean).join('；');
    const filters=container.querySelector('[data-notice-filters]');
    filters.innerHTML=Object.entries({unread:'未读',all:'全部',read:'已读'}).map(([id,label])=>`<button type="button" data-notice-filter="${id}" aria-pressed="${filter===id}">${label}<span>${value.items.filter(item=>id==='all'||item.read===(id==='read')).length}</span></button>`).join('');
    filters.querySelectorAll('[data-notice-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.noticeFilter;refresh().catch(retry);});
    const items=value.items.filter(item=>filter==='all'||item.read===(filter==='read'));
    const proposals=new Map((agent.proposals||[]).map(item=>[item.id,item]));
    container.querySelector('[data-notices]').innerHTML=items.map(item=>{
      const p=proposals.get(item.proposal_id), markdown=renderMarkdown(item.summary);
      const plain=document.createElement('div');plain.innerHTML=markdown;
      const label=item.read?'标记未读':'标记已读';
      const sourceNames={mail:'学校邮箱',blackboard:'Blackboard',gradescope:'Gradescope',elrc:'教学社区',piazza:'Piazza',assignments:'作业管理',eams:'教务系统',timetable:'时间表'};
      const sources=[...new Set(item.citations.map(source=>sourceNames[source.source]||source.source).filter(Boolean))].join(' · ');
      return `<article class="notice-item ${item.read?'is-read':''}"><details data-notice-id="${e(item.id)}" ${expanded.has(item.id)?'open':''}><summary><div class="notice-meta">${item.importance!=='normal'?`<span class="notice-importance ${e(item.importance)}">${e({urgent:'紧急',important:'重要'}[item.importance])}</span>`:''}<span>${e(sources||'学习事项')}</span>${item.event_at?'<time>'+e(time(item.event_at))+'</time>':''}</div><h3>${item.read?'':'<span class="notice-dot" aria-label="未读"></span>'}${e(item.title)}</h3><p class="notice-preview">${e(plain.textContent.slice(0,160))}</p></summary><div class="notice-body"><div class="notice-summary" data-summary="${e(item.id)}">${markdown}</div>${item.why?'<details class="notice-why"><summary>为什么提醒我</summary><p>'+e(item.why)+'</p></details>':''}${item.auto_read?.reason==='assignment_submitted'?'<p class="field-hint">关联作业已提交，已自动标记已读。</p>':''}${p?`<section class="notice-event"><h4>${e(p.event.title)}</h4><p>${e(time(p.event.starts_at))}${p.event.location?' · '+e(p.event.location):''}</p><details><summary>日程依据</summary><blockquote>${e(p.quote)}</blockquote></details>${p.state==='pending'?`<div class="form-actions"><button class="button button-primary" type="button" data-attend="${e(p.id)}">参加并加入时间表</button><button class="text-button" type="button" data-dismiss="${e(p.id)}">不参加</button></div>`:p.state==='accepted'?'<p class="notice-event-result">已加入时间表 · <a href="#timetable">查看安排</a></p>':'<p class="field-hint">已选择不参加</p>'}</section>`:''}${item.citations.length?'<div class="notice-sources"><span>原始资料</span>'+item.citations.map(source=>link(source.url,source.title,e)).join('')+'</div>':''}</div></details><button type="button" class="notice-read" title="${label}" aria-label="${label}：${e(item.title)}" data-read="${e(item.id)}" data-value="${!item.read}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="${item.read?'M4 6h16v13H4z M4 7l8 6 8-6':'M4 10l8-6 8 6v10H4z M4 10l8 6 8-6'}"/></svg><span class="visually-hidden">${label}</span></button></article>`;
    }).join('')||'<div class="empty-state"><h3>'+({unread:'没有未读通知',read:'暂无已读通知',all:'重要事项会显示在这里'}[filter])+'</h3><p>已提交作业的提醒会自动归入已读。</p></div>';
    container.querySelectorAll('[data-notice-id]').forEach(details=>{details.ontoggle=()=>{if(details.open)expanded.add(details.dataset.noticeId);else expanded.delete(details.dataset.noticeId);};});
    container.querySelectorAll('[data-read]').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{await context.api('/'+encodeURIComponent(button.dataset.read)+'/read',{method:'PUT',body:{read:button.dataset.value==='true'}});await refresh();}));
    for(const [attr,action]of[['attend','accept'],['dismiss','dismiss']])container.querySelectorAll('[data-'+attr+']').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{await context.api('/proposals/'+button.dataset[attr]+'/'+action,{method:'POST'});context.ui.toast(action==='accept'?'已加入时间表。':'已记录不参加。');await refresh();}));
    timer=setTimeout(()=>refresh().catch(retry),6000);
  }
  function retry(error){if(!context.signal.aborted){container.querySelector('[data-error]').textContent=error.message;timer=setTimeout(()=>refresh().catch(retry),12000);}}
  const generate=container.querySelector('[data-generate]');generate.onclick=context.ui.safeAction(generate,async()=>{await context.api('/generate?force=true',{method:'POST'});await refresh();});
  const check=container.querySelector('[data-check]');check.onclick=context.ui.safeAction(check,async()=>{await context.api('/agent/check',{method:'POST'});context.ui.toast('已开始检查最近资料。');await refresh();});
  container.querySelector('[data-agent-enabled]').onchange=async event=>{try{await context.api('/agent/settings',{method:'PUT',body:{enabled:event.currentTarget.checked}});await refresh();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
  container.querySelector('[data-auto]').onchange=async event=>{try{await context.api('/settings',{method:'PUT',body:{auto_generate:event.currentTarget.checked}});await refresh();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
  await refresh();return cleanup;
}
