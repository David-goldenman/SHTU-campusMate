import {escape} from '../shared.js';
import {quoteFor} from './campus-copy.js';

const slogan=(id,lead,accent,zh)=>Object.freeze({id,lead,accent,zh});
export const homeSlogans=Object.freeze([
  slogan('portal-somewhere', "Everything’s on the portal.", 'Somewhere.', '所有信息都在学校系统里。至于在哪嘛……'),
  slogan('campus-without-hunt', 'Your campus,', 'minus the scavenger hunt.', '你的校园，减去满世界找信息的寻宝游戏。'),
  slogan('portal-not-answer', 'No, "check the portal"', 'is not an answer.', '不，“去系统里看看”不算一个答案。'),
  slogan('university-page', 'Your university has a page for that.', 'We know which one.', '学校确实有个网页写了这件事。而我们知道是哪个。'),
  slogan('portal-patience', 'Too many portals.', 'Not enough patience.', '校园系统太多了。人的耐心是有限的。'),
  slogan('group-chat-syllabus', 'Your group chat has theories.', 'We have the syllabus.', '你的班群里全是猜测。我们有课程大纲。'),
]);
const key='campus.home-slogan.v1';
const canonical=text=>text.normalize('NFKC').replace(/[‘’]/g,"'").replace(/[“”]/g,'"').replace(/\s+/g,' ').trim().toLowerCase();
let selected;
export function homeSlogan() {
  if(selected)return selected;
  // The smaller general greeting stays independent, without repeating the hero.
  const greeting=canonical(quoteFor().en);
  const eligible=homeSlogans.filter(item=>canonical(item.lead+' '+item.accent)!==greeting);
  let previous;
  try {previous=sessionStorage.getItem(key);} catch { /* Storage is optional. */ }
  const candidates=eligible.filter(item=>item.id!==previous);
  const pool=candidates.length?candidates:eligible;
  selected=pool[Math.floor(Math.random()*pool.length)];
  try {sessionStorage.setItem(key,selected.id);} catch { /* Keep this page stable in memory. */ }
  return selected;
}
export function renderHomeSlogan() {
  const item=homeSlogan();
  return '<h3 class="study-welcome-title" lang="en"><span>'+escape(item.lead)+'</span><strong>'+escape(item.accent)+'</strong></h3><p class="study-welcome-translation" lang="zh-CN">'+escape(item.zh)+'</p>';
}
