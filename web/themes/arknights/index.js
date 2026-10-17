export const icon = '/assets/themes/arknights/assets/terminal-mark.svg';
export const themeColor = () => '#171b1e';

export function renderSlot(name) {
  if (name !== 'assistant.welcome') return;
  return `<div class="study-welcome ark-welcome"><span class="ark-eyebrow">PRTS / LEARNING SUPPORT</span>
    <div class="ark-welcome-symbol" aria-hidden="true"><svg viewBox="0 0 32 32" width="30" height="30" fill="none" stroke="currentColor"><path d="M16 3v26M3 16h26M7 7l18 18M7 25 25 7"/></svg></div><h3>从一个问题，<br>开始下一步。</h3>
    <p>理解课程、安排作业、准备复习。<br>让分散的资料，成为连贯的思路。</p>
    <span class="ark-welcome-foot" aria-hidden="true">THINK CLEARLY. MOVE FORWARD.</span></div>`;
}
