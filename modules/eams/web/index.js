import {sourcePanel} from '/assets/campus.js';

const BLANK = '当学期没有安排考试时间，请等待。';

export async function mount(container, context) {
  const e = context.ui.escape;
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('./styles.css', import.meta.url);
  document.head.append(style);
  const cache = new Map();
  const state = {drawn: null, semesters: [], semester_id: '', semester: '', batches: [], batch_id: '', batch: '', exams: [], question: '', answer: ''};

  const options = (items, selected) => items.map(item => '<option value="' + e(item.id) + '"' + (item.id === selected ? ' selected' : '') + '>' + e(item.name) + '</option>').join('');

  function examPanel() {
    const list = state.exams.length
      ? '<div class="campus-list">' + state.exams.map(item => '<article class="campus-item"><h4>' + e(item.title) + '</h4><p>' + e([item.date, item.window, item.location].filter(Boolean).join(' · ')) + '</p><p class="field-hint">' + e([item.exam_kind, item.status, item.note].filter(Boolean).join(' · ')) + '</p></article>').join('') + '</div>'
      : '<p class="field-hint">' + BLANK + '</p>';
    return '<section class="panel eams-panel"><h3>考试安排</h3><div class="campus-toolbar"><label>学期<select data-semester>' + options(state.semesters, state.semester_id) + '</select></label>' +
      (state.batches.length > 1 ? '<label>考试批次<select data-batch>' + options(state.batches, state.batch_id) + '</select></label>' : '') +
      '<span class="field-hint">' + e([state.semester, state.batch].filter(Boolean).join(' · ')) + '</span><span data-exam-status role="status"></span></div><div data-exams>' + list + '</div></section>';
  }

  function gpaPanel(data) {
    const gpa = (data.metadata || {}).gpa || {};
    const rows = (gpa.semesters || []).map(item => '<tr><td>' + e(item.label) + '</td><td>' + e(item.courses ?? '') + '</td><td>' + e(item.credits ?? '') + '</td><td>' + e(item.gpa ?? '') + '</td></tr>').join('');
    const details = data.courses.map(item => '<article class="campus-item"><h4>' + e(item.title) + '</h4><p class="field-hint">' + e([item.code, item.term, item.category, item.credits === null ? '' : item.credits + ' 学分', item.score, item.point === null ? '' : item.point + ' 绩点'].filter(Boolean).join(' · ')) + '</p></article>').join('');
    return '<section class="panel eams-panel"><h3>GPA</h3><p class="eams-summary">总绩点 ' + e(gpa.overall ?? '未提供') + ' · 累计获得学分 ' + e(gpa.earned_credits ?? '未提供') + '</p>' +
      (rows ? '<table class="eams-table"><thead><tr><th>学期</th><th>门数</th><th>学分</th><th>平均绩点</th></tr></thead><tbody>' + rows + '</tbody></table>' : '<p class="field-hint">还没有学期成绩记录。</p>') +
      (details ? '<details><summary>课程成绩明细（' + data.courses.length + ' 门）</summary><div class="campus-list">' + details + '</div></details>' : '') + '</section>';
  }

  function planPanel(data) {
    const plan = (data.metadata || {}).study_plan || {};
    const groups = (plan.groups || []).map(group => '<article class="eams-group"><h4>' + e(group.path.join(' / ')) + '</h4><ul>' + group.courses.map(course => '<li>' + e(course.title) + '<span class="field-hint">' + e([course.code, course.credits === null ? '' : course.credits + ' 学分', course.required ? '必修' : '选修', course.terms.length ? '建议第 ' + course.terms.join('、') + ' 学期' : '', course.department, course.note].filter(Boolean).join(' · ')) + '</span></li>').join('') + '</ul></article>').join('');
    return '<section class="panel eams-panel eams-plan"><details><summary>培养方案：' + e(plan.title || '暂无数据') + '</summary>' + (groups || '<p class="field-hint">还没有培养方案数据，请先同步。</p>') + '</details></section>';
  }

  function askPanel() {
    const answer = state.answer ? '<article class="campus-item"><h4>回答</h4><p>' + e(state.answer) + '</p></article>' : '';
    return '<section class="panel eams-panel"><h3>教务问答</h3><p class="field-hint">提问会把当前考试、成绩与培养方案摘要发送到设置中的 DeepSeek 服务，只回答这些数据支持的内容。<a class="text-button" href="#settings">AI 设置</a></p>' +
      '<form class="campus-form" data-ask><label>问题<textarea name="question" required maxlength="4000" placeholder="本学期有哪些考试？我的必修课还有哪些没有修？">' + e(state.question) + '</textarea></label><button class="button button-primary" type="submit">提问</button></form>' +
      '<div data-answer aria-live="polite">' + answer + '</div></section>';
  }


  function mountExam(body) {
    const holder = body.querySelector('[data-exam-holder]');
    const node = document.createElement('div');
    node.innerHTML = examPanel();
    const panel = node.firstElementChild;
    holder.replaceChildren(panel);
    panel.querySelector('[data-semester]').onchange = event => load(body, {semester_id: event.target.value, batch_id: ''});
    const batch = panel.querySelector('[data-batch]');
    if (batch) batch.onchange = event => load(body, {semester_id: state.semester_id, batch_id: event.target.value});
  }

  async function load(body, request) {
    const holder = body.querySelector('[data-exam-holder]');
    holder.querySelectorAll('select').forEach(select => { select.disabled = true; });
    holder.querySelector('[data-exam-status]').textContent = '正在读取…';
    const key = request.semester_id + '|' + request.batch_id;
    try {
      const result = cache.get(key) || await context.api('/exams?' + new URLSearchParams(request));
      cache.set(key, result);
      state.semester_id = result.semester_id;
      state.batch_id = result.batch_id || '';
      state.batch = result.batch || '';
      state.batches = result.batches || state.batches;
      state.semester = result.semester || state.semester;
      state.exams = result.exams || [];
      mountExam(body);
    } catch (error) {
      if (context.signal.aborted) return;
      context.ui.toast(error.message);
      holder.querySelector('[data-exam-status]').textContent = '';
      holder.querySelectorAll('select').forEach(select => { select.disabled = false; });
    }
  }

  async function ask(form) {
    const button = form.querySelector('button');
    const question = form.elements.question.value.trim();
    if (!question || button.disabled) return;
    state.question = question;
    const target = form.parentElement.querySelector('[data-answer]');
    button.disabled = true;
    target.innerHTML = '<p class="field-hint">正在请求回答…</p>';
    try {
      const result = await context.api('/ask', {method: 'POST', body: {question}});
      state.answer = result.answer;
      target.innerHTML = '<article class="campus-item"><h4>回答</h4><p>' + e(result.answer) + '</p></article>';
    } catch (error) {
      target.innerHTML = '';
      if (!context.signal.aborted) context.ui.toast(error.message);
    } finally { button.disabled = false; }
  }

  function draw(body, snapshot) {
    const data = snapshot.data;
    const meta = data.metadata || {};
    const key = String(snapshot.updated_at || '') + '|' + JSON.stringify(data.issues || []);
    if (key === state.drawn) return;
    state.drawn = key;
    state.semesters = meta.semesters || [];
    state.semester_id = meta.semester_id || '';
    state.semester = meta.semester || '';
    state.batches = (meta.exams || {}).batches || [];
    state.batch_id = (meta.exams || {}).batch_id || '';
    state.batch = (meta.exams || {}).batch || '';
    state.exams = data.assignments || [];
    body.innerHTML = '<div class="eams-panels"><div data-exam-holder></div>' + gpaPanel(data) + planPanel(data) + askPanel() + '</div>';
    mountExam(body);
    const form = body.querySelector('[data-ask]');
    form.onsubmit = event => { event.preventDefault(); ask(form); };
  }

  let cleanup;
  try {
    cleanup = await sourcePanel(container, context, draw);
  } catch (error) {
    style.remove();
    throw error;
  }
  return () => { style.remove(); cleanup(); };
}
