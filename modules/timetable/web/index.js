import {sourcePanel, link} from '/assets/campus.js';

const DAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const ACCENTS = ['#5e81ac', '#81a1c1', '#8fbcbb', '#a3be8c', '#d08770', '#b48ead', '#ebcb8b', '#bf616a'];
const WEEKS = 18;
const UNITS = 13;

// 把教学周数组压缩成“第 1–8 周”这样的范围文字。
function ranges(weeks) {
  const sorted = [...new Set(Array.isArray(weeks) ? weeks : [])].sort((a, b) => a - b);
  const parts = [];
  sorted.forEach(week => {
    const tail = parts[parts.length - 1];
    if (tail && week === tail[1] + 1) tail[1] = week;
    else parts.push([week, week]);
  });
  return parts.map(([start, end]) => start === end ? '第 ' + start + ' 周' : '第 ' + start + '–' + end + ' 周').join('、');
}

export async function mount(container, context) {
  const e = context.ui.escape;
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('./styles.css', import.meta.url);
  document.head.append(style);
  const cache = new Map();
  const state = {semesters: [], semester_id: '', year: '', week: 'all', view: null, pending: false};
  let holder = null;
  let cleanup;

  const years = () => [...new Set(state.semesters.map(item => item.school_year))].reverse();
  const terms = () => state.semesters.filter(item => item.school_year === state.year);
  const selected = id => state.semesters.find(item => item.id === id) || {};
  const options = (items, value) => items.map(item => '<option value="' + e(item[0]) + '"' + (item[0] === value ? ' selected' : '') + '>' + e(item[1]) + '</option>').join('');
  const accent = value => ACCENTS[[...String(value)].reduce((sum, char) => sum + char.charCodeAt(0), 0) % ACCENTS.length];

  function block(item) {
    const weeks = state.week === 'all' ? ranges(item.weeks) : '';
    return '<article class="timetable-block" style="border-left-color:' + accent(item.course_id || item.id) + '">' +
      '<h4>' + link(item.url, item.title, e) + '</h4>' +
      '<p>' + e(item.location || '教室未提供') + '</p>' +
      '<p>' + e(item.teacher || '教师未提供') + '</p>' +
      (weeks ? '<p class="timetable-weeks">' + e(weeks) + '</p>' : '') + '</article>';
  }

  // 星期为列、节次为行；同一格里的重叠活动叠放在一起。
  function grid(items, units) {
    const total = Math.max(units || UNITS, ...items.map(item => item.period_end || 0));
    const board = [];
    for (let day = 0; day < 7; day++) {
      board.push({});
      items.filter(item => item.weekday === day + 1).sort((a, b) => a.period_start - b.period_start || a.period_end - b.period_end).forEach(item => {
        const host = board[day][item.period_start];
        if (host) {
          for (let period = host.end + 1; period <= item.period_end; period++) if (!board[day][period]) board[day][period] = host;
          host.end = Math.max(host.end, item.period_end);
          host.blocks.push(item);
          return;
        }
        const cell = {start: item.period_start, end: item.period_end, blocks: [item]};
        for (let period = cell.start; period <= cell.end; period++) board[day][period] = cell;
      });
    }
    const rows = [];
    for (let period = 1; period <= total; period++) {
      const row = ['<th scope="row">第 ' + period + ' 节</th>'];
      for (let day = 0; day < 7; day++) {
        const cell = board[day][period];
        if (!cell) row.push('<td class="timetable-slot"></td>');
        else if (cell.start === period) row.push('<td rowspan="' + (cell.end - cell.start + 1) + '">' + cell.blocks.map(block).join('') + '</td>');
      }
      rows.push('<tr>' + row.join('') + '</tr>');
    }
    return '<div class="timetable-scroll"><table class="timetable-grid"><thead><tr><th scope="col">节次</th>' +
      DAYS.map(day => '<th scope="col">' + day + '</th>').join('') + '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  }
  function toolbar() {
    const view = state.view || {};
    const weeks = Array.from({length: view.week_count || WEEKS}, (_, index) => [String(index + 1), '第 ' + (index + 1) + ' 周']);
    return '<div class="campus-toolbar timetable-toolbar">' +
      '<label>学年<select data-year>' + options(years().map(year => [year, year]), state.year) + '</select></label>' +
      '<label>学期<select data-season>' + options(terms().map(item => [item.id, item.season]), state.semester_id) + '</select></label>' +
      '<label>教学周<select data-week>' + options([['all', '全部周次'], ...weeks], state.week) + '</select></label>' +
      '<span class="field-hint">' + e([view.semester, view.week_count ? '共 ' + view.week_count + ' 周' : ''].filter(Boolean).join(' · ')) + '</span>' +
      '<span data-table-status role="status"></span></div><div data-table></div>';
  }

  function paint() {
    const view = state.view || {timetable: [], units: UNITS};
    if (state.pending) {
      holder.querySelector('[data-table]').innerHTML = '<p class="field-hint">正在读取该学期课表…</p>';
      return;
    }
    const items = (view.timetable || []).filter(item => state.week === 'all' || (Array.isArray(item.weeks) && item.weeks.includes(Number(state.week))));
    const blank = (view.timetable || []).length ? '所选教学周没有课程安排。' : '该学期还没有课表安排，可切换其他学年或学期查看。';
    holder.querySelector('[data-table]').innerHTML = items.length ? grid(items, view.units) : '<p class="field-hint">' + blank + '</p>';
  }

  function render() {
    if (!state.semesters.length) {
      holder.innerHTML = '<p class="field-hint">还没有学期目录，请先同步教务课表。</p>';
      return;
    }
    holder.innerHTML = toolbar();
    holder.querySelector('[data-year]').onchange = event => { state.year = event.target.value; choose((terms()[0] || {}).id || state.semester_id); };
    holder.querySelector('[data-season]').onchange = event => choose(event.target.value);
    holder.querySelector('[data-week]').onchange = event => { state.week = event.target.value; paint(); };
    paint();
  }
  async function choose(semester_id) {
    if (!semester_id) return;
    state.semester_id = semester_id;
    state.year = selected(semester_id).school_year || state.year;
    state.week = 'all';
    if (cache.has(semester_id)) {
      state.view = cache.get(semester_id);
      render();
      return;
    }
    state.view = {semester_id, semester: selected(semester_id).name || '', week_count: 0, units: UNITS, timetable: []};
    state.pending = true;
    render();
    holder.querySelector('[data-table-status]').textContent = '正在读取…';
    holder.querySelectorAll('select').forEach(control => { control.disabled = true; });
    try {
      const value = await context.api('/table?semester_id=' + encodeURIComponent(semester_id));
      cache.set(semester_id, value);
      if (context.signal.aborted || state.semester_id !== semester_id) return;
      state.view = value;
      if ((value.issues || []).length) context.ui.toast(value.issues[0]);
    } catch (error) {
      if (context.signal.aborted) return;
      context.ui.toast(error.message);
      state.view = {semester_id, semester: selected(semester_id).name || '', week_count: 0, units: UNITS, timetable: []};
    }
    state.pending = false;
    render();
  }

  try {
    cleanup = await sourcePanel(container, context, (body, snapshot) => {
      const data = snapshot.data;
      const metadata = data.metadata || {};
      state.semesters = metadata.semesters || [];
      state.semester_id = metadata.semester_id || '';
      state.year = selected(state.semester_id).school_year || (state.semesters.length ? years()[0] : '');
      state.week = 'all';
      state.view = {semester_id: state.semester_id, semester: metadata.semester || '', week_count: metadata.week_count || WEEKS, units: metadata.units || UNITS, timetable: data.timetable || []};
      state.pending = false;
      if (state.semester_id) cache.set(state.semester_id, state.view);
      body.innerHTML = '<section class="panel timetable-panel"><h3>课程表</h3><div data-holder></div></section>';
      holder = body.querySelector('[data-holder]');
      render();
    });
  } catch (error) {
    style.remove();
    throw error;
  }
  return () => { style.remove(); cleanup(); };
}



