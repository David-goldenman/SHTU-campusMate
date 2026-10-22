import {sourcePanel, records, link, time, submissionLabel} from '/assets/campus.js';
import {deadlineInfo,deadlineMarkup} from '/assets/deadlines.js';

const zone = {timeZone:'Asia/Shanghai'};
const handlingReasons = {team_submitted:'队友已提交',not_required:'老师说明无需提交',other:'其他原因'};
const dueInput = value => {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.valueOf())) return '';
  return new Intl.DateTimeFormat('sv-SE',{...zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date).replace(' ','T');
};
const sections = [
  ['pending','待完成作业','来源明确开放、尚未确认已提交且尚未截止；无截止时间按第 18 教学周周日估计。'],
  ['late','迟交作业','已过截止时间，但来源仍开放提交。'],
  ['graded','已批改作业','已提交并已公布成绩。'],
  ['completed','已完成作业','已提交，成绩尚未公布。'],
  ['ended','已结束作业','来源已关闭、尚未开放或开放状态未知。'],
  ['waived','无需我提交','你已确认无需单独提交，不再计入待办和截止提醒；可随时恢复。原站个人提交状态仍保留。'],
];

export async function mount(container,context) {
  const e = context.ui.escape;
  const handlingNote = item => item.reminder_suppressed ? `<p class="assignment-handling-note">无需我提交 · ${e(handlingReasons[item.handling?.reason] || '本地选择')}${item.handling?.note ? '<br>'+e(item.handling.note) : ''}</p>` : '';
  const statuses = {open:'已开放',scheduled:'尚未开放',closed:'已关闭',unknown:'开放状态未知'};
  const requested = new URLSearchParams(location.hash.split('?')[1] || '').get('view');
  let view = ['urgent','overdue','undated'].includes(requested) ? requested : 'all';
  let sectionFilter = view === 'overdue' ? 'late' : 'pending';
  container.classList.add('assignment-center');
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const canEditDue = item => item.due_default || !item.due_at || item.due_source === 'manual';
  const deadlineCell = item => {
    if (item.reminder_suppressed) return `<div class="assignment-deadline"><span class="field-hint">已停止截止提醒</span>${item.due_at && !item.due_default ? '<span class="field-hint">原截止 '+e(time(item.due_at))+'</span>' : ''}</div>`;
    if (item.due_default) {
      const estimate = deadlineInfo(item.due_at);
      return `<div class="assignment-deadline assignment-deadline-tentative"><strong>待完成 · 时间待定</strong><span>默认第 18 教学周周日 · ${e(estimate.date)} ${e(estimate.clock)}</span><button type="button" class="text-button" data-due-toggle>设置时间</button></div>`;
    }
    return `<div class="assignment-deadline">${deadlineMarkup(item.due_at,e,{emphasize:['pending','late'].includes(item.category)})}${canEditDue(item) ? '<button type="button" class="text-button" data-due-toggle>'+ (item.due_source === 'manual' ? '调整时间' : '设置时间') +'</button>' : ''}</div>`;
  };
  const dueEditor = item => {
    if (!canEditDue(item)) return '';
    return `<div class="assignment-due-editor" data-due-editor hidden><label>截止时间（北京时间）<input type="datetime-local" data-due-input value="${e(dueInput(item.due_at))}" required></label><button type="button" class="button button-primary" data-due-save>保存</button>${item.due_source === 'manual' ? '<button type="button" class="text-button" data-due-reset>恢复默认</button>' : ''}<button type="button" class="text-button" data-due-cancel>取消</button></div>`;
  };
  const card = item => {
    const score = item.score !== null && item.score !== undefined ? `<span class="assignment-grade">${e(item.score)}${item.max_score != null ? ' / '+e(item.max_score) : ''}</span>` : '';
    const priority = item.reminder_suppressed ? 'handled' : item.due_default ? 'unknown' : deadlineInfo(item.due_at).urgency;
    const handlingAction = item.reminder_suppressed ? '<button type="button" class="text-button" data-handling-restore>恢复提醒</button>' : !item.submitted && !item.exempt ? '<button type="button" class="text-button" data-handling-open>无需我提交</button>' : '';
    return `<article class="assignment-card" draggable="true" tabindex="0" data-assignment="${e(item.id)}" data-priority="${priority}" title="聚焦后使用 ↑↓ 调整顺序"><div class="assignment-main"><p>${e(item.course_title)} <span>· ${e(item.source)}</span></p><h4><button type="button" class="assignment-title" data-detail="${e(item.id)}">${e(item.title)}</button></h4>${handlingNote(item)}</div>${deadlineCell(item)}<div class="assignment-state"><span title="${e(item.submission_reason || '')}">${item.reminder_suppressed?'原站：':''}${e(submissionLabel(item))}</span>${score}${item.needs_review?'<span class="assignment-review">需核实</span>':''}</div><div class="assignment-card-actions">${handlingAction}${link(item.url,'原站',e)}<button type="button" class="assignment-move" data-move="up" aria-label="上移 ${e(item.title)}" title="上移">↑</button><button type="button" class="assignment-move" data-move="down" aria-label="下移 ${e(item.title)}" title="下移">↓</button></div>${dueEditor(item)}</article>`;
  };
  const cleanup = await sourcePanel(container,context,(body,snapshot,_,reload) => {
    body.classList.add('assignment-board');
    body.innerHTML = '<div class="assignment-toolbar"><input data-search type="search" aria-label="搜索作业" placeholder="搜索作业或课程"><label class="checkbox-label"><input data-current type="checkbox" checked>本学期</label><details class="assignment-order-help"><summary>排序说明</summary><p>可拖动同一分类的作业行，或聚焦后用 ↑↓ 调整顺序。顺序自动保存。</p></details><span class="visually-hidden" data-order-status role="status"></span></div><nav class="assignment-tabs" data-assignment-tabs aria-label="作业状态"></nav><div class="assignment-view-filters" data-view-filters aria-label="截止时间筛选"></div><div data-lists></div>';
    if (snapshot.coverage) {
      const names = {blackboard:'Blackboard',gradescope:'Gradescope',ecourse:'E 云课堂'};
      const labels = {ready:'已同步',partial:'部分读取',cached:'缓存待更新',syncing:'正在同步',error:'读取失败',not_connected:'未连接',login_required:'需要登录',verification_required:'需要验证',disabled:'未启用'};
      const label = snapshot.coverage.status === 'unavailable' ? '尚未取得作业数据，不代表没有作业'
        : snapshot.coverage.status === 'partial' ? '部分来源需要更新，已保留已知待办' : '作业来源与更新时间';
      body.insertAdjacentHTML('afterbegin',`<details class="assignment-coverage" data-coverage="${e(snapshot.coverage.status)}"><summary>${e(label)}</summary><p>这里汇总已同步平台的作业，课堂、邮件或群通知中的其他要求仍需核对。</p><ul>${snapshot.coverage.sources.map(source=>`<li>${e(names[source.id] || source.id)}：${e(labels[source.status] || source.status)}${source.updated_at ? ' · '+e(time(source.updated_at)) : ''}</li>`).join('')}</ul><a href="#settings?tab=accounts">检查来源连接 →</a></details>`);
    }
    const lists = body.querySelector('[data-lists]');
    const status = text => {body.querySelector('[data-order-status]').textContent = text;};
    const idsFor = section => snapshot.data.assignments.filter(item => item.category === section).map(item => item.id);
    const focusCard = identity => {
      const target = [...body.querySelectorAll('[data-assignment]')].find(item => item.dataset.assignment === identity);
      if (target) target.focus();
    };
    function reorder(section,identity,targetId,after) {
      if (!targetId || identity === targetId) return null;
      const all = snapshot.data.assignments, items = all.filter(item => item.category === section);
      const from = items.findIndex(item => item.id === identity);
      if (from < 0) return null;
      const moved = items.splice(from,1)[0];
      let to = items.findIndex(item => item.id === targetId);
      if (to < 0) return null;
      if (after) to += 1;
      items.splice(to,0,moved);
      snapshot.data.assignments = all.filter(item => item.category !== section).concat(items);
      return items.map(item => item.id);
    }
    let saving = false;
    async function save(section,before,focusId) {
      const ids = idsFor(section);
      saving = true;
      draw();
      status('正在保存顺序…');
      try {
        const value = await context.api('/order',{method:'PUT',body:{section,ids,account_revision:snapshot.account_revision || ''}});
        snapshot.order = value.order;
        status('顺序已保存');
      } catch (error) {
        snapshot.data.assignments = before;
        draw();
        status('');
        context.ui.toast(error.message);
        focusCard(focusId);
      } finally {
        saving = false;
        focusCard(focusId);
      }
    }
    function move(section,identity,direction) {
      if (saving) return;
      const ids = idsFor(section), index = ids.indexOf(identity), target = ids[index + direction];
      if (!target) return;
      const before = snapshot.data.assignments;
      if (reorder(section,identity,target,direction > 0)) void save(section,before,identity);
    }
    let dragging = null;
    const clearDrop = () => lists.querySelectorAll('.drop-before,.drop-after').forEach(item => item.classList.remove('drop-before','drop-after'));
    lists.addEventListener('dragstart',event => {
      const article = event.target.closest('[data-assignment]');
      if (saving || !article || event.target.closest('a,button,input,label,[data-due-editor]') || !event.dataTransfer) return;
      const section = article.closest('[data-section]').dataset.section;
      dragging = {article,id:article.dataset.assignment,section,before:snapshot.data.assignments};
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain',article.dataset.assignment);
      article.classList.add('is-dragging');
    });
    lists.addEventListener('dragover',event => {
      if (!dragging) return;
      const article = event.target.closest('[data-assignment]');
      if (!article || article === dragging.article) return;
      if (article.closest('[data-section]').dataset.section !== dragging.section) {clearDrop();return;}
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      clearDrop();
      article.classList.add(event.clientY > article.getBoundingClientRect().top + article.offsetHeight / 2 ? 'drop-after' : 'drop-before');
    });
    lists.addEventListener('drop',event => {
      if (!dragging) return;
      const article = event.target.closest('[data-assignment]');
      if (!article || article === dragging.article || article.closest('[data-section]').dataset.section !== dragging.section) return;
      event.preventDefault();
      const after = event.clientY > article.getBoundingClientRect().top + article.offsetHeight / 2;
      const {id,section,before} = dragging;
      dragging = null;
      clearDrop();
      if (reorder(section,id,article.dataset.assignment,after)) void save(section,before,id);
    });
    lists.addEventListener('dragend',() => {dragging = null;clearDrop();lists.querySelectorAll('.is-dragging').forEach(item => item.classList.remove('is-dragging'));});
    const draw = () => {
      const query = body.querySelector('[data-search]').value.toLowerCase();
      const all = snapshot.data.assignments.filter(item => (!body.querySelector('[data-current]').checked || item.current) && (item.title + ' ' + item.course_title).toLowerCase().includes(query));
      body.querySelector('[data-assignment-tabs]').innerHTML = [['all','全部'],...sections.map(([id,label])=>[id,label.replace('作业','')])].map(([id,label])=>`<button type="button" data-section-filter="${id}" aria-pressed="${sectionFilter===id}">${label}<span>${all.filter(item=>id==='all'||item.category===id).length}</span></button>`).join('');
      body.querySelector('[data-view-filters]').innerHTML = Object.entries({all:'全部时间',urgent:'24 小时内',overdue:'已逾期',undated:'时间待定'}).map(([id,label])=>`<button type="button" data-view="${id}" aria-pressed="${view===id}">${label}</button>`).join('');
      const values = all.filter(item => {
        if (sectionFilter!=='all' && item.category!==sectionFilter) return false;
        const when=deadlineInfo(item.due_at);
        return view==='all' || view==='urgent' && !item.due_default && when.urgency==='urgent' || view==='overdue' && !item.due_default && when.urgency==='overdue' || view==='undated' && (item.due_default===true || when.timestamp===null);
      });
      lists.innerHTML = sections.map(([id,label,hint]) => {
        if (sectionFilter!=='all' && sectionFilter!==id) return '';
        const items = values.filter(item => item.category === id);
        if (!items.length && sectionFilter==='all') return '';
        return `<section class="assignment-section" data-section="${id}"><header class="assignment-section-head"><h3>${label}</h3><span class="assignment-count">${items.length} 项</span><span class="assignment-section-hint">${hint}</span></header><div class="assignment-rows" ${['pending','late'].includes(id)?'data-pending':''}>${items.map(card).join('') || '<p class="field-hint assignment-empty">没有符合条件的作业。</p>'}</div></section>`;
      }).join('');
      body.querySelectorAll('[data-section-filter]').forEach(button=>{button.onclick=()=>{sectionFilter=button.dataset.sectionFilter;view='all';draw();};});
      body.querySelectorAll('[data-view]').forEach(button=>{button.onclick=()=>{view=button.dataset.view;if(view==='overdue')sectionFilter='late';else if(view!=='all')sectionFilter='pending';draw();};});
      body.querySelectorAll('[data-detail]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
        const detail = await context.api('/detail?assignment_id=' + encodeURIComponent(button.dataset.detail));
        if(context.signal.aborted)return;
        const content=document.createElement('div');content.className='assignment-detail';
        content.innerHTML='<p class="field-hint">'+e(detail.assignment.course_title)+' · '+e(statuses[detail.assignment.availability]||'开放状态未知')+'</p>'+(detail.assignment.due_default?'<p class="field-hint assignment-due-note">来源未提供截止时间；当前按第 18 教学周周日（'+e(deadlineInfo(detail.assignment.due_at).date+' '+deadlineInfo(detail.assignment.due_at).clock)+'）估计，可在作业列表中内联修改。</p>':deadlineMarkup(detail.assignment.due_at,e,{emphasize:false}))+'<p>'+e(submissionLabel(detail.assignment))+'</p><details><summary>提交状态依据</summary><p>'+e(detail.assignment.submission_reason||'依据最近同步的原站记录。')+'</p>'+(detail.assignment.checked_at?'<p class="field-hint">检查于 '+e(time(detail.assignment.checked_at))+'</p>':'')+(detail.assignment.submitted_at?'<p class="field-hint">提交于 '+e(time(detail.assignment.submitted_at))+'</p>':'')+'</details><div class="assignment-statement">'+e(detail.assignment.body_text||'可下载题目或在原站查看完整要求。')+'</div>'+records(detail.materials,e)+'<div class="dialog-actions">'+link(detail.assignment.url,'打开原站',e)+'</div>';
        const dialog=context.ui.dialog(detail.assignment.title,content);context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
        content.insertAdjacentHTML('afterbegin',handlingNote(detail.assignment));
      }));
      const saveHandling = async (item,status,reason=null,note='') => {
        await context.api('/handling',{method:'PUT',body:{assignment_id:item.id,status,reason,note,
          expected_revision:item.handling?.revision || '',account_revision:snapshot.account_revision || ''}});
      };
      body.querySelectorAll('[data-handling-open]').forEach(button => button.onclick = () => {
        const item = snapshot.data.assignments.find(value=>value.id===button.closest('[data-assignment]').dataset.assignment);
        const form = document.createElement('form');
        form.className = 'assignment-handling-form';
        form.innerHTML = `<p>${e(item.title)}</p><p class="field-hint">停止这项作业的待办和截止提醒，保留原站个人提交状态。以后可在“无需我提交”分类中恢复。</p><label>原因<select name="reason">${Object.entries(handlingReasons).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><label>说明（选填）<textarea name="note" maxlength="500" rows="3" placeholder="例如：老师要求小组只交一份，队友已提交"></textarea></label><div class="dialog-actions"><button type="button" class="text-button" data-handling-cancel>取消</button><button type="submit" class="button button-primary" data-handling-save>保存选择</button></div>`;
        const dialog = context.ui.dialog('无需我提交',form);
        context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
        form.querySelector('[data-handling-cancel]').onclick = ()=>dialog.close();
        const reason = form.elements.reason, note = form.elements.note;
        reason.onchange = ()=>{note.required=reason.value==='other';};
        const saveButton = form.querySelector('[data-handling-save]');
        form.onsubmit = event => {
          event.preventDefault();
          if(saveButton.disabled || !form.reportValidity())return;
          void context.ui.safeAction(saveButton,async()=>{
            await saveHandling(item,'waived',reason.value,note.value);
            dialog.close();
            sectionFilter='waived';view='all';
            await reload();
            context.ui.toast('已保存，可在“无需我提交”中恢复提醒');
          })();
        };
      });
      body.querySelectorAll('[data-handling-restore]').forEach(button => button.onclick = context.ui.safeAction(button,async()=>{
        const item = snapshot.data.assignments.find(value=>value.id===button.closest('[data-assignment]').dataset.assignment);
        await saveHandling(item,'required');
        await reload();
        context.ui.toast('已恢复，待办与提醒按原站状态重新判断');
      }));
      body.querySelectorAll('[data-due-toggle]').forEach(button => button.onclick = () => {
        const editor = button.closest('[data-assignment]').querySelector('[data-due-editor]');
        editor.hidden = !editor.hidden;
        if (!editor.hidden) editor.querySelector('[data-due-input]').focus();
      });
      body.querySelectorAll('[data-due-cancel]').forEach(button => button.onclick = () => {
        button.closest('[data-due-editor]').hidden = true;
      });
      body.querySelectorAll('[data-due-save]').forEach(button => button.onclick = context.ui.safeAction(button,async() => {
        const article=button.closest('[data-assignment]'),input=article.querySelector('[data-due-input]');
        if (!input.value) { input.reportValidity(); return; }
        await context.api('/deadline',{method:'PUT',body:{assignment_id:article.dataset.assignment,due_at:input.value+':00+08:00',account_revision:snapshot.account_revision || ''}});
        status('截止时间已保存');
        await reload();
      }));
      body.querySelectorAll('[data-due-reset]').forEach(button => button.onclick = context.ui.safeAction(button,async() => {
        const article=button.closest('[data-assignment]');
        await context.api('/deadline',{method:'PUT',body:{assignment_id:article.dataset.assignment,due_at:null,account_revision:snapshot.account_revision || ''}});
        status('已恢复默认截止时间');
        await reload();
      }));
      body.querySelectorAll('[data-assignment]').forEach(article => {
        article.addEventListener('keydown',event => {
          if (event.target !== article || !['ArrowUp','ArrowDown'].includes(event.key)) return;
          event.preventDefault();
          move(article.closest('[data-section]').dataset.section,article.dataset.assignment,event.key === 'ArrowUp' ? -1 : 1);
        });
      });
      body.querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
        const article = button.closest('[data-assignment]');
        move(article.closest('[data-section]').dataset.section,article.dataset.assignment,button.dataset.move === 'up' ? -1 : 1);
      });
    };
    body.querySelector('[data-current]').onchange = draw;
    body.querySelector('[data-search]').oninput = draw;
    draw();
  });
  return () => {cleanup();removeStyle();container.classList.remove('assignment-center');};
}
