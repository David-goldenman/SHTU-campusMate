import {sourcePanel, records, link, time} from '/assets/campus.js';

const sections = [
  ['pending','待完成作业','来源明确开放、尚未确认已提交且尚未截止。'],
  ['late','迟交作业','已过截止时间，但来源仍开放提交。'],
  ['graded','已批改作业','已提交并已公布成绩。'],
  ['completed','已完成作业','已提交，成绩尚未公布。'],
  ['ended','已结束作业','来源已关闭、尚未开放或开放状态未知。'],
];

export async function mount(container,context) {
  const e = context.ui.escape;
  const statuses = {open:'已开放',scheduled:'尚未开放',closed:'已关闭',unknown:'开放状态未知'};
  container.classList.add('assignment-center');
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const card = item => {
    const score = item.score !== null && item.score !== undefined
      ? `<p class="assignment-grade">成绩 <strong>${e(item.score)}</strong>${item.max_score !== null && item.max_score !== undefined ? '<span> / ' + e(item.max_score) + '</span>' : ''}</p>` : '';
    const late = item.category === 'late' ? '<strong class="assignment-late">已过截止，仍可提交</strong>' : item.overdue ? ' · 已过截止，来源仍允许处理' : '';
    return `<article class="campus-item assignment-card"><div class="assignment-card-head"><h4>${link(item.url,item.title,e)}</h4>${item.category === 'graded' ? '<span class="assignment-badge">已批改</span>' : ''}</div><p class="field-hint">${e(item.course_title)} · ${e(item.source)} · ${e(statuses[item.availability] || '开放状态未知')} · ${item.submitted === true ? '已提交' : item.submitted === false ? '未提交' : '提交状态未知'}</p><p>截止：${e(time(item.due_at))}${late}</p>${score}<button type="button" class="text-button" data-detail="${e(item.id)}">查看详情与题目</button></article>`;
  };
  const cleanup = await sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = '<div class="campus-toolbar"><label class="checkbox-label"><input data-current type="checkbox" checked>本学期</label><input data-search aria-label="搜索作业" placeholder="搜索作业或课程"></div><div data-lists></div><div class="campus-detail" data-preview aria-live="polite"></div>';
    const draw = () => {
      const query = body.querySelector('[data-search]').value.toLowerCase();
      const values = snapshot.data.assignments.filter(item => (!body.querySelector('[data-current]').checked || item.current) && (item.title + ' ' + item.course_title).toLowerCase().includes(query));
      body.querySelector('[data-lists]').innerHTML = sections.map(([id,label,hint]) => {
        const items = values.filter(item => item.category === id);
        return `<section class="assignment-section" data-section="${id}"><header class="assignment-section-head"><h3>${label}</h3><span class="assignment-count" aria-label="${items.length} 项">${items.length}</span></header><p class="field-hint">${hint}</p><div class="campus-list">${items.map(card).join('') || '<p class="field-hint assignment-empty">没有符合条件的作业。</p>'}</div></section>`;
      }).join('');
      body.querySelectorAll('[data-detail]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
        const detail = await context.api('/detail?assignment_id=' + encodeURIComponent(button.dataset.detail));
        body.querySelector('[data-preview]').innerHTML = '<article class="campus-item"><h3>' + e(detail.assignment.title) + '</h3><p>' + e(detail.assignment.body_text || '该作业未提供可展示的在线题干，可下载题目或查看原站。') + '</p></article>' + records(detail.materials,e);
      }));
    };
    body.querySelector('[data-current]').onchange = draw;
    body.querySelector('[data-search]').oninput = draw;
    draw();
  });
  return () => {cleanup();removeStyle();container.classList.remove('assignment-center');};
}
