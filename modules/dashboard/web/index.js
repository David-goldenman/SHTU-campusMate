import {sourcePanel, records, link, time} from '/assets/campus.js';

export function mount(container,context) {
  const e = context.ui.escape;
  return sourcePanel(container,context,(body,snapshot) => {
    const labels = {ready:'已同步',partial:'部分数据可用',cached:'本地缓存',syncing:'正在同步',error:'读取失败',not_connected:'未连接',login_required:'需要登录',verification_required:'需要验证'};
    const names = {timetable:'教务课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'教学社区',mail:'校园邮箱'};
    body.innerHTML = '<div class="campus-grid">' + [['courses','本学期课程','#courses'],['pending','待完成作业','#assignments'],['materials','课程资料','#courses'],['ready_sources','读取成功的来源','#settings']].map(([key,label,url]) => `<a class="campus-item" href="${url}"><span>${label}</span><h2>${snapshot.stats[key]}</h2></a>`).join('') + '</div><h3>近期截止</h3><div class="campus-list">' + (snapshot.upcoming.map(item => `<article class="campus-item"><h4>${link(item.url,item.title,e)}</h4><p>${e(item.course_title)} · ${e(time(item.due_at))}</p></article>`).join('') || '<p class="field-hint">当前没有明确待完成的近期截止作业。</p>') + '</div><h3>来源状态</h3><div class="campus-grid">' + Object.entries(names).map(([id,name]) => { const source = snapshot.data.metadata.source_metadata[id]; return `<article class="campus-item"><h4>${name}</h4><p>${e(source ? labels[source.status] || source.status : '模块未启用')}</p><p class="field-hint">${e(source?.updated_at ? time(source.updated_at) : '尚未同步')}</p></article>`; }).join('') + '</div><h3>重要通知</h3>' + (snapshot.notifications.map(item => `<article class="campus-item"><h4>${e(item.title)}</h4><p>${e(item.summary)}</p>${item.citations.map(source => link(source.url,source.title,e)).join(' · ')}</article>`).join('') || '<p class="field-hint">在通知页选择提炼重要事项，可查看带来源的通知。</p>') + '<h3>继续你的课程</h3>' + records(snapshot.data.courses.filter(item => item.current).slice(0,6),e);
  });
}
