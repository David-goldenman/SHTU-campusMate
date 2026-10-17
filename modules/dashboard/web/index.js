import {sourcePanel, link} from '/assets/campus.js';
import {deadlineInfo, deadlineMarkup} from '/assets/deadlines.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('campus-overview','overview-compact');
  const card = container.closest('.module-card');
  card.classList.add('overview-card');
  let expanded = false, latest, host, timer;
  const dispose = () => {clearInterval(timer);removeStyle();card.classList.remove('overview-card');};
  context.signal.addEventListener('abort',dispose,{once:true});
  const sourceNames = {timetable:'课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'教学社区',mail:'邮箱'};
  const typeNames = {class:'课程',deadline:'截止',quiz:'Quiz',presentation:'展示',exam:'考试',activity:'活动',lecture:'讲座',calendar:'校历'};
  function draw(body,snapshot) {
    const labels = {ready:'已同步',partial:'部分数据可用',cached:'本地缓存',syncing:'同步中',error:'读取失败',not_connected:'未连接',login_required:'需要登录',verification_required:'需要验证'};
    const metadata = snapshot.data.metadata.source_metadata || {};
    const waiting = Object.values(metadata).every(source => source.status === 'not_connected');
    if (waiting && snapshot.status !== 'syncing') container.querySelector('[data-status]').textContent = '等待连接账号';
    const issueNode = body.parentElement.querySelector('[data-issues]');
    if (waiting && issueNode) issueNode.textContent = [snapshot.message,...(snapshot.data.issues || [])].filter(Boolean).filter(issue => metadata[String(issue).split(/[:：]/,1)[0].trim()]?.status !== 'not_connected').join('\n');
    const now = Date.now(), zone = {timeZone:'Asia/Shanghai'};
    const dayOf = value => new Intl.DateTimeFormat('sv-SE',zone).format(new Date(value));
    const today = dayOf(now), tomorrow = dayOf(now + 86400000);
    const pending = (snapshot.pending || snapshot.upcoming || []).map(item => ({...item,deadline:deadlineInfo(item.due_at,now)}));
    const dated = pending.filter(item => item.deadline.timestamp !== null).sort((a,b) => a.deadline.timestamp - b.deadline.timestamp);
    const overdue = dated.filter(item => item.deadline.urgency === 'overdue');
    const upcoming = dated.filter(item => item.deadline.urgency !== 'overdue');
    const urgent = upcoming.filter(item => item.deadline.urgency === 'urgent');
    const unknown = pending.length - dated.length;
    const task = item => `<article class="overview-task" data-priority="${item.deadline.urgency}"><div><p class="overview-course">${e(item.course_title || '待完成作业')}</p><h4>${link(item.url,item.title,e)}</h4></div>${deadlineMarkup(item.due_at,e,{now})}</article>`;
    const agenda = (snapshot.agenda || []).map(day => {
      const events = day.events.filter(item => !['leave','cancel','moved'].includes(item.status) && item.event_type !== 'deadline' && !(day.date === today && item.ends_at && Date.parse(item.ends_at) < now));
      return `<div class="overview-day"><h4>${day.date === today ? '今天' : day.date === tomorrow ? '明天' : e(day.date)} <span>${e(day.date.slice(5).replace('-',' / '))}</span></h4>${events.slice(0,4).map(item => {
        const when = item.all_day ? '全天' : item.event_type === 'exam' && item.source !== 'local' && !item.start_time ? '时间待公布' : item.at ? new Intl.DateTimeFormat('zh-CN',{...zone,hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(item.at)) : item.period_start ? '第 ' + item.period_start + ' 节' : '时间待定';
        return `<a class="overview-agenda-item" href="#timetable"><time>${e(when)}</time><span><strong>${e(item.title)}</strong><small>${e([typeNames[item.event_type],item.location].filter(Boolean).join(' · '))}</small></span></a>`;
      }).join('') || '<p class="field-hint">' + (day.date === today ? '今天没有后续安排。' : '暂无安排。') + '</p>'}${events.length > 4 ? '<a class="text-button" href="#timetable">还有 ' + (events.length - 4) + ' 项，查看时间表 →</a>' : ''}</div>`;
    }).join('');
    const count = key => waiting ? '—' : snapshot.stats[key] ?? '—';
    body.innerHTML = `<header class="overview-focus-heading"><div><p>今日重点 · ${e(new Intl.DateTimeFormat('zh-CN',{...zone,month:'long',day:'numeric',weekday:'long'}).format(new Date(now)))}</p><h2>待办与截止</h2></div><a class="button button-primary" href="#assignments">查看全部作业 →</a></header>` +
      (waiting ? '<div class="overview-onboarding"><strong>连接账号，查看你的待办</strong><p>连接课程与作业来源后，这里会显示截止时间和日程。</p><a class="button button-secondary" href="#settings">连接账号 →</a></div>' : '') +
      `<div class="overview-attention"><a href="#assignments?view=urgent" data-tone="urgent"><span>24 小时内截止</span><strong>${waiting ? '—' : urgent.length}<small>项</small></strong></a><a href="#assignments?view=overdue" data-tone="overdue"><span>已逾期 · 仍可处理</span><strong>${waiting ? '—' : overdue.length}<small>项</small></strong></a><a href="#assignments"><span>待完成作业</span><strong>${e(count('pending'))}<small>项</small></strong></a></div>
      <div class="overview-columns overview-priorities"><section><div class="overview-heading"><h3>最近截止</h3><span class="field-hint">北京时间</span></div><div class="overview-task-list">${upcoming.slice(0,4).map(task).join('') || '<p class="overview-empty">' + (waiting ? '连接账号后显示近期 DDL。' : '暂时没有已知截止时间的后续待办。') + '</p>'}</div>${overdue.length ? '<div class="overview-overdue"><div class="overview-heading"><h3>已逾期待处理</h3><a href="#assignments?view=overdue">查看 ' + overdue.length + ' 项 →</a></div>' + overdue.slice(-2).reverse().map(task).join('') + '</div>' : ''}${unknown ? '<a class="overview-undated" href="#assignments?view=undated">另有 ' + unknown + ' 项待办的截止时间待定 →</a>' : ''}</section><section class="overview-agenda"><div class="overview-heading"><h3>今天与明天</h3><a href="#timetable">时间表 →</a></div>${agenda || '<p class="overview-empty">暂无可用日程，连接课程来源后显示。</p>'}</section></div>
      <details class="overview-sources"><summary>课程统计、来源与通知</summary><div class="overview-stats">${[['courses','本学期课程','#courses'],['pending','待完成作业','#assignments'],['materials','课程资料','#courses'],['ready_sources','已连接来源','#settings']].map(([key,label,url]) => `<a href="${url}"><strong>${e(count(key))}</strong><span>${label}</span></a>`).join('')}</div><p>${Object.entries(sourceNames).map(([id,name]) => {const source = metadata[id];return name + '：' + e(source ? labels[source.status] || source.status : '未启用');}).join(' · ')}</p>${(snapshot.notifications || []).map(item => '<article class="overview-item"><h4>' + e(item.title) + '</h4><p>' + e(item.summary) + '</p>' + (item.citations || []).map(source => link(source.url,source.title,e)).join(' · ') + '</article>').join('') || '<p class="field-hint">暂无未读重要通知。</p>'}</details>`;
    const details = body.querySelector('.overview-sources');
    details.open = expanded;details.ontoggle = () => {expanded = details.open;};
  }
  const cleanup = await sourcePanel(container,context,(body,snapshot) => {
    latest=snapshot;host=body;draw(body,snapshot);
    container.append(container.querySelector('.source-toolbar'),container.querySelector('[data-issues]'));
  });
  if (!context.signal.aborted) timer=setInterval(()=>{if(latest && !container.contains(document.activeElement))draw(host,latest);},60000);
  return () => {cleanup();dispose();};
}
