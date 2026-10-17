// A decorative plate; chat state and requests stay with the existing conversation.
export const artTheme = true;
export const icon = '/assets/themes/assets/observatory-mark.svg';
export const themeColor = id => id === 'observatory' ? '#151e2d' : '#2852b8';
export function renderSlot(name) {
  if (name !== 'assistant.welcome') return;
  return '<div class="study-welcome">' +
    '<div class="study-welcome-plate"><div class="study-welcome-copy">' +
    '<span class="study-art-label" aria-hidden="true">A SPACE FOR YOUR CURIOSITY</span>' +
    '<h3>让好奇心，<br>找到它的坐标。</h3><p>从一个问题开始，探索更远一点。</p>' +
    '</div><div class="study-welcome-illustration" role="img" aria-label="蓝白雕版风格的天球、古典雕塑与星图插画"></div>' +
    '<svg class="study-orbit" viewBox="0 0 240 240" fill="none" aria-hidden="true"><circle cx="120" cy="120" r="94"/><ellipse cx="120" cy="120" rx="108" ry="42" transform="rotate(-28 120 120)"/><circle cx="29" cy="157" r="4" fill="currentColor" stroke="none"/></svg>' +
    '</div><div class="study-welcome-caption"><span aria-hidden="true">01 / OPEN A NEW ORBIT</span><a href="#settings?tab=appearance">切换氛围 <span aria-hidden="true">↗</span></a></div></div>';
}
