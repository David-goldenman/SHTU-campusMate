const zone = {timeZone:'Asia/Shanghai'};
const dayFormat = new Intl.DateTimeFormat('sv-SE',zone);
const dateFormat = new Intl.DateTimeFormat('zh-CN',{...zone,month:'long',day:'numeric'});
const clockFormat = new Intl.DateTimeFormat('zh-CN',{...zone,hour:'2-digit',minute:'2-digit',hour12:false});
const hour = 3600000, day = 24 * hour;

function duration(milliseconds) {
  const minutes = Math.floor(milliseconds / 60000), hours = Math.floor(minutes / 60);
  if (hours >= 24) return Math.floor(hours / 24) + ' 天' + (hours % 24 ? ' ' + hours % 24 + ' 小时' : '');
  if (hours) return hours + ' 小时' + (minutes % 60 ? ' ' + minutes % 60 + ' 分钟' : '');
  return minutes ? minutes + ' 分钟' : '不到 1 分钟';
}

// Display only: callers decide which records are still actionable.
export function deadlineInfo(value, now = Date.now()) {
  const timestamp = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(timestamp)) return {timestamp:null,urgency:'unknown',date:'截止时间未提供',clock:'待定',relative:'请查看课程通知',absolute:'截止时间未提供'};
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return {timestamp:null,urgency:'unknown',date:value,clock:'时刻待定',relative:'具体截止时刻未提供',absolute:value + '，具体截止时刻未提供'};
  const gap = timestamp - now, date = new Date(timestamp), today = dayFormat.format(new Date(now));
  const dateKey = dayFormat.format(date), tomorrow = dayFormat.format(new Date(now + day));
  const label = dateKey === today ? '今天 · ' : dateKey === tomorrow ? '明天 · ' : '';
  return {timestamp,urgency:gap <= 0 ? 'overdue' : gap <= day ? 'urgent' : gap <= 7 * day ? 'upcoming' : 'later',
    date:label + (dateKey.slice(0,4) !== today.slice(0,4) ? dateKey.slice(0,4) + '年' : '') + dateFormat.format(date),clock:clockFormat.format(date),
    relative:gap <= 0 ? '已逾期 ' + duration(-gap) : '剩余 ' + duration(gap),
    absolute:dateKey + ' ' + clockFormat.format(date) + '（北京时间）'};
}

export function deadlineMarkup(value, escape, {now = Date.now(), emphasize = true} = {}) {
  const info = deadlineInfo(value,now);
  return `<div class="deadline-stamp" data-urgency="${emphasize ? info.urgency : 'neutral'}"><span class="deadline-date">${escape(info.date)}</span><time ${info.timestamp !== null ? 'datetime="' + escape(value) + '"' : ''} aria-label="${escape(info.absolute)}">${escape(info.clock)}</time>${emphasize ? '<strong class="deadline-relative">' + escape(info.relative) + '</strong>' : ''}</div>`;
}
