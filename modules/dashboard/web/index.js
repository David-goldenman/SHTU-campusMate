import {sourcePanel, link, time} from '/assets/campus.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('campus-overview','overview-compact');
  const card = container.closest('.module-card');
  card.classList.add('overview-card');
  card.style.order = '-1';
  let expanded = false;
  const cleanup = await sourcePanel(container,context,(body,snapshot) => {
    const labels = {ready:'已同步',partial:'部分数据可用',cached:'本地缓存',syncing:'同步中',error:'读取失败',not_connected:'未连接',login_required:'需要登录',verification_required:'需要验证'};
    const sourceNames = {timetable:'课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'教学社区',mail:'邮箱'};
    const typeNames = {class:'课程',deadline:'截止',quiz:'Quiz',presentation:'展示',exam:'考试',activity:'活动',lecture:'讲座',calendar:'校历'};
    const metadata = snapshot.data.metadata.source_metadata || {};
    const waiting = Object.values(metadata).every(source => source.status === 'not_connected');
    if (waiting && snapshot.status !== 'syncing') container.querySelector('[data-status]').textContent = '等待连接账号';
    const issueNode = body.parentElement.querySelector('[data-issues]');
    if (waiting && issueNode) issueNode.textContent = [snapshot.message,...(snapshot.data.issues || [])].filter(Boolean).filter(issue => metadata[String(issue).split(/[:：]/,1)[0].trim()]?.status !== 'not_connected').join('\n');
    const count = key => waiting ? '—' : snapshot.stats[key] ?? '—';
    const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
    body.innerHTML = (waiting ? '<div class="overview-onboarding"><strong>连接账号，开始汇总校园信息</strong><p>连接课程、作业和消息来源后，这里会显示统计与日程。</p><a class="button button-secondary" href="#settings">连接账号 →</a></div>' : '') + '<div class="overview-stats">' + [['courses','本学期课程','#courses'],['pending','待完成作业','#assignments'],['materials','课程资料','#courses'],['ready_sources','已连接来源','#settings']].map(([key,label,url]) => `<a href="${url}"><strong>${e(count(key))}</strong><span>${label}</span></a>`).join('') + '</div><div class="overview-columns"><section><div class="overview-heading"><h3>近期需完成</h3><a href="#assignments">全部作业 →</a></div>' + (snapshot.upcoming.slice(0,4).map(item => `<article class="overview-item"><h4>${link(item.url,item.title,e)}</h4><p>${e(item.course_title || '')}<span>${e(time(item.due_at))} 截止</span></p></article>`).join('') || '<p class="field-hint">暂无明确未完成的近期作业。</p>') + '</section><section><div class="overview-heading"><h3>日程</h3><a href="#timetable">时间表 →</a></div>' + ((snapshot.agenda || []).map(day => '<div class="overview-day"><h4>' + (day.date === today ? '今天' : '明天') + ' <span>' + e(day.date.slice(5)) + '</span></h4>' + (day.events.slice(0,4).map(item => '<p><span>' + (item.all_day ? '全天' : item.at ? e(new Date(item.at).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false})) : '第 ' + item.period_start + ' 节') + '</span><a href="#timetable">' + e(item.title) + '</a><small>' + e(typeNames[item.event_type]) + '</small></p>').join('') || '<p class="field-hint">暂无安排</p>') + '</div>').join('') || '<p class="field-hint">连接课程来源后，可在这里查看近期安排。</p>') + '</section></div><details class="overview-sources"><summary>来源与通知</summary><p>' + Object.entries(sourceNames).map(([id,name]) => {const source = snapshot.data.metadata.source_metadata[id];return name + '：' + e(source ? labels[source.status] || source.status : '未启用');}).join(' · ') + '</p>' + (snapshot.notifications.map(item => '<article class="overview-item"><h4>' + e(item.title) + '</h4><p>' + e(item.summary) + '</p>' + item.citations.map(source => link(source.url,source.title,e)).join(' · ') + '</article>').join('') || '<p class="field-hint">暂无未读重要通知。</p>') + '</details>';
    const details = document.createElement('details'), summary = document.createElement('summary');
    details.className = 'overview-details';summary.textContent = '近期待办与日程';
    const columns = body.querySelector('.overview-columns');
    columns.replaceWith(details);details.append(summary,columns,body.querySelector('.overview-sources'));
    details.open = expanded;details.ontoggle = () => {expanded = details.open;};
  });
  return () => {cleanup();removeStyle();card.classList.remove('overview-card');card.style.removeProperty('order');};
}
