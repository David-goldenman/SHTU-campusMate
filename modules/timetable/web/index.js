import {sourcePanel, link, time} from '/assets/campus.js';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  let week = 'all', range = 'upcoming', kind = 'all';
  const schedule = {...context,api:(path,options) => context.api(path === '/snapshot' ? '/schedule' : '/schedule/sync',options)};
  const cleanup = await sourcePanel(container, schedule, (body, snapshot) => {
    const data = snapshot.data;
    body.innerHTML = '<h3>每周上课安排</h3><div class="campus-toolbar"><label>教学周 <select data-week><option value="all">全部周次</option>' + Array.from({length:data.metadata.week_count || 18}, (_,index) => `<option value="${index + 1}">第 ${index + 1} 周</option>`).join('') + '</select></label><span>' + e(data.metadata.semester || '') + '</span></div><div class="campus-list" data-grid></div><h3 class="timetable-events-heading">Quiz、作业与考试</h3><p class="field-hint">按北京时间排列各来源已同步的事项；考试显示开始时间，作业与 quiz 显示截止时间。</p><p class="field-hint" data-source-times></p><div class="campus-toolbar"><label>时间范围<select data-range><option value="upcoming">即将到来</option><option value="all">全部时间</option><option value="past">已过去</option></select></label><label>事项类型<select data-kind><option value="all">全部事项</option><option value="deadline">Quiz / 作业</option><option value="exam">教务考试</option></select></label></div><div class="campus-list" data-events></div><p class="field-hint" data-undated></p>';
    const names = {timetable:'教务课表',blackboard:'Blackboard',gradescope:'Gradescope',eams:'教务系统'};
    body.querySelector('[data-source-times]').textContent = Object.entries(snapshot.sources).map(([id,source]) => names[id] + '：' + (source.updated_at ? time(source.updated_at) : '暂无缓存')).join('；');
    body.querySelector('[data-week]').value = week;
    body.querySelector('[data-range]').value = range;
    body.querySelector('[data-kind]').value = kind;
    const draw = () => {
      week = body.querySelector('[data-week]').value;
      const items = data.timetable.filter(item => week === 'all' || item.weeks.includes(Number(week))).sort((a,b) => a.weekday - b.weekday || a.period_start - b.period_start);
      body.querySelector('[data-grid]').innerHTML = items.length ? items.map(item => `<article class="campus-item"><h4>周${'一二三四五六日'[item.weekday - 1]} · 第 ${item.period_start}–${item.period_end} 节　${link(item.url,item.title,e)}</h4><p>${e(item.teacher)} · ${e(item.location)}</p><p class="field-hint">第 ${e(item.weeks.join('、'))} 周</p></article>`).join('') : '<p class="field-hint">所选周次没有课程安排。</p>';
    };
    const drawEvents = () => {
      range = body.querySelector('[data-range]').value;
      kind = body.querySelector('[data-kind]').value;
      const now = Date.now();
      const events = data.events.filter(item => {
        const at = new Date(item.at).valueOf() + (item.event_type === 'exam' && !item.start_time ? 86400000 : 0);
        return (kind === 'all' || item.event_type === kind) && (range === 'all' || (range === 'past' ? at < now : at >= now));
      });
      body.querySelector('[data-events]').innerHTML = events.length ? events.map(item => {
        const exam = item.event_type === 'exam';
        const when = exam && !item.start_time ? item.date + ' · 具体时间待公布' : time(item.at);
        const status = exam ? item.window : item.submitted === true ? '已提交' : item.submitted === false ? '未提交' : '提交状态待确认';
        return `<article class="campus-item"><p class="field-hint">${exam ? '考试开始' : '截止'} · ${e(when)} · ${e(names[item.source] || item.source)}</p><h4>${link(item.url,item.title,e)}</h4><p>${e([item.course_title, item.location, status, item.stale ? '上次缓存' : ''].filter(Boolean).join(' · '))}</p>${item.note ? '<p>' + e(item.note) + '</p>' : ''}</article>`;
      }).join('') : '<p class="field-hint">当前范围没有已提供时间的事项。请同步数据，或切换时间范围。</p>';
    };
    body.querySelector('[data-week]').onchange = draw;
    body.querySelector('[data-range]').onchange = drawEvents;
    body.querySelector('[data-kind]').onchange = drawEvents;
    body.querySelector('[data-undated]').textContent = data.undated ? '另有 ' + data.undated + ' 条事项未提供有效时间，可在作业管理或教务系统查看。' : '';
    draw();
    drawEvents();
  }).catch(error => { removeStyle(); throw error; });
  return () => { cleanup(); removeStyle(); };
}
