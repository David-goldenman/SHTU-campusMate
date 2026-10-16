import {sourcePanel, link} from '/assets/campus.js';

export function mount(container, context) {
  const e = context.ui.escape;
  return sourcePanel(container, context, (body, snapshot) => {
    const data = snapshot.data;
    body.innerHTML = '<div class="campus-toolbar"><label>教学周 <select data-week><option value="all">全部周次</option>' + Array.from({length:data.metadata.week_count || 18}, (_,index) => `<option value="${index + 1}">第 ${index + 1} 周</option>`).join('') + '</select></label><span>' + e(data.metadata.semester || '') + '</span></div><div class="campus-list" data-grid></div>';
    const draw = () => {
      const week = body.querySelector('[data-week]').value;
      const items = data.timetable.filter(item => week === 'all' || item.weeks.includes(Number(week))).sort((a,b) => a.weekday - b.weekday || a.period_start - b.period_start);
      body.querySelector('[data-grid]').innerHTML = items.length ? items.map(item => `<article class="campus-item"><h4>周${'一二三四五六日'[item.weekday - 1]} · 第 ${item.period_start}–${item.period_end} 节　${link(item.url,item.title,e)}</h4><p>${e(item.teacher)} · ${e(item.location)}</p><p class="field-hint">第 ${e(item.weeks.join('、'))} 周</p></article>`).join('') : '<p class="field-hint">所选周次没有课程安排。</p>';
    };
    body.querySelector('[data-week]').onchange = draw;
    draw();
  });
}
