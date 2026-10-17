import {link, time, applyAccent} from '/assets/campus.js';
import {bindSyncNetwork} from '/assets/sync-network.js';
import {mountCampusMoment} from '/assets/themes/campus-moments.js';
import {applyLessonPositions, compareEvents, eventGroup, isCancelledClass, isLesson, lessonLayout, matchesFilter, periodsFor} from './planner.js';

const kinds = {class:'课程',deadline:'作业截止',quiz:'Quiz',tutorial:'习题课',study:'学习',presentation:'展示',exam:'考试',activity:'活动',lecture:'讲座',calendar:'校历'};
const personalKinds = ['quiz','exam','tutorial','study','presentation','activity','lecture'];
const statuses = {leave:'已请假',cancel:'已取消',moved:'已调课',rescheduled:'调课后'};
const zone = {timeZone:'Asia/Shanghai'};
const dayOf = value => new Intl.DateTimeFormat('sv-SE',zone).format(new Date(value));
const clock = value => new Intl.DateTimeFormat('zh-CN',{...zone,hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
const shift = (day,n) => dayOf(new Date(new Date(day + 'T12:00:00+08:00').valueOf() + n * 86400000));

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('week-planner');
  let current = dayOf(Date.now()), snapshot, timer, midnight, request = 0, filter = 'all', showCancelled = false;
  let removeMoment = () => {};
  const cleanup = () => {removeMoment();clearTimeout(timer);clearTimeout(midnight);removeStyle();};
  context.signal.addEventListener('abort',cleanup,{once:true});
  const networkHost = document.createElement('div');
  networkHost.hidden = true;
  const diagnose = bindSyncNetwork(networkHost,context,async () => {await context.api('/schedule/sync',{method:'POST'});await refresh();});

  function when(item) {
    if (item.all_day) return '全天';
    if (isLesson(item)) return '第 ' + item.period_start + '–' + item.period_end + ' 节' + (item.at ? ' · ' + clock(item.at) + (item.ends_at ? '–' + clock(item.ends_at) : '') : ' · 钟点待同步');
    if (item.event_type === 'exam' && !item.start_time && item.source !== 'local') return '时间待公布';
    if (!item.at) return '时间待定';
    return (item.event_type === 'deadline' ? '截止 ' : '') + clock(item.at) + (item.ends_at ? '–' + clock(item.ends_at) : '');
  }
  function card(item) {
    const sport = item.appearance?.icon === 'person-running' ? '<img class="course-sport-icon" src="/assets/vendor/fontawesome/person-running.svg" alt="" aria-hidden="true">' : '';
    const timing = isLesson(item) && item.at ? clock(item.at) + (item.ends_at ? '–' + clock(item.ends_at) : '') : kinds[item.event_type] + ' · ' + when(item);
    return `<button type="button" class="calendar-event kind-${item.event_type}${item.submitted ? ' is-complete' : ''}${['leave','cancel','moved'].includes(item.status) ? ' is-inactive' : ''}" data-event="${e(item.id)}" title="${e([item.title,when(item),item.location,item.appearance?.label,statuses[item.status]].filter(Boolean).join(' · '))}"><span class="calendar-event-meta">${e(timing)}</span><strong>${sport}${e(item.title)}</strong>${statuses[item.status] ? '<span class="calendar-status">' + statuses[item.status] + (item.moved_to ? ' · 至 ' + e(item.moved_to) : '') + '</span>' : ''}${item.location || item.course_title ? '<span>' + e(item.location || item.course_title) + '</span>' : ''}${item.submitted ? '<span>已提交</span>' : ''}</button>`;
  }
  function overviewCard(item) {
    const timed = isLesson(item) ? '第 ' + item.period_start + '–' + item.period_end + ' 节' + (item.at ? ' · ' + clock(item.at) : '')
      : item.event_type === 'exam' && !item.start_time && item.source !== 'local' ? '时间待公布'
      : !item.at ? '时间待定' : (item.event_type === 'deadline' ? '截止 ' : '') + clock(item.at);
    const place = isLesson(item) ? item.location : [item.course_title,item.location].filter(Boolean).join(' · ');
    return `<button type="button" class="overview-item kind-${item.event_type}${item.late ? ' is-late' : ''}${item.submitted ? ' is-complete' : ''}${['leave','cancel','moved'].includes(item.status) ? ' is-inactive' : ''}" data-event="${e(item.id)}" title="${e(item.title + ' · ' + when(item))}">${item.platform ? '<span class="overview-platform">' + e(item.platform) + '</span>' : ''}<strong>${e(item.title)}</strong><span class="overview-meta">${e(timed)}${item.late ? '<em class="overview-late">迟交</em>' : ''}</span>${place ? '<span class="overview-place">' + e(place) + '</span>' : ''}</button>`;
  }
  let overviewOpen=false, weekOpen=true;
  function overviewView(value) {
    if (!value || !value.weeks?.length) return '';
    const today = dayOf(Date.now());
    const weekdays = ['周一','周二','周三','周四','周五','周六','周日'];
    const head = weekdays.map(label => `<th scope="col">${label}</th>`).join('');
    const rows = value.weeks.map(week => {
      const label = Number.isInteger(week.teaching_week) ? '第 ' + week.teaching_week + ' 周' : '第 ? 周';
      const relative = week.week_start === value.week_start ? '本周' : week.offset < 0 ? '上周' : week.offset === 1 ? '下周' : '下下周';
      return `<tr><th scope="row" class="overview-week${week.week_start === value.week_start ? ' is-current' : ''}"><span>${label}</span><strong>${e(week.week_start.slice(5).replace('-','/'))}–${e(week.week_end.slice(5).replace('-','/'))}</strong><small>${relative}</small></th>${week.days.map(day => {
        const items = day.events.filter(item => item.event_type === 'deadline' || item.homework).sort(compareEvents);
        return `<td class="overview-day${day.date === today ? ' is-today' : ''}" data-overview-date="${e(day.date)}">${items.map(overviewCard).join('') || '<span class="overview-empty">—</span>'}</td>`;
      }).join('')}</tr>`;
    }).join('');
    return `<details class="planner-overview" ${overviewOpen ? 'open' : ''}><summary><span>近四周作业日程</span><small>待完成 ${value.pending ?? 0} · 迟交 ${value.late ?? 0}</small></summary><div class="overview-heading"><div><h3 id="overview-title" class="planner-section-title">近四周作业日程</h3><p class="field-hint">固定显示当前教学周前后四周的作业截止，不随上方周切换按钮变化 · 待完成 ${value.pending ?? ''} · 迟交 ${value.late ?? ''}</p></div><span class="overview-platforms">作业平台：Blackboard · Gradescope · E 云课堂</span></div><div class="overview-scroll" tabindex="0" aria-label="近四周作业日程，行为教学周、列为星期"><table class="four-week-grid" data-overview><thead><tr><th scope="col">教学周</th>${head}</tr></thead><tbody>${rows}</tbody></table></div></details>`;
  }
  const groups = [['timed','定时安排'],['deadline','截止事项'],['untimed','全天与时间待定']];
  function weekView(cal, selected, dayClass, title, header) {
    const periods = periodsFor(cal,snapshot.data.metadata);
    const lessons = cal.days.map(day => lessonLayout(day.events.filter(selected)));
    const labels = periods.map(item => `<div class="lesson-period"><strong>第 ${item.period} 节</strong>${item.start && item.end ? '<span>' + e(item.start) + '<br>' + e(item.end) + '</span>' : ''}</div>`).join('');
    const hasClasses = lessons.some(day => day.items.length);
    const missingClock = lessons.some(day => day.items.some(({item}) => !item.at || !item.ends_at));
    const courseTable = hasClasses ? `<h3 class="planner-section-title">课程课表</h3>${missingClock ? '<p class="field-hint">部分课程的具体钟点尚未同步，已按教务节次排列；可点击“同步来源”补充钟点。</p>' : ''}<div class="calendar-table-wrap lesson-table-wrap" tabindex="0" aria-label="每周课程课表"><table class="calendar-table lesson-table" data-calendar><caption class="visually-hidden">${title}，课程按节次排列，北京时间</caption><thead><tr><th scope="col">节次</th>${header}</tr></thead><tbody><tr><th scope="row"><div class="lesson-periods" data-period-count="${periods.length}">${labels}</div></th>${cal.days.map((day,i) => `<td class="${dayClass(day)}"><div class="lesson-day" data-period-count="${periods.length}" data-lesson-lanes="${lessons[i].lanes}">${lessons[i].items.map(({item,lane}) => `<div class="lesson-block" data-lesson-start="${item.period_start}" data-lesson-span="${item.period_end-item.period_start+1}" data-lesson-lane="${lane}">${card(item)}</div>`).join('')}</div></td>`).join('')}</tr></tbody></table></div>` : '<p class="planner-empty">' + (!cal.week_one && snapshot.data.timetable.length ? '课程日期待确认，设置教学周后显示课表。' : '本周没有符合筛选条件的课程。') + '</p>';
    const rows = groups.filter(([kind]) => cal.days.some(day => day.events.some(item => selected(item) && eventGroup(item) === kind))).map(([kind,label]) => `<tr><th scope="row">${label}</th>${cal.days.map(day => `<td class="${dayClass(day)}">${day.events.filter(item => selected(item) && eventGroup(item) === kind).sort(compareEvents).map(card).join('')}</td>`).join('')}</tr>`).join('');
    const otherTable = rows ? `<h3 class="planner-section-title">日程与截止事项</h3><div class="calendar-table-wrap" tabindex="0" aria-label="每周日程与截止事项"><table class="calendar-table" ${hasClasses ? '' : 'data-calendar'}><thead><tr><th scope="col">事项</th>${header}</tr></thead><tbody>${rows}</tbody></table></div>` : '';
    return `<div class="calendar-desktop">${courseTable}${otherTable}</div>`;
  }
  function mobileDay(day, selected) {
    return [['class','按节次安排'],...groups].map(([kind,label]) => {
      const items = day.events.filter(item => selected(item) && eventGroup(item) === kind).sort(compareEvents);
      return items.length ? `<h4>${label}</h4>${items.map(card).join('')}` : '';
    }).join('') || '<p>暂无安排</p>';
  }
  function armMidnight() {
    const now = Date.now();
    const next = new Date(dayOf(now) + 'T00:00:00+08:00').valueOf() + 86400000;
    midnight = setTimeout(async () => {
      if (context.signal.aborted) return;
      try {await refresh();} catch (error) {if (!context.signal.aborted) context.ui.toast(error.message);}
      if (!context.signal.aborted) armMidnight();
    }, Math.max(1000,next - now + 1000));
  }
  async function refresh() {
    clearTimeout(timer);
    const version = ++request;
    const value = await context.api('/schedule?' + new URLSearchParams({week_start:current}));
    if (context.signal.aborted || version !== request) return;
    snapshot = value;
    current = value.calendar.week_start;
    draw();
    if (value.status === 'syncing') timer = setTimeout(() => refresh().catch(error => {if (!context.signal.aborted) context.ui.toast(error.message);}),1500);
  }
  function draw() {
    const today = dayOf(Date.now()), tomorrow = shift(today,1), cal = snapshot.calendar;
    const dayClass = day => day.date === today ? 'is-today' : day.date === tomorrow ? 'is-tomorrow' : '';
    const selected = item => matchesFilter(item,filter,showCancelled);
    const cancelledCount = cal.days.flatMap(day => day.events).filter(isCancelledClass).length;
    const title = `${cal.week_start.slice(5).replace('-','月')}日 — ${cal.week_end.slice(5).replace('-','月')}日`;
    const week = cal.teaching_week > 0 && cal.teaching_week <= (snapshot.data.metadata.week_count || 18) ? '第 ' + cal.teaching_week + ' 教学周' : cal.week_one ? '教学周以外' : '尚未设置教学周';
    const header = cal.days.map((day,i) => `<th scope="col" class="${dayClass(day)}"><span>周${'一二三四五六日'[i]}</span><strong>${day.date.slice(5).replace('-',' / ')}</strong>${day.date === today ? '<em>今天</em>' : day.date === tomorrow ? '<em>明天</em>' : ''}</th>`).join('');
    container.innerHTML = `<div class="planner-heading"><div><h2>${title}</h2><p>${e(snapshot.data.metadata.semester || '我的时间表')} · ${week}</p></div><div class="planner-actions"><button class="button button-secondary" data-settings type="button">学期设置</button><button class="button button-primary" data-add type="button">添加安排</button></div></div>${overviewView(snapshot.overview)}<div class="planner-toolbar"><div class="week-switch"><button class="button button-secondary" data-shift="-7" type="button" aria-label="上一周">上一周</button><button class="button button-secondary" data-today type="button">本周</button><button class="button button-secondary" data-shift="7" type="button" aria-label="下一周">下一周</button><label class="visually-hidden" for="planner-date">跳转日期</label><input id="planner-date" data-date type="date" value="${current}"></div><label class="planner-filter">显示<select data-filter><option value="all">全部安排</option><option value="study">课程与学习</option><option value="life">活动与讲座</option></select></label></div>${!cal.week_one && snapshot.data.timetable.length ? '<p class="notice">设置第 1 教学周的周一日期，即可将课程放入日历。<button class="text-button" data-set-anchor type="button">设置日期</button></p>' : ''}<div class="planner-legend">${Object.entries(kinds).map(([id,label]) => `<span class="legend-${id}">${label}</span>`).join('')}</div><details class="planner-week-detail" ${weekOpen ? 'open' : ''}><summary>本周详情 · 节次、冲突与全部事项</summary>${conflictNotice(cal.conflicts)}${weekView(cal,selected,dayClass,title,header)}</details><div class="calendar-mobile">${cal.days.map((day,i) => `<section class="${dayClass(day)}"><h3>周${'一二三四五六日'[i]} · ${day.date.slice(5)}${day.date === today ? ' · 今天' : day.date === tomorrow ? ' · 明天' : ''}</h3>${mobileDay(day,selected)}</section>`).join('')}</div><div class="planner-footer"><span data-status role="status">${snapshot.status === 'syncing' ? '正在同步…' : snapshot.updated_at ? '更新于 ' + time(snapshot.updated_at) : '尚未同步课程来源'} · 北京时间</span><button class="text-button" data-sync type="button" ${snapshot.status === 'syncing' ? 'disabled' : ''}>同步来源</button></div>${snapshot.data.undated ? '<p class="field-hint">另有 ' + snapshot.data.undated + ' 项未提供日期，可在作业页查看；确定的 Quiz、展示、活动和讲座可手动添加。</p>' : ''}${snapshot.data.issues.length ? '<details class="planner-issues"><summary>来源提示（' + snapshot.data.issues.length + '）</summary><p>' + e(snapshot.data.issues.join('；')) + '</p></details>' : ''}`;
    applyLessonPositions(container);
    const classEvents = new Map(cal.days.flatMap(day=>day.events).map(item=>[item.id,item]));
    container.querySelectorAll('.calendar-event[data-event]').forEach(element=>{
      const appearance = classEvents.get(element.dataset.event)?.appearance;
      if (appearance) { element.dataset.department = appearance.key; applyAccent(element,appearance); }
    });
    if (snapshot.palette?.length) {
      const legend = document.createElement('div');
      legend.className = 'department-legend';
      legend.setAttribute('aria-label','开课院系配色');
      legend.innerHTML = '<strong>开课院系</strong>' + snapshot.palette.map(value=>'<span>' + e(value.label) + '</span>').join('');
      [...legend.querySelectorAll('span')].forEach((element,index)=>applyAccent(element,snapshot.palette[index]));
      container.querySelector('.planner-legend').after(legend);
    }
    const overview=container.querySelector('.planner-overview');
    if(overview)overview.ontoggle=()=>{overviewOpen=overview.open;};
    const weekDetail=container.querySelector('.planner-week-detail');weekDetail.ontoggle=()=>{weekOpen=weekDetail.open;};
    removeMoment();
    if (['observatory','star-notes'].includes(context.theme?.id)) removeMoment = mountCampusMoment(container,'timetable',context.signal);
    container.prepend(networkHost);
    diagnose.update(snapshot.network_failures || []);
    container.querySelectorAll('[data-shift]').forEach(button => button.onclick = act(button,async () => {current = shift(current,Number(button.dataset.shift));await refresh();}));
    container.querySelector('[data-today]').onclick = act(container.querySelector('[data-today]'),async () => {current = today;await refresh();});
    container.querySelector('[data-date]').onchange = event => {if (event.target.value) {current = event.target.value;void refresh().catch(error => context.ui.toast(error.message));}};
    container.querySelector('[data-filter]').value = filter;
    container.querySelector('[data-filter]').onchange = event => {filter = event.target.value;draw();};
    if (cancelledCount) {
      const toggle = document.createElement('label');
      toggle.className = 'planner-cancelled-toggle';
      toggle.innerHTML = `<input type="checkbox" data-show-cancelled>显示已取消课程（${cancelledCount}）`;
      const input = toggle.querySelector('input');
      input.checked = showCancelled;
      input.onchange = () => {showCancelled = input.checked;draw();container.querySelector('[data-show-cancelled]').focus();};
      container.querySelector('.planner-toolbar').append(toggle);
    }
    container.querySelector('[data-sync]').onclick = act(container.querySelector('[data-sync]'),async () => {await context.api('/schedule/sync',{method:'POST'});await refresh();});
    container.querySelector('[data-add]').onclick = () => edit();
    container.querySelector('[data-settings]').onclick = semesterSettings;
    container.querySelector('[data-set-anchor]')?.addEventListener('click',semesterSettings,{signal:context.signal});
    const events = new Map([...cal.days,...(snapshot.overview?.weeks || []).flatMap(week => week.days)].flatMap(day => day.events).map(item => [item.id,item]));
    container.querySelectorAll('[data-event]').forEach(button => button.onclick = () => {
      const item = events.get(button.dataset.event);
      if (!item) return;
      if (item.source === 'local') edit(item); else if (item.event_type === 'class') adjustClass(item); else detail(item);
    });
  }
  const act = (control, action) => context.ui.safeAction(control,action);
  function detail(item) {
    const body = document.createElement('div');
    body.innerHTML = `<p>${e(kinds[item.event_type])} · ${e(when(item))}</p><p>${e([item.course_title,item.location,item.teacher].filter(Boolean).join(' · '))}</p>${item.event_type === 'class' ? '<p class="field-hint">第 ' + item.period_start + '–' + item.period_end + ' 节</p>' : ''}${item.notes ? '<p>' + e(item.notes) + '</p>' : ''}${item.url ? link(item.url,'打开原始来源',e) : ''}`;
    context.ui.dialog(item.title,body);
  }
  function conflictNotice(value) {
    if (!value) return '';
    const items = value.items || [];
    return (items.length ? `<details class="planner-conflicts"><summary>发现 ${items.length} 处时间重叠</summary><ul>${items.slice(0,12).map(item => '<li>' + e(item.date + ' · ' + item.first_title + ' / ' + item.second_title) + '</li>').join('')}</ul></details>` : '') + (value.message ? '<p class="field-hint">' + e(value.message) + '</p>' : '');
  }
  function timingFields(item = {}) {
    const localTime = value => value ? dayOf(value) + 'T' + clock(value) : '';
    const day = item.date || (item.at ? dayOf(item.at) : current);
    return `<label>时间方式<select name="timing"><option value="clock" ${!isLesson(item) ? 'selected' : ''}>具体钟点</option><option value="period" ${isLesson(item) ? 'selected' : ''}>日期与节次</option></select></label><fieldset data-clock-fields class="planner-form-row"><label>开始时间（北京时间）<input name="starts_at" type="datetime-local" value="${localTime(item.starts_at || item.at) || day + 'T09:00'}"></label><label>结束时间（可选）<input name="ends_at" type="datetime-local" value="${localTime(item.ends_at)}"></label></fieldset><fieldset data-period-fields class="planner-form-row"><label>日期<input name="date" type="date" value="${e(day)}"></label><label>开始节次<input name="period_start" type="number" min="1" max="30" value="${item.period_start || 1}"></label><label>结束节次<input name="period_end" type="number" min="1" max="30" value="${item.period_end || item.period_start || 1}"></label></fieldset>`;
  }
  function bindTiming(form) {
    const update = () => {
      const period = form.elements.timing.value === 'period';
      form.querySelector('[data-clock-fields]').hidden = period;
      form.querySelector('[data-clock-fields]').disabled = period;
      form.querySelector('[data-period-fields]').hidden = !period;
      form.querySelector('[data-period-fields]').disabled = !period;
      form.elements.starts_at.required = !period;
      for (const name of ['date','period_start','period_end']) form.elements[name].required = period;
    };
    form.elements.timing.onchange = update;update();
  }
  function timingData(form) {
    if (form.elements.timing.value === 'period') return {date:form.elements.date.value,period_start:Number(form.elements.period_start.value),period_end:Number(form.elements.period_end.value),starts_at:null,ends_at:null};
    return {date:null,period_start:null,period_end:null,starts_at:form.elements.starts_at.value + ':00+08:00',ends_at:form.elements.ends_at.value ? form.elements.ends_at.value + ':00+08:00' : null};
  }
  function edit(item) {
    const form = document.createElement('form');
    form.className = 'campus-form planner-event-form';
    form.innerHTML = `<label>事项名称<input name="title" maxlength="200" required value="${e(item?.title || '')}" placeholder="例如：概率论 Quiz 2"></label><div class="planner-form-row"><label>类型<select name="event_type">${personalKinds.map(type => '<option value="' + type + '">' + kinds[type] + '</option>').join('')}</select></label><label>关联课程<input name="course_title" maxlength="200" value="${e(item?.course_title || '')}"></label></div>${timingFields(item)}<label>地点<input name="location" maxlength="200" value="${e(item?.location || '')}"></label><label>备注<textarea name="notes" rows="2" maxlength="2000">${e(item?.notes || '')}</textarea></label><p class="danger-text" data-error role="alert"></p><div class="form-actions"><button class="button button-primary" type="submit">保存安排</button>${item ? '<button class="text-button danger-text" data-delete type="button">删除安排</button>' : ''}</div>`;
    form.elements.event_type.value = item?.event_type || 'activity';
    bindTiming(form);
    const dialog = context.ui.dialog(item ? '编辑安排' : '添加安排',form);
    const requestId = crypto.randomUUID(), owner = snapshot.account_revision;
    context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
    form.onsubmit = act(form.querySelector('[type=submit]'),async () => {
      if (!form.reportValidity()) return;
      const data = {...Object.fromEntries(new FormData(form)),...timingData(form)};delete data.timing;
      try {await context.api('/commands',{method:'POST',body:{action:item?'update':'create',record_id:item?.id || '',expected_revision:item ? item.revision || '' : undefined,account_revision:owner,request_id:requestId,event:data}});dialog.close();await refresh();}
      catch (error) {if (!context.signal.aborted) form.querySelector('[data-error]').textContent = error.message;}
    });
    form.querySelector('[data-delete]')?.addEventListener('click',act(form.querySelector('[data-delete]'),async () => {
      if (!await context.ui.confirmDialog('删除安排','删除这条手动添加的安排？','删除')) return;
      await context.api('/commands',{method:'POST',body:{action:'delete',record_id:item.id,expected_revision:item.revision || '',account_revision:owner,request_id:crypto.randomUUID()}});dialog.close();await refresh();
    }),{signal:context.signal});
  }
  function adjustClass(item) {
    const form = document.createElement('form');
    form.className = 'campus-form planner-event-form';
    form.innerHTML = `<p>${e(item.original_date + ' · ' + when(item))}<br>${e([item.location,item.teacher,item.appearance?.label].filter(Boolean).join(' · '))}</p><p class="field-hint">记录在本地时间表中。请假审批及学校统一调课仍以学校系统为准。</p><label>调整方式<select name="action" required><option value="">选择要执行的调整</option><option value="leave">请假</option><option value="cancel">取消上课</option><option value="move">调课／修改地点</option><option value="restore">恢复教务原安排</option></select></label><label>影响范围<select name="scope"><option value="once">仅这一次</option><option value="following">本次及本学期后续同一排课</option></select></label><label data-until>调整到哪天（可选，默认学期结束）<input name="until_date" type="date"></label><fieldset data-move-fields>${timingFields(item)}<label>调整后地点<input name="location" maxlength="200" value="${e(item.location || '')}"></label></fieldset><label>备注<textarea name="notes" rows="2" maxlength="2000"></textarea></label><p class="danger-text" data-error role="alert"></p><button class="button button-primary" type="submit">保存课程调整</button>`;
    bindTiming(form);
    const update = () => {
      const moving = form.elements.action.value === 'move';
      form.querySelector('[data-move-fields]').hidden = !moving;
      form.querySelector('[data-move-fields]').disabled = !moving;
      const following = form.elements.scope.value === 'following';
      form.querySelector('[data-until]').hidden = !following;form.elements.until_date.disabled = !following;
    };
    form.elements.action.onchange = update;form.elements.scope.onchange = update;update();
    const dialog = context.ui.dialog(item.title,form);
    const requestId = crypto.randomUUID(), owner = snapshot.account_revision;
    context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
    form.onsubmit = act(form.querySelector('[type=submit]'),async () => {
      if (!form.reportValidity()) return;
      const adjustment = {lesson_id:item.lesson_id,on_date:item.original_date,action:form.elements.action.value,scope:form.elements.scope.value,notes:form.elements.notes.value};
      if (adjustment.scope === 'following' && form.elements.until_date.value) adjustment.until_date = form.elements.until_date.value;
      if (adjustment.action === 'move') {
        const timing = timingData(form);adjustment.to_date = timing.date;delete timing.date;
        Object.assign(adjustment,timing,{location:form.elements.location.value});
      }
      try {
        await context.api('/commands',{method:'POST',body:{action:'adjust_class',record_id:item.id,expected_revision:item.revision || '',account_revision:owner,request_id:requestId,adjustment}});
        dialog.close();await refresh();
      } catch (error) {if (!context.signal.aborted) form.querySelector('[data-error]').textContent = error.message;}
    });
  }
  async function semesterSettings() {
    const settings = await context.api('/calendar-settings');
    if (context.signal.aborted) return;
    const form = document.createElement('form');
    form.className = 'campus-form planner-event-form';
    form.innerHTML = `<p>${e(snapshot.data.metadata.semester || '当前学期')}</p><label>第 1 教学周的周一<input name="week_one" type="date" required value="${settings.week_one || ''}"></label><p class="field-hint">手动日期仅用于本学期；自动更新会保留你的修改。</p><p class="danger-text" data-error role="alert"></p><div class="form-actions"><button class="button button-primary" type="submit">保存手动日期</button><button class="button button-secondary" data-auto type="button">更新学校校历</button></div><p class="field-hint" data-calendar-source></p>`;
    form.querySelector('[data-calendar-source]').textContent = settings.source === 'manual' ? '当前使用手动日期。' : settings.week_one ? '当前使用学校校历日期。' : '尚未确定学期日期，请读取学校校历或手动填写。';
    if (settings.url) form.querySelector('[data-calendar-source]').insertAdjacentHTML('beforeend',' · ' + link(settings.url,'查看学校校历',e));
    if (settings.source === 'manual') {
      const restore = document.createElement('button');
      restore.type = 'button';restore.className = 'text-button';restore.textContent = '恢复学校日期';
      form.querySelector('.form-actions').append(restore);
      restore.onclick = act(restore,async () => {await context.api('/calendar-settings',{method:'DELETE'});dialog.close();await refresh();});
    }
    const dialog = context.ui.dialog('学期与校历',form);
    form.onsubmit = act(form.querySelector('[type=submit]'),async () => {
      try {await context.api('/calendar-settings',{method:'PUT',body:Object.fromEntries(new FormData(form))});dialog.close();await refresh();}
      catch (error) {if (!context.signal.aborted) form.querySelector('[data-error]').textContent = error.message;}
    });
    form.querySelector('[data-auto]').onclick = act(form.querySelector('[data-auto]'),async () => {
      try {await context.api('/calendar/refresh',{method:'POST'});dialog.close();await refresh();}
      catch (error) {if (!context.signal.aborted) form.querySelector('[data-error]').textContent = error.message;}
    });
  }
  try {await refresh();armMidnight();} catch (error) {cleanup();throw error;}
  return cleanup;
}
