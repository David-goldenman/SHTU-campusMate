import {escape} from '../shared.js';

// Selected from the user-provided corpus. Topics are explicit, never inferred from private data.
const quote = (id, en, zh) => Object.freeze({id,en,zh});
export const copyCatalog = Object.freeze({
  general:Object.freeze([
    quote('say-it-again', "We don't say \"as I said earlier.\" We say it again.", '我们不会说“刚才不是讲过了吗”。我们会再讲一遍。'),
    quote('group-replies', 'Your group project finally has someone who replies.', '你的小组作业终于有了一个会回消息的队友。'),
    quote('portal-patience', 'Too many portals. Not enough patience.', '校园系统太多了。人的耐心是有限的。'),
    quote('semester-information', "Your semester is a mess. Your information doesn't have to be.", '这学期已经够乱了，信息就别跟着添乱了。'),
    quote('little-semester', 'So many questions. So little semester.', '问题很多。学期很短。'),
    quote('second-brain', 'Your second brain. No surgery required.', '你的第二大脑。无需开颅手术。'),
    quote('class-questions', 'Now accepting questions you were too afraid to ask in class.', '现已开放接收那些你上课不敢举手问的问题。'),
  ]),
  grades:Object.freeze([
    quote('gpa-called', 'Your GPA called. We need to talk.', '你的GPA有话要说。'),
  ]),
  deadlines:Object.freeze([
    quote('deadline-confusion', "Your deadline isn't moving. Neither is your confusion. Let's fix one of those.", '截止时间不会变。你的困惑也在原地。至少让我们解决其中一个。'),
    quote('deadline-fuel', 'Powered by AI. Fueled by deadlines.', 'AI 驱动，DDL 供能。'),
  ]),
  timetable:Object.freeze([
    quote('timetable-detective', "Your timetable shouldn't require detective skills.", '看个课表不应该需要侦探技能。'),
    quote('calendar-remembers', "Your calendar remembers. So you don't have to.", '你的日历替你记。你就不用记了。'),
  ]),
  documents:Object.freeze([
    quote('search-brain', 'Ctrl+F, but with a brain.', 'Ctrl+F，但长了个脑子。'),
  ]),
});

const selected = new Map();
const prefix = 'campus.copy.v1.';
export function quoteFor(topic = 'general') {
  const name = typeof topic === 'string' && Object.hasOwn(copyCatalog,topic) ? topic : 'general';
  if (selected.has(name)) return selected.get(name);
  const pool = copyCatalog[name];
  let remembered;
  try { remembered = sessionStorage.getItem(prefix + name); } catch { /* Storage may be blocked. */ }
  const candidates = pool.length > 1 ? pool.filter(entry => entry.id !== remembered) : pool;
  const item = candidates[Math.floor(Math.random() * candidates.length)];
  selected.set(name,item);
  try { sessionStorage.setItem(prefix + name,item.id); } catch { /* The module cache remains stable. */ }
  return item;
}

export function renderStudyQuote(topic = 'general') {
  const item = quoteFor(topic);
  return '<div class="study-bilingual-quote"><p lang="en">' + escape(item.en) + '</p><p lang="zh-CN">' + escape(item.zh) + '</p></div>';
}
