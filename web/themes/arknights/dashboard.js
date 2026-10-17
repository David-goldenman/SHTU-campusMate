const symbols = {
  timetable:'<rect x="4" y="5" width="24" height="23"/><path d="M4 12h24M10 2v7M22 2v7M10 18h3m6 0h3m-12 5h3m6 0h3"/>',
  assignments:'<path d="M10 6H5v23h22V6h-5M11 3h10v6H11zM10 17l4 4 8-8"/>',
  courses:'<path d="M16 8C12 5 7 5 3 6v21c5-1 9-1 13 2 4-3 8-3 13-2V6c-4-1-9-1-13 2Zm0 0v21"/>',
  mail:'<rect x="3" y="6" width="26" height="21"/><path d="m3 7 13 11L29 7"/>',
  notifications:'<path d="M8 13a8 8 0 0 1 16 0v7l3 5H5l3-5Zm5 15h6M16 2v3"/>',
  assistant:'<path d="M16 2v6m0 16v6M2 16h6m16 0h6M16 7l9 9-9 9-9-9Z"/>',
};
const icon = id => `<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">${symbols[id]}</svg>`;

export async function mount(container, context) {
  const dispose = () => container.classList.remove('ark-dashboard');
  context.signal.addEventListener('abort', dispose, {once:true});
  container.classList.add('ark-dashboard');
  const available = id => !!document.querySelector(`#navigation [data-nav="${id}"]`);
  const destinations = [
    ['timetable','时间表','TIMETABLE','把握今天，安排下一步。','01'],
    ['assignments','作业管理','ASSIGNMENTS','截止 · 进度 · 提交','02'],
    ['courses','课程中心','COURSES','课程资料与平台整合','03'],
    ['mail','校园邮箱','MAIL','阅读、分类与总结','04'],
    ['notifications','通知中心','NOTICES','关注值得行动的变化','05'],
  ].filter(([id]) => available(id));
  const assistant = !!document.querySelector('[data-module-id="academic-assistant"]');
  container.innerHTML = `<section class="ark-terminal" aria-label="学习终端快捷入口">
    <div class="ark-operator"><div class="ark-operator-grid" aria-hidden="true"></div>
      <div class="ark-operator-meta"><span>ASSISTANT / 001</span><span>罗德岛 · 阿米娅</span></div>
      <span class="ark-operator-word" aria-hidden="true">AMIYA</span>
      <img class="ark-portrait" src="/assets/themes/arknights/assets/amiya.png" alt="值守学习终端的阿米娅" width="646" height="1306" fetchpriority="high">
      <div class="ark-operator-name"><span>YOUR COMPANION</span><strong>阿米娅 <small>AMIYA</small></strong></div>
      <div class="ark-voice"><span>VOICE / 阿米娅</span><p>博士，您还有许多事情需要处理。<br>现在还不能休息哦。</p><i aria-hidden="true"></i></div>
    </div>
    <div class="ark-command"><header class="ark-command-heading"><div><span class="ark-eyebrow">PERSONAL LEARNING TERMINAL</span><h2>欢迎回来，博士。</h2></div><span class="ark-local">本机工作台</span></header>
      <nav class="ark-destinations" aria-label="学习功能">${destinations.map(([id,label,english,description,number]) => `<a class="ark-tile ark-tile-${id}" href="#${id}"><span class="ark-tile-code">${number} / ${english}</span>${icon(id)}<strong>${label}</strong><span class="ark-tile-description">${description}</span></a>`).join('')}
      ${assistant ? `<a class="ark-tile ark-tile-assistant" href="#dashboard?view=assistant"><span class="ark-tile-code">06 / LEARNING SUPPORT</span>${icon('assistant')}<strong>学习助手</strong><span class="ark-tile-description">和资料一起，想清楚。</span></a>` : ''}</nav>
      <footer class="ark-terminal-footer"><span>课程 / 作业 / 日程 / 资料</span><span aria-hidden="true">PRTS — CAMPUS EDITION</span></footer>
    </div>
  </section><div class="ark-briefing-label"><span>DAILY BRIEFING</span><span>今日学习简报</span><span aria-hidden="true">↓</span></div><div class="ark-overview"></div>`;
  const cleanup = await context.defaultView(container.querySelector('.ark-overview'));
  return () => {cleanup?.();dispose();};
}
