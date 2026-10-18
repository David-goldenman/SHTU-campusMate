// Shared by the desktop grid and mobile agenda. Lesson numbers work offline.
export const isLesson = item => Number.isInteger(item.period_start) && Number.isInteger(item.period_end);
export const isCancelledClass = item => item.event_type === 'class' && item.status === 'cancel';

// Navigate with the saved event identity so the map reads the latest adjusted location.
export function campusMapUrl(item) {
  if(!item?.id||!item.location?.trim()||['cancel','leave','moved'].includes(item.status)||['deadline','calendar'].includes(item.event_type)||item.all_day)return '';
  const value=item.at||item.starts_at||'',instant=/T\d{2}:\d{2}.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)?Date.parse(value):NaN;
  const day=Number.isFinite(instant)?new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date(instant)):item.date;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day||'')||!Number.isFinite(Date.parse(day))||!new Date(day).toISOString().startsWith(day))return '';
  return '#campus-map?'+new URLSearchParams({date:day,event:item.id});
}

export function matchesFilter(item, filter = 'all', showCancelled = false) {
  if (isCancelledClass(item) && !showCancelled) return false;
  return filter === 'all' || (filter === 'study'
    ? ['class','deadline','quiz','tutorial','study','presentation','exam'].includes(item.event_type)
    : ['activity','lecture'].includes(item.event_type));
}

export function compareEvents(a, b) {
  if (isLesson(a) && isLesson(b)) {
    return a.period_start - b.period_start || a.period_end - b.period_end || a.id.localeCompare(b.id);
  }
  if (isLesson(a) || isLesson(b)) return isLesson(a) ? -1 : 1;
  return Date.parse(a.at) - Date.parse(b.at) || a.id.localeCompare(b.id);
}

export function eventGroup(item) {
  if (isLesson(item)) return 'class';
  if (item.event_type === 'deadline') return 'deadline';
  if (!item.at || item.all_day || (item.event_type === 'exam' && !item.start_time && item.source !== 'local')) return 'untimed';
  return 'timed';
}

export function periodsFor(calendar, metadata) {
  const classes = calendar.days.flatMap(day => day.events).filter(isLesson);
  const supplied = calendar.periods || metadata.periods || [];
  const numbers = [metadata.units, ...classes.map(item => item.period_end), ...supplied.map(item => item.period)];
  const count = Math.max(0, ...numbers.filter(value => Number.isInteger(value) && value > 0 && value <= 30));
  return Array.from({length:count}, (_,i) => supplied.find(item => item.period === i + 1) || {period:i + 1});
}

export function lessonLayout(events) {
  const lessons = events.filter(isLesson).sort(compareEvents);
  const lanes = [];
  const items = lessons.map(item => {
    let lane = lanes.findIndex(end => end < item.period_start);
    if (lane === -1) lane = lanes.length;
    lanes[lane] = item.period_end;
    return {item, lane:lane + 1};
  });
  return {items, lanes:Math.max(1, lanes.length)};
}

export function applyLessonPositions(container) {
  // CSP rejects inline style attributes; individual CSSOM properties are allowed.
  for (const element of container.querySelectorAll('[data-period-count]')) {
    element.style.setProperty('--period-count',element.dataset.periodCount);
  }
  for (const element of container.querySelectorAll('[data-lesson-lanes]')) {
    element.style.setProperty('--lesson-lanes',element.dataset.lessonLanes);
  }
  for (const element of container.querySelectorAll('[data-lesson-start]')) {
    element.style.gridRow = `${element.dataset.lessonStart} / span ${element.dataset.lessonSpan}`;
    element.style.gridColumn = element.dataset.lessonLane;
  }
}
