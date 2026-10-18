import {renderStudyQuote} from './campus-copy.js';

// The blue-white editions opt into copy; new themes keep their own voice.
export const artTheme = true;
export const openingLines = true;
export const icon = '/assets/themes/assets/observatory-mark.svg';
export const themeColor = id => id === 'observatory' ? '#151e2d' : '#2852b8';
function welcome(home) {
  const caption=home
    ? '<button class="button button-primary study-enter" data-enter-study type="button"><span>开始对话</span><span lang="en">Ask anything</span><span aria-hidden="true">↗</span></button><p class="study-home-note">课程、课表与校园日常，先从一个问题开始。</p>'
    : '<span aria-hidden="true">A LITTLE LESS CAMPUS ARCHAEOLOGY</span><a href="#settings?tab=appearance">切换氛围 <span aria-hidden="true">↗</span></a>';
  const plate='<div class="study-welcome">' +
    '<div class="study-welcome-plate"><div class="study-welcome-copy">' +
    '<span class="study-art-label" aria-hidden="true">A SPACE FOR YOUR CURIOSITY</span>' +
    '<h3 class="study-welcome-title" lang="en"><span>Everything’s on the portal.</span><strong>Somewhere.</strong></h3><p class="study-welcome-translation" lang="zh-CN">所有信息都在学校系统里。<br>至于在哪嘛……</p>' +
    '</div><div class="study-welcome-illustration" role="img" aria-label="蓝白雕版风格的天球、古典雕塑与星图插画"></div>' +
    '<svg class="study-orbit" viewBox="0 0 240 240" fill="none" aria-hidden="true"><circle cx="120" cy="120" r="94"/><ellipse cx="120" cy="120" rx="108" ry="42" transform="rotate(-28 120 120)"/><circle cx="29" cy="157" r="4" fill="currentColor" stroke="none"/></svg>' +
    '</div><div class="study-welcome-caption'+(home?' study-home-caption':'')+'">'+caption+'</div></div>';
  return home?'<div class="study-home-intro">'+plate+renderStudyQuote()+'</div>':plate;
}
export function renderSlot(name,props={}) {
  if (name === 'assistant.home') return welcome(true);
  if (name === 'assistant.welcome') return welcome(false);
  if (name === 'assistant.footer') return renderStudyQuote(props.topic);
}
