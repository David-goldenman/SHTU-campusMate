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
  const unproject=([x,y])=>[minX+(x-40)/cos/scale,maxY-(y-40)/scale];
  return {polygon, center, point, unproject, width: width * scale + 80, height: height * scale + 80};
}

export function buildingLabel(building) {
  if(building.short_name)return building.short_name;
  return building.name.replace('H1,校园服务中心,309室 IT服务中心','H1 校园服务中心')
    .replace('H2楼,学生科创中心','H2 学生科创中心').replace('数学科学研究所','数学所')
    .replace('创意与艺术学院','创艺学院').replace('创业与管理学院','创管学院')
    .replace('人文科学研究院','人文研究院').replace('上海张江海科雅乐轩酒店','雅乐轩酒店');
}

// Work in screen pixels so labels stay readable at every zoom and viewport size.
export function layoutLabels(items, view, size) {
  const scale=Math.min(size.width/view.w,size.height/view.h);
  if(!Number.isFinite(scale)||scale<=0)return [];
  const offset=[(size.width-view.w*scale)/2,(size.height-view.h*scale)/2];
  const occupied=[{x:size.width-65,y:size.height-170,w:65,h:170},
    {x:size.width-118,y:0,w:118,h:58},{x:0,y:0,w:60,h:70},
    {x:0,y:size.height-28,w:size.width,h:28}],result=[];
  for(const item of items.filter(item=>item.marker)){const x=(item.point[0]-view.x)*scale+offset[0],y=(item.point[1]-view.y)*scale+offset[1];occupied.push({x:x-18,y:y-29,w:36,h:29});}
  const intersects=(a,b)=>a.x<b.x+b.w+5&&a.x+a.w+5>b.x&&a.y<b.y+b.h+4&&a.y+a.h+4>b.y;
  const sorted=[...items].sort((a,b)=>b.priority-a.priority||a.id.localeCompare(b.id));
  for(const item of sorted) {
    const anchor=[(item.point[0]-view.x)*scale+offset[0],(item.point[1]-view.y)*scale+offset[1]];
    if(anchor[0]<6||anchor[0]>size.width-6||anchor[1]<8||anchor[1]>size.height-8)continue;
    const lines=item.label.split('\n'),font=item.kind==='road'?12:14;
    const textWidth=Math.max(...lines.map(line=>[...line].reduce((n,c)=>n+(/[\u2e80-\uffff]/.test(c)?font:font*.58),0)));
    const w=Math.ceil(textWidth+16+(item.kind==='gate'?18:0)),h=lines.length*19+10;
    const pin=item.marker?7:0;
    const candidates=[[0,pin],[-w/2-9,0],[w/2+9,0],[0,-h-pin-4],[-w/2-9,-h],[w/2+9,-h],[0,h+pin+5],
      [-w/2-12,h+8],[w/2+12,h+8],[-w/2-12,-h*2-8],[w/2+12,-h*2-8],[0,-h*3],[0,h*3]];
    let box;
    for(const [dx,dy] of candidates){const trial={x:Math.max(7,Math.min(size.width-w-7,anchor[0]-w/2+dx)),y:Math.max(7,Math.min(size.height-h-7,anchor[1]+dy)),w,h};if(!occupied.some(old=>intersects(trial,old))){box=trial;break;}}
    if(!box)continue;
    occupied.push(box);
    result.push({...item,lines,font,box,anchor,units:1/scale,x:view.x+(box.x-offset[0])/scale,y:view.y+(box.y-offset[1])/scale});
  }
  return result;
}
