const zone = {timeZone: 'Asia/Shanghai'};
export const today = () => new Intl.DateTimeFormat('sv-SE', zone).format(new Date());
export const shiftDay = (day, count) => new Intl.DateTimeFormat('sv-SE', zone).format(new Date(Date.parse(day + 'T12:00:00+08:00') + count * 86400000));
export function validDay(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value || '') && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().startsWith(value);
}
const normalize = text => String(text || '').normalize('NFKC').toLowerCase().replace(/\s+/g, '').replace(/号楼/g, '');

export function matchLocation(location, buildings) {
  const text = normalize(location);
  if (!text) return {status: 'missing', buildings: []};
  const matches = buildings.filter(building => building.aliases.some(alias => {
    const name = normalize(alias);
    if (['东门','南门','西门','北门','东南门'].includes(name)) return text === name || text === '学校' + name || text === '校' + name;
    let index = text.indexOf(name);
    while (index >= 0) {
      const before = text[index - 1] || '', after = text[index + name.length] || '';
      if (!(/[a-z0-9]/.test(name[0]) && /[a-z0-9]/.test(before)) && !(/\d$/.test(name) && /\d/.test(after)) && !(/[a-z]$/.test(name) && /[a-z]/.test(after))) return true;
      index = text.indexOf(name, index + 1);
    }
    return false;
  }));
  return {status: matches.length === 1 ? 'matched' : matches.length ? 'ambiguous' : 'unknown', buildings: matches};
}

export function eventTime(item) {
  if (item.all_day) return '全天';
  if (item.event_type === 'exam' && item.source !== 'local' && !item.start_time) return '时间待公布';
  const at = item.at || item.starts_at;
  const clock = value => {
    const date = new Date(value);
    return value && Number.isFinite(date.valueOf()) ? new Intl.DateTimeFormat('zh-CN', {...zone, hour: '2-digit', minute: '2-digit', hour12: false}).format(date) : '';
  };
  const start = clock(at), end = clock(item.ends_at);
  const period = item.period_start ? '第 ' + item.period_start + (item.period_end && item.period_end !== item.period_start ? '–' + item.period_end : '') + ' 节' : '';
  if (!start) return period ? period + ' · 钟点待同步' : '时间待定';
  return (item.event_type === 'deadline' ? '截止 ' : '') + start + (end ? '–' + end : '') + (period ? ' · ' + period : '');
}

export function projectCampus(data) {
  const points = [...data.campus.polygon, ...data.buildings.flatMap(item => item.polygon)];
  const minX = Math.min(...points.map(p => p[0])), maxY = Math.max(...points.map(p => p[1]));
  const cos = Math.cos(maxY * Math.PI / 180);
  const width = (Math.max(...points.map(p => p[0])) - minX) * cos;
  const height = maxY - Math.min(...points.map(p => p[1]));
  const scale = Math.min(920 / width, 680 / height);
  const point = ([x,y]) => [40 + (x - minX) * cos * scale, 40 + (maxY - y) * scale];
  const polygon = points => points.map(p => point(p).map(n => n.toFixed(2)).join(',')).join(' ');
  const center = points => {const xy = points.map(point);return [xy.reduce((s,p) => s+p[0],0)/xy.length, xy.reduce((s,p) => s+p[1],0)/xy.length];};
  return {polygon, center, width: width * scale + 80, height: height * scale + 80};
}
