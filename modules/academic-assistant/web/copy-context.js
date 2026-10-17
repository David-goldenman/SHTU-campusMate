// Only explicit user text selects a presentation topic; no API calls or storage.
export function copyTopic(text) {
  if (typeof text !== 'string') return 'general';
  if (/绩点|均绩|成绩|学分绩|\b(?:gpa|cgpa|grades?|scores?|transcript)\b/i.test(text)) return 'grades';
  if (/作业|截止|到期|\b(?:ddl|deadlines?|homework|assignments?)\b|\bdue\s+(?:date|soon|tomorrow|today|this|next)\b/i.test(text)) return 'deadlines';
  if (/课表|排课|课程表|课程安排|下(?:一)?(?:节|堂)课|\b(?:timetable|class\s+schedule|course\s+schedule|schedule\s+classes|next\s+(?:class|lecture))\b/i.test(text)) return 'timetable';
  if (/讲义|大纲|资料|课件|教材|\b(?:pdf|syllabus|handouts?|lecture\s+notes|documents?|course\s+materials)\b/i.test(text)) return 'documents';
  return 'general';
}

export function latestUserText(messages) {
  if (!Array.isArray(messages)) return '';
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'user') return typeof messages[i].text === 'string' ? messages[i].text : '';
  }
  return '';
}

export function studyCopyText(messages, draft) {
  return typeof draft === 'string' && draft.trim() ? draft : latestUserText(messages);
}
