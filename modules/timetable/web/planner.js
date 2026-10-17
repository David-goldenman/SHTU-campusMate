// Shared by the desktop grid and mobile agenda. Lesson numbers work offline.
export function compareEvents(a, b) {
  if (a.event_type === 'class' && b.event_type === 'class') {
    return a.period_start - b.period_start || a.period_end - b.period_end || a.id.localeCompare(b.id);
  }
  if (a.event_type === 'class' || b.event_type === 'class') return a.event_type === 'class' ? -1 : 1;
  return Date.parse(a.at) - Date.parse(b.at) || a.id.localeCompare(b.id);
}

export function eventGroup(item) {
  if (item.event_type === 'class') return 'class';
  if (item.event_type === 'deadline') return 'deadline';
  if (!item.at || item.all_day || (item.event_type === 'exam' && !item.start_time)) return 'untimed';
  return 'timed';
}

export function periodsFor(calendar, metadata) {
  const classes = calendar.days.flatMap(day => day.events).filter(item => item.event_type === 'class');
  const supplied = calendar.periods || metadata.periods || [];
  const numbers = [metadata.units, ...classes.map(item => item.period_end), ...supplied.map(item => item.period)];
  const count = Math.max(0, ...numbers.filter(value => Number.isInteger(value) && value > 0 && value <= 30));
  return Array.from({length:count}, (_,i) => supplied.find(item => item.period === i + 1) || {period:i + 1});
}

export function lessonLayout(events) {
  const lessons = events.filter(item => item.event_type === 'class').sort(compareEvents);
  const lanes = [];
  const items = lessons.map(item => {
    let lane = lanes.findIndex(end => end < item.period_start);
    if (lane === -1) lane = lanes.length;
    lanes[lane] = item.period_end;
    return {item, lane:lane + 1};
  });
  return {items, lanes:Math.max(1, lanes.length)};
}
