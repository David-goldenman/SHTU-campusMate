const collections = ['assignments', 'materials', 'announcements', 'posts', 'lessons', 'timetable'];

export function courseSummaries(data) {
  const byCourse = new Map();
  for (const kind of collections) {
    for (const item of data[kind] || []) {
      if (!item.course_id) continue;
      if (!byCourse.has(item.course_id)) byCourse.set(item.course_id, {});
      const contents = byCourse.get(item.course_id);
      (contents[kind] ||= []).push(item);
    }
  }
  const source = data.metadata?.source_metadata?.elrc;
  const complete = source?.status === 'ready'
    && !(data.issues || []).some(issue => /^elrc\s*[：:]/i.test(String(issue)))
    && !(data.lessons || []).some(item => item.source === 'elrc' && !item.course_id);
  return (data.courses || []).map(course => {
    const members = [...new Set(course.course_ids || course.sources.map(item => item.id))];
    const contents = Object.fromEntries(collections.map(kind => [kind, members.flatMap(id => byCourse.get(id)?.[kind] || [])]));
    contents.grades = course.sources.flatMap(source => (source.grades || []).map(item => ({...item, source:source.source})));
    const count = contents.lessons.length, linked = course.sources.some(item => item.source === 'elrc');
    const state = count ? 'available' : complete && linked ? 'empty' : 'unknown';
    const recording = {state, count,
      label:count ? `有录播 · ${count} 条` : state === 'empty' ? '暂无录播' : '录播待确认',
      hint:count ? '已收录的录播可在原站打开。' : state === 'empty'
        ? '本次同步没有找到这门课的录播，后续发布后可再次同步。'
        : !linked ? '尚未关联教学社区课程，关联或同步后可确认录播。'
        : '录播来源尚未完成读取或暂时不可用，同步后再确认。'};
    const pending = contents.assignments.filter(item => ['blackboard','gradescope','ecourse'].includes(item.source)
      && item.actionable === true && item.submitted === false && item.exempt !== true
      && [undefined,null,'not_submitted','draft'].includes(item.submission_status)).length;
    return {course, contents, recording, pending};
  });
}

export function termLabel(value) {
  const match = /^(\d{4})-(fall|spring|summer)$/.exec(value || '');
  return match ? `${match[1]} 年${{fall:'秋季',spring:'春季',summer:'夏季'}[match[2]]}` : value || '学期待确认';
}
