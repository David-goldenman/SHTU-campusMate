import {sourcePanel, records, link, time} from '/assets/campus.js';

export function mount(container,context) {
  const e = context.ui.escape;
  const statuses = {open:'已开放',scheduled:'尚未开放',closed:'已关闭',unknown:'开放状态未知'};
  const card = item => `<article class="campus-item"><h4>${link(item.url,item.title,e)}</h4><p class="field-hint">${e(item.course_title)} · ${e(item.source)} · ${e(statuses[item.availability] || '开放状态未知')} · ${item.submitted === true ? '已提交' : item.submitted === false ? '未提交' : '提交状态未知'}</p><p>截止：${e(time(item.due_at))}${item.overdue ? ' · 已过截止，来源仍允许处理' : ''}${item.score !== null && item.score !== undefined ? ' · 成绩 ' + e(item.score) + ' / ' + e(item.max_score ?? '未提供') : ''}</p><button type="button" class="text-button" data-detail="${e(item.id)}">查看详情与题目</button></article>`;
  return sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = '<div class="campus-toolbar"><label class="checkbox-label"><input data-current type="checkbox" checked>本学期</label><input data-search aria-label="搜索作业" placeholder="搜索作业或课程"></div><div data-lists></div><div class="campus-detail" data-preview aria-live="polite"></div>';
    const draw = () => {
      const query = body.querySelector('[data-search]').value.toLowerCase();
      const values = snapshot.data.assignments.filter(item => (!body.querySelector('[data-current]').checked || item.current) && (item.title + ' ' + item.course_title).toLowerCase().includes(query));
      const pending = snapshot.pending.filter(item => values.some(value => value.id === item.id));
      const groups = new Map();
      for (const item of values) { const key = item.group_id || 'unlinked'; if (!groups.has(key)) groups.set(key,[]); groups.get(key).push(item); }
      body.querySelector('[data-lists]').innerHTML = '<h3>待完成作业</h3><div class="campus-list">' + (pending.map(card).join('') || '<p class="field-hint">没有来源明确开放且尚未提交的本学期作业。</p>') + '</div><h3>按课程查看</h3>' + [...groups.values()].map(items => '<details class="campus-item"><summary>' + e(items[0].course_title) + ' · ' + items.length + ' 项</summary><div class="campus-list">' + items.map(card).join('') + '</div></details>').join('');
      body.querySelectorAll('[data-detail]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
        const detail = await context.api('/detail?assignment_id=' + encodeURIComponent(button.dataset.detail));
        body.querySelector('[data-preview]').innerHTML = '<article class="campus-item"><h3>' + e(detail.assignment.title) + '</h3><p>' + e(detail.assignment.body_text || '该作业未提供可展示的在线题干，可下载题目或查看原站。') + '</p></article>' + records(detail.materials,e);
      }));
    };
    body.querySelector('[data-current]').onchange = draw;
    body.querySelector('[data-search]').oninput = draw;
    draw();
  });
}
