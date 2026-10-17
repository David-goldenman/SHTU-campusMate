import {sourcePanel, records, link, time, submissionLabel} from '/assets/campus.js';

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
    return `<article class="campus-item assignment-card" draggable="true" tabindex="0" data-assignment="${e(item.id)}" title="拖动卡片，或聚焦后使用 ↑↓ 调整顺序"><div class="assignment-card-head"><h4>${link(item.url,item.title,e)}</h4><div class="assignment-card-actions">${item.category === 'graded' ? '<span class="assignment-badge">已批改</span>' : ''}${item.needs_review ? '<span class="assignment-badge">待核实</span>' : ''}<button type="button" class="assignment-move" data-move="up" aria-label="上移 ${e(item.title)}" title="上移">↑</button><button type="button" class="assignment-move" data-move="down" aria-label="下移 ${e(item.title)}" title="下移">↓</button><span class="assignment-drag" aria-hidden="true">⠿</span></div></div><p class="field-hint">${e(item.course_title)} · ${e(item.source)} · ${e(statuses[item.availability] || '开放状态未知')} · ${e(submissionLabel(item))}</p><p>截止：${e(time(item.due_at))}${late}${item.submitted_at ? ' · 提交于 ' + e(time(item.submitted_at)) : ''}</p>${score}<button type="button" class="text-button" data-detail="${e(item.id)}">查看详情与题目</button></article>`;
  };
  const cleanup = await sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = '<div class="campus-toolbar"><label class="checkbox-label"><input data-current type="checkbox" checked>本学期</label><input data-search aria-label="搜索作业" placeholder="搜索作业或课程"><span class="assignment-order-hint">拖动卡片或使用 ↑↓ 调整顺序，自动保存</span><span class="visually-hidden" data-order-status role="status"></span></div><div data-lists></div><div class="campus-detail" data-preview aria-live="polite"></div>';
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
      if (saving || !article || event.target.closest('a,button') || !event.dataTransfer) return;
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
      const values = snapshot.data.assignments.filter(item => (!body.querySelector('[data-current]').checked || item.current) && (item.title + ' ' + item.course_title).toLowerCase().includes(query));
      lists.innerHTML = sections.map(([id,label,hint]) => {
        const items = values.filter(item => item.category === id);
        return `<section class="assignment-section" data-section="${id}"><header class="assignment-section-head"><h3>${label}</h3><span class="assignment-count" aria-label="${items.length} 项">${items.length}</span></header><p class="field-hint">${hint}</p><div class="campus-list">${items.map(card).join('') || '<p class="field-hint assignment-empty">没有符合条件的作业。</p>'}</div></section>`;
      }).join('');
      body.querySelectorAll('[data-detail]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
        const detail = await context.api('/detail?assignment_id=' + encodeURIComponent(button.dataset.detail));
        body.querySelector('[data-preview]').innerHTML = '<article class="campus-item"><h3>' + e(detail.assignment.title) + '</h3><p>' + e(submissionLabel(detail.assignment)) + ' · ' + e(detail.assignment.submission_reason || '依据最近同步的原站记录。') + '</p>' + (detail.assignment.checked_at ? '<p class="field-hint">提交情况检查时间：' + e(time(detail.assignment.checked_at)) + '</p>' : '') + '<p>' + e(detail.assignment.body_text || '该作业未提供可展示的在线题干，可下载题目或查看原站。') + '</p></article>' + records(detail.materials,e);
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
