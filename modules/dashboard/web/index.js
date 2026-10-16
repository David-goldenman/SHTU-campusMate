import {sourcePanel, records, link, time} from '/assets/campus.js';
import {icon} from '/assets/icons.js';

const sourceNames = {timetable:'教务课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'教学社区',mail:'校园邮箱'};
const sourceLabels = {ready:'已同步',partial:'部分可用',cached:'本地缓存',syncing:'同步中',error:'读取失败',not_connected:'未连接',login_required:'需要登录',verification_required:'需要验证'};

function dueDate(value, escape) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.valueOf())) return '<span>时间</span><strong>待定</strong>';
  const month = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'short'}).format(date);
  const day = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',day:'numeric'}).format(date).replace('日','');
  return '<span>' + escape(month) + '</span><strong>' + escape(day) + '</strong>';
}

export async function mount(container,context) {
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('./styles.css',import.meta.url);
  document.head.append(style);
  const e = context.ui.escape;
  const cleanup = () => style.remove();
  context.signal.addEventListener('abort',cleanup,{once:true});
  try {
    const stop = await sourcePanel(container,context,(body,snapshot) => {
      const metadata = snapshot.data.metadata?.source_metadata || {};
      const courses = snapshot.data.courses || [];
      const upcoming = snapshot.upcoming || [];
      const notifications = snapshot.notifications || [];
      const hasData = Object.values(metadata).some(source => ['ready','cached','partial'].includes(source.status)) || courses.length > 0;
      const noConnection = Object.keys(metadata).length > 0 && Object.values(metadata).every(source => source.status === 'not_connected');
      const issues = container.querySelector('[data-issues]');
      if (noConnection) {
        const otherIssues = (snapshot.data.issues || []).filter(issue => !Object.entries(metadata).some(([id,source]) => source.status === 'not_connected' && String(issue).startsWith(id + ':')));
        issues.textContent = ['连接课程来源后，课程、作业与资料会汇总到这里。',snapshot.message,...otherIssues].filter(Boolean).join('；');
        container.querySelector('[data-status]').textContent = '等待连接账号';
      }
      issues.classList.toggle('dashboard-connect-notice',noConnection);
      const stats = snapshot.stats || {};
      const tiles = [['courses','本学期课程','book','#courses','当前学期的学习安排'],['pending','待完成作业','check','#assignments','仅统计明确待完成的事项'],['materials','课程资料','files','#courses','按课程整理，随时查找'],['ready_sources','已同步来源','link','#settings','教务、课程平台与校园邮箱']];
      body.innerHTML = '<div class="dashboard-stats">' + tiles.map(([key,label,symbol,url,hint],index) => `<a class="dashboard-stat stat-${index}" href="${url}"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon(symbol)}</span></div><strong class="stat-value">${hasData ? e(stats[key] ?? 0) : '—'}</strong><span class="stat-hint">${hasData ? hint : '连接账号后显示'}</span></a>`).join('') + '</div>' +
        '<div class="dashboard-columns"><section class="dashboard-section deadline-section"><header class="dashboard-section-heading"><div><span class="section-kicker">UP NEXT</span><h3>近期截止</h3></div><a class="dashboard-more" href="#assignments">查看作业 ' + icon('arrow') + '</a></header>' +
        (upcoming.length ? '<div class="deadline-list">' + upcoming.map(item => `<article class="deadline-row"><div class="deadline-date">${dueDate(item.due_at,e)}</div><div class="deadline-copy"><h4>${link(item.url,item.title,e)}</h4><p>${e(item.course_title || '课程作业')}</p><span>${icon('clock')}${e(time(item.due_at))}</span></div><span class="deadline-label">待完成</span></article>`).join('') + '</div>' : '<div class="dashboard-empty"><span class="dashboard-empty-icon">' + icon('calendar') + '</span><h4>' + (hasData ? '暂时没有临近截止的作业' : '把下一项重要安排，放在这里') + '</h4><p>' + (hasData ? '有明确截止时间的待办会显示在这里。' : '先连接课程来源，查看你的课程与待办。') + '</p><a class="button button-secondary" href="' + (hasData ? '#assignments' : '#settings') + '">' + (hasData ? '查看全部作业' : '连接账号') + icon('arrow') + '</a></div>') + '</section>' +
        '<section class="dashboard-section sources-section"><header class="dashboard-section-heading"><div><span class="section-kicker">CONNECTIONS</span><h3>来源状态</h3></div><a class="dashboard-more" href="#settings">管理 ' + icon('arrow') + '</a></header><div class="dashboard-sources">' + Object.entries(sourceNames).map(([id,name]) => {
          const source = metadata[id];
          const status = source?.status || 'disabled';
          const initials = {timetable:'教',blackboard:'B',gradescope:'G',piazza:'P',elrc:'社',mail:'邮'};
          return `<div class="dashboard-source"><span class="source-monogram source-${id}" aria-hidden="true">${initials[id]}</span><div><strong>${name}</strong><small>${e(source?.updated_at ? time(source.updated_at) : '尚未同步')}</small></div><span class="source-state source-state-${e(status)}">${e(source ? sourceLabels[status] || status : '未启用')}</span></div>`;
        }).join('') + '</div></section></div>' +
        '<section class="dashboard-section notifications-section"><header class="dashboard-section-heading"><div><span class="section-kicker">STAY IN THE LOOP</span><h3>重要通知 <span class="dashboard-count">' + e(notifications.length) + '</span></h3></div><a class="dashboard-more" href="#notifications">查看通知 ' + icon('arrow') + '</a></header>' +
        (notifications.length ? '<div class="dashboard-notifications">' + notifications.map(item => `<article class="dashboard-notification"><span class="notification-symbol">${icon('bell')}</span><div><h4>${e(item.title)}</h4><p>${e(item.summary)}</p><div class="notification-citations">${(item.citations || []).map(source => link(source.url,source.title,e)).join(' · ')}</div></div></article>`).join('') + '</div>' : '<div class="notification-empty">' + icon('bell') + '<div><strong>重要消息，会在这里汇合</strong><p>连接来源后，可在通知页提炼带来源的重要事项。</p></div></div>') + '</section>' +
        '<section class="dashboard-section continue-section"><header class="dashboard-section-heading"><div><span class="section-kicker">KEEP LEARNING</span><h3>继续你的课程</h3></div><a class="dashboard-more" href="#courses">课程中心 ' + icon('arrow') + '</a></header>' + records(courses.filter(item => item.current).slice(0,6),e) + '</section>';
    });
    return () => { stop?.(); cleanup(); };
  } catch (error) {
    cleanup();
    throw error;
  }
}
