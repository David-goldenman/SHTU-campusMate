import {escape} from '../shared.js';

// Selected from the user-provided corpus. Topics are explicit, never inferred from private data.
const quote = (id, en, zh) => Object.freeze({id,en,zh});
export const copyCatalog = Object.freeze({
  general:Object.freeze([
    quote('group-replies', 'Your group project finally has someone who replies.', '你的小组作业终于有了一个会回消息的队友。'),
    quote('portal-patience', 'Too many portals. Not enough patience.', '校园系统太多了。人的耐心是有限的。'),
    quote('semester-information', "Your semester is a mess. Your information doesn't have to be.", '这学期已经够乱了，信息就别跟着添乱了。'),
    quote('little-semester', 'So many questions. So little semester.', '问题很多。学期很短。'),
    quote('second-brain', 'Your second brain. No surgery required.', '你的第二大脑。无需开颅手术。'),
    quote('your-professor-has-office', "Your professor has office hours. We don't.", '你的教授有固定答疑时间。我们没有这个限制。'),
    quote('we-cant-cancel-your', "We can't cancel your exams. We can make them less terrifying.", '我们没法取消考试。但可以让它没那么可怕。'),
    quote('no-judgment-even-if', "No judgment. Even if it's Week 14 and you're asking about Week 1.", '绝不嫌弃。哪怕已经第十四周了，你还在问第一周的内容。'),
    quote('you-have-37-tabs', 'You have 37 tabs open. None of them are helping.', '你开了 37 个浏览器标签。没一个真正帮上忙。'),
    quote('we-dont-judge-your', "We don't judge your questions. Your search history is another story.", '我们不评价你的问题。至于你的搜索记录嘛……另说。'),
    quote('its-2-am-you', "It's 2 AM. You have questions. We have answers. Your sleep schedule has concerns.", '凌晨两点，你有问题，我们有答案。你的作息表示强烈抗议。'),
    quote('we-cant-fix-your', "We can't fix your procrastination. But we can stop pretending it isn't happening.", '我们治不了你的拖延症。但至少可以停止假装它不存在。'),
    quote('academic-panic-now-with', 'Academic panic. Now with AI support.', '学业焦虑，现在有 AI 技术支持了。'),
    quote('study-smarter-panic-more', 'Study smarter. Panic more efficiently.', '更聪明地学习。更高效地崩溃。'),
    quote('artificial-intelligence-genuine-academic', 'Artificial intelligence. Genuine academic suffering.', '智能是人工的。学业痛苦是真实的。'),
    quote('everythings-on-the-portal', "Everything's on the portal. Somewhere.", '所有信息都在学校系统里。至于在哪嘛……'),
    quote('your-campus-minus-the', 'Your campus, minus the scavenger hunt.', '你的校园，减去满世界找信息的寻宝游戏。'),
    quote('your-university-has-a', 'Your university has a page for that. We know which one.', '学校确实有个网页写了这事。而我们知道是哪个。'),
    quote('your-group-chat-has', 'Your group chat has theories. We have the syllabus.', '你的班群里全是猜测。我们有课程大纲。'),
    quote('we-read-the-80', "We read the 80-page handbook. You're welcome.", '那本 80 页的学生手册我们读了。不用谢。'),
    quote('your-8-am-class', 'Your 8 AM class is still at 8 AM. Sorry.', '你的早八还是早八。很遗憾。'),
    quote('the-syllabus-knows-we', 'The syllabus knows. We asked it.', '课程大纲知道答案。我们替你问过了。'),
    quote('we-cant-skip-class', "We can't skip class for you. We can tell you where it is.", '我们不能替你翘课，但能告诉你课在哪上。'),
    quote('your-university-made-it', 'Your university made it complicated. We made it searchable.', '学校把事情搞复杂了。我们把它变得能搜了。'),
    quote('we-know-more-about', 'We know more about your syllabus than your group chat does.', '我们比你的班群更了解你的课程大纲。'),
    quote('the-deadline-was-in', 'The deadline was in Appendix C. Of course it was.', '截止日期藏在附录 C 里。当然了，不然呢？'),
    quote("we-don-t-say-as-i-said-earlier-we-say-it", "We don't say \"as I said earlier.\" We say it again.", "我们不会说\"刚才不是讲过了吗\"。我们会再讲一遍。"),
    quote("your-deadline-isn-t-moving-neither-is-yo", "Your deadline isn't moving. Neither is your confusion. Let's fix one of those.", "截止时间不会变。你的困惑也在原地。至少让我们解决其中一个。"),
    quote("your-professor-said-it-s-obvious-we-resp", "Your professor said \"it's obvious.\" We respectfully disagree.", "你的教授说\"这不是显而易见吗\"。我们谨慎地表示不同意。"),
    quote("powered-by-ai-fueled-by-deadlines", "Powered by AI. Fueled by deadlines.", "AI 驱动，DDL 供能。"),
    quote("now-accepting-questions-you-were-too-afr", "Now accepting questions you were too afraid to ask in class.", "现已开放接收那些你上课不敢举手问的问题。"),
    quote("no-check-the-portal-is-not-an-answer", "No, \"check the portal\" is not an answer.", "不，\"去系统里看看\"不算一个答案。"),
    quote("your-timetable-shouldn-t-require-detecti", "Your timetable shouldn't require detective skills.", "看个课表不应该需要侦探技能。"),
    quote('say-it-again', 'We don\'t say "as I said earlier." We say it again.', '我们不会说"刚才不是讲过了吗"。我们会再讲一遍。'),
    quote('deadline-not-moving', "Your deadline isn't moving. Neither is your confusion. Let's fix one of those.", '截止时间不会变。你的困惑也在原地。至少让我们解决其中一个。'),
    quote('professor-said-obvious', 'Your professor said "it\'s obvious." We respectfully disagree.', '你的教授说"这不是显而易见吗"。我们谨慎地表示不同意。'),
    quote('too-afraid-to-ask', 'Now accepting questions you were too afraid to ask in class.', '现已开放接收那些你上课不敢举手问的问题。'),
    quote('check-portal-not-answer', 'No, "check the portal" is not an answer.', '不，"去系统里看看"不算一个答案。'),
    quote('timetable-detective', "Your timetable shouldn't require detective skills.", '看个课表不应该需要侦探技能。'),
    quote('syllabus-vs-groupchat', 'The syllabus answers faster than your group chat.', '课程大纲比你的班群回得快。'),
    quote('week-one-question', "It's Week 12. The answer was in Week 1. We brought it back.", '已经第十二周了。答案在第一周。我们把它找回来了。'),
    quote('office-hours-anytime', "Office hours are 2 hours a week. We're the other 166.", '答疑时间一周两小时。剩下 166 小时归我们。'),
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
