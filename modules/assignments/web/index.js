import {sourcePanel, records, link} from '/assets/campus.js';
import {deadlineInfo, deadlineMarkup} from '/assets/deadlines.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('assignment-board');
  const statuses = {open:'已开放',scheduled:'尚未开放',closed:'已关闭',unknown:'开放状态未知'};
  const views = {all:'全部',urgent:'24 小时内',overdue:'已逾期',undated:'待定'};
  let current = true, query = '', view = new URLSearchParams(location.hash.split('?')[1] || '').get('view') || 'all', redraw, timer;
  if (!Object.hasOwn(views,view)) view = 'all';
  const dispose = () => {clearInterval(timer);removeStyle();};
  context.signal.addEventListener('abort',dispose,{once:true});
  const card = (item,now,pending=false) => `<article class="assignment-task" data-assignment="${e(item.id)}" data-priority="${pending ? deadlineInfo(item.due_at,now).urgency : 'neutral'}"><div class="assignment-task-main"><p class="assignment-course">${e(item.course_title || '未关联课程')}<span>${e(item.source === 'blackboard' ? 'Blackboard' : item.source === 'gradescope' ? 'Gradescope' : item.source)}</span></p><h4>${link(item.url,item.title,e)}</h4><p class="assignment-state">${pending ? '待完成' : item.submitted === true ? '已提交' : item.submitted === false ? '未提交' : '提交状态未知'} · ${e(statuses[item.availability] || '开放状态未知')}${item.score != null ? ' · 成绩 ' + e(item.score) + ' / ' + e(item.max_score ?? '未提供') : ''}</p></div>${deadlineMarkup(item.due_at,e,{now,emphasize:pending})}<div class="assignment-actions"><button type="button" class="text-button" data-detail="${e(item.id)}">查看详情与题目 →</button></div></article>`;
  const cleanup = await sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = `<header class="assignment-heading"><h2>待完成作业</h2><span>时间均为北京时间</span></header><div data-summary></div><div class="campus-toolbar assignment-toolbar"><label class="checkbox-label"><input data-current type="checkbox" ${current ? 'checked' : ''}>本学期</label><input data-search type="search" aria-label="搜索作业" placeholder="搜索作业或课程" value="${e(query)}"></div><div class="assignment-filters" data-filters role="group" aria-label="按截止时间筛选"></div><div data-lists></div>`;
    const draw = () => {
      const now = Date.now();
      const values = snapshot.data.assignments.filter(item => (!current || item.current) && (item.title + ' ' + item.course_title).toLowerCase().includes(query.toLowerCase()));
      const ids = new Set(values.map(item => item.id));
      const pending = snapshot.pending.filter(item => ids.has(item.id)).map(item => ({...item,deadline:deadlineInfo(item.due_at,now)}));
      const upcoming = pending.filter(item => item.deadline.timestamp !== null && item.deadline.urgency !== 'overdue').sort((a,b) => a.deadline.timestamp - b.deadline.timestamp);
      const overdue = pending.filter(item => item.deadline.urgency === 'overdue').sort((a,b) => b.deadline.timestamp - a.deadline.timestamp);
      const undated = pending.filter(item => item.deadline.timestamp === null);
      const urgent = upcoming.filter(item => item.deadline.urgency === 'urgent');
      const counts = {all:pending.length,urgent:urgent.length,overdue:overdue.length,undated:undated.length};
      body.querySelector('[data-summary]').innerHTML = `<div class="assignment-summary"><div><strong>${pending.length}</strong><span>项待完成</span></div><div data-tone="urgent"><strong>${urgent.length}</strong><span>项在 24 小时内截止</span></div><div data-tone="overdue"><strong>${overdue.length}</strong><span>项已逾期，仍可处理</span></div></div>`;
      body.querySelector('[data-filters]').innerHTML = Object.entries(views).map(([key,label]) => `<button type="button" data-view="${key}" aria-pressed="${view === key}">${label}<span>${counts[key]}</span></button>`).join('');
      const sections = view === 'urgent' ? [['24 小时内截止',urgent]] : view === 'overdue' ? [['已逾期，来源仍允许处理',overdue]] : view === 'undated' ? [['截止时间待定',undated]] : [['即将截止',upcoming],['已逾期，来源仍允许处理',overdue],['截止时间待定',undated]];
      const lists = sections.filter(([,items]) => items.length).map(([title,items]) => `<section class="assignment-section"><h3>${title}<span>${items.length} 项</span></h3>${items.map(item => card(item,now,true)).join('')}</section>`).join('');
      const groups = new Map();
      for (const item of values) {const key = item.group_id || 'unlinked';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
      body.querySelector('[data-lists]').innerHTML = `<div class="assignment-pending" data-pending>${lists || '<p class="assignment-empty">' + (query ? '没有符合搜索条件的待办。' : view !== 'all' ? '当前筛选下没有待办，可切换“全部”查看。' : '目前没有来源明确开放且尚未提交的本学期作业。') + '</p>'}</div><section class="assignment-courses"><h3>按课程查看全部作业<span>${values.length} 项</span></h3>${[...groups.values()].map(items => '<details class="assignment-course-group"><summary>' + e(items[0].course_title || '未关联课程') + '<span>' + items.length + ' 项</span></summary>' + items.map(item => card(item,now)).join('') + '</details>').join('') || '<p class="field-hint">没有符合条件的课程作业。</p>'}</section>`;
      body.querySelectorAll('[data-view]').forEach(button => button.onclick = () => {view=button.dataset.view;draw();body.querySelector('[data-view="' + view + '"]').focus();});
      body.querySelectorAll('[data-detail]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
        const detail = await context.api('/detail?assignment_id=' + encodeURIComponent(button.dataset.detail));
        if (context.signal.aborted) return;
        const content = document.createElement('div');
        content.innerHTML = '<p>' + e(detail.assignment.body_text || '该作业未提供可展示的在线题干，可下载题目或查看原站。') + '</p>' + records(detail.materials,e);
        const dialog = context.ui.dialog(detail.assignment.title,content);
        context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
      }));
    };
    body.querySelector('[data-current]').onchange = event => {current=event.currentTarget.checked;draw();};
    body.querySelector('[data-search]').oninput = event => {query=event.currentTarget.value;draw();};
    redraw=draw;draw();
    container.append(container.querySelector('.source-toolbar'));
  });
  if (!context.signal.aborted) timer=setInterval(()=>{if(redraw && !container.contains(document.activeElement))redraw();},60000);
  return () => {cleanup();dispose();};
}
