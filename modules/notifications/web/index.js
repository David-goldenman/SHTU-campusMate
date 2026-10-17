import {link,time} from '/assets/campus.js';
import {renderMarkdown} from '/assets/markdown.js';

export async function mount(container,context) {
  const e=context.ui.escape,removeStyle=context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('notice-center');
  let timer, filter='unread';
  container.innerHTML='<section class="notice-agent"><div><h3>后台助手</h3><p data-agent-status class="field-hint" role="status"></p></div><label class="checkbox-label"><input data-agent-enabled type="checkbox">资料更新后检查</label><button type="button" class="button button-secondary" data-check>检查一次</button></section><p class="field-hint">按需整理更新的资料并复核最近邮件；可选活动由你确认参加后加入时间表。<a href="#mail">调整邮件偏好</a></p><div class="campus-toolbar notice-toolbar"><button class="button button-secondary" data-generate type="button">汇总当前学习待办</button><details><summary>提炼设置</summary><label class="checkbox-label"><input data-auto type="checkbox">定期提炼学习待办</label><a href="#settings?tab=ai">AI 设置</a></details></div><p data-error role="status" class="danger-text"></p><div class="campus-list" data-notices></div>';
  async function refresh(){
    clearTimeout(timer);
    const [value,agent]=await Promise.all([context.api('/snapshot'),context.api('/agent/status')]);
    if(context.signal.aborted)return;
    container.querySelector('[data-auto]').checked=value.auto_generate;
    container.querySelector('[data-agent-enabled]').checked=!!agent.enabled;
    container.querySelector('[data-agent-enabled]').disabled=!agent.available;
    container.querySelector('[data-check]').disabled=!agent.available||!agent.enabled||agent.running;
    const checked=agent.last_run?.completed_at||agent.last_checked;
    container.querySelector('[data-agent-status]').textContent=agent.available?(agent.running?'正在检查更新的资料…':agent.summary)+(checked?' · '+(agent.last_run?'最近综合检查 ':'资料检查 ')+time(checked):''):'在设置中启用校园后台助手后，可按资料变化自动检查。';
    container.querySelector('[data-error]').textContent=[value.error,agent.error].filter(Boolean).join('；');
    let filters=container.querySelector('[data-notice-filters]');
    if(!filters){filters=document.createElement('nav');filters.dataset.noticeFilters='';filters.className='campus-toolbar notice-filters';filters.setAttribute('aria-label','通知筛选');container.querySelector('[data-notices]').before(filters);}
    filters.innerHTML=Object.entries({unread:'未读',read:'已读',all:'全部'}).map(([id,label])=>`<button type="button" class="button button-secondary" data-notice-filter="${id}" aria-pressed="${filter===id}">${label} <span>${value.items.filter(item=>id==='all'||item.read===(id==='read')).length}</span></button>`).join('');
    filters.querySelectorAll('[data-notice-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.noticeFilter;refresh().catch(retry);});
    const items=value.items.filter(item=>filter==='all'||item.read===(filter==='read'));
    const proposals=new Map((agent.proposals||[]).map(item=>[item.id,item]));
    container.querySelector('[data-notices]').innerHTML=items.map(item=>{
      const p=proposals.get(item.proposal_id);
      return `<article class="campus-item notice-item ${item.read?'is-read':''}"><header><div><p class="field-hint">${e({urgent:'紧急',important:'重要',normal:'提醒'}[item.importance])}${item.event_at?' · '+e(time(item.event_at)):''}</p><h3>${item.read?'':'<span class="notice-dot" aria-label="未读"></span>'}${e(item.title)}</h3></div><button type="button" class="text-button" data-read="${e(item.id)}" data-value="${!item.read}">${item.read?'标记未读':'标记已读'}</button></header><div class="notice-summary" data-summary="${e(item.id)}"></div>${item.why?'<p class="notice-why">'+e(item.why)+'</p>':''}${p?`<div class="notice-event"><strong>${e(p.event.title)}</strong><p>${e(time(p.event.starts_at))}${p.event.location?' · '+e(p.event.location):''}</p><details><summary>日程依据</summary><blockquote>${e(p.quote)}</blockquote></details>${p.state==='pending'?`<div class="form-actions"><button class="button button-primary" type="button" data-attend="${e(p.id)}">参加并加入时间表</button><button class="text-button" type="button" data-dismiss="${e(p.id)}">不参加</button></div>`:p.state==='accepted'?'<p class="field-hint">已加入时间表 · <a href="#timetable">查看安排</a></p>':'<p class="field-hint">已选择不参加</p>'}</div>`:''}<div class="notice-sources">${item.citations.map(source=>link(source.url,source.title,e)).join(' · ')}</div></article>`;
    }).join('')||'<div class="empty-state"><h3>'+({unread:'没有未读通知',read:'暂无已读通知',all:'重要事项会显示在这里'}[filter])+'</h3><p>已提交作业的提醒会自动归入已读，可切换查看历史。</p></div>';
    for(const item of items){const node=[...container.querySelectorAll('[data-summary]')].find(node=>node.dataset.summary===item.id);node.innerHTML=renderMarkdown(item.summary);if(item.auto_read?.reason==='assignment_submitted'){const explanation=document.createElement('p');explanation.className='field-hint';explanation.textContent='关联作业已提交，已自动标记已读。';node.after(explanation);}}
    container.querySelectorAll('[data-read]').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{await context.api('/'+encodeURIComponent(button.dataset.read)+'/read',{method:'PUT',body:{read:button.dataset.value==='true'}});await refresh();}));
    for(const [attr,action]of[['attend','accept'],['dismiss','dismiss']])container.querySelectorAll('[data-'+attr+']').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{await context.api('/proposals/'+button.dataset[attr]+'/'+action,{method:'POST'});context.ui.toast(action==='accept'?'已加入时间表。':'已记录不参加。');await refresh();}));
    timer=setTimeout(()=>refresh().catch(retry),6000);
  }
  function retry(error){if(!context.signal.aborted){container.querySelector('[data-error]').textContent=error.message;timer=setTimeout(()=>refresh().catch(retry),12000);}}
  const generate=container.querySelector('[data-generate]');generate.onclick=context.ui.safeAction(generate,async()=>{await context.api('/generate?force=true',{method:'POST'});await refresh();});
  const check=container.querySelector('[data-check]');check.onclick=context.ui.safeAction(check,async()=>{await context.api('/agent/check',{method:'POST'});context.ui.toast('已开始检查最近资料。');await refresh();});
  container.querySelector('[data-agent-enabled]').onchange=async event=>{try{await context.api('/agent/settings',{method:'PUT',body:{enabled:event.currentTarget.checked}});await refresh();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
  container.querySelector('[data-auto]').onchange=async event=>{try{await context.api('/settings',{method:'PUT',body:{auto_generate:event.currentTarget.checked}});await refresh();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
  const cleanup=()=>{clearTimeout(timer);removeStyle();};context.signal.addEventListener('abort',cleanup,{once:true});
  await refresh();return cleanup;
}
