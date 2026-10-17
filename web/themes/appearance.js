const key = 'campus.appearance.v1';
export const themes = Object.freeze({
  observatory: {name:'观星台', english:'OBSERVATORY', description:'雕塑、天球与深钴蓝。把好奇心，放在更远的地方。'},
  'star-notes': {name:'星夜手记', english:'STAR NOTES', description:'星图、纸页与轻盈线条。为日常，留一点遐想。'}
});
const companion = value => ['female','male','hidden'].includes(value) ? value : 'female';
export function normalizeAppearance(value) {
  if (!value || typeof value !== 'object') value = {};
  return {
    theme:Object.hasOwn(themes,value.theme) ? value.theme : 'observatory',
    companions:{observatory:companion(value.companions?.observatory), 'star-notes':companion(value.companions?.['star-notes'])},
    moments:{dashboard:value.moments?.dashboard !== false,timetable:value.moments?.timetable !== false},
    reduceMotion:value.reduceMotion === true
  };
}
let state;
try { state = normalizeAppearance(JSON.parse(localStorage.getItem(key))); }
catch { state = normalizeAppearance(); }
export function getAppearance() { return {...state,companions:{...state.companions},moments:{...state.moments}}; }
function apply() {
  document.documentElement.dataset.artTheme = state.theme;
  document.documentElement.dataset.artMotion = state.reduceMotion ? 'reduced' : 'system';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',state.theme === 'observatory' ? '#173caa' : '#2852b8');
  document.querySelectorAll('[data-theme-name]').forEach(node => {node.textContent = themes[state.theme].name;});
}
export function setAppearance(patch) {
  state = normalizeAppearance({...state,...patch,companions:{...state.companions,...patch.companions},moments:{...state.moments,...patch.moments}});
  let saved = true;
  try { localStorage.setItem(key,JSON.stringify(state)); } catch { saved = false; }
  apply();
  window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
  return saved;
}
apply();
window.addEventListener('storage',event => {
  if (event.key !== key && event.key !== null) return;
  try { state = normalizeAppearance(event.newValue ? JSON.parse(event.newValue) : null); }
  catch { state = normalizeAppearance(); }
  apply();
  window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
});
export function appearancePanel() {
  const cards = Object.entries(themes).map(([id,theme]) =>
    '<label class="art-theme-choice"><input type="radio" name="art-theme" value="' + id + '">' +
    '<span class="art-theme-card"><img src="/assets/themes/assets/' + id + '-hero.webp" alt="" width="720" height="360" loading="lazy">' +
    '<span class="art-theme-meta"><strong>' + theme.name + '</strong><span data-choice-state="' + id + '"></span></span>' +
    '<span class="art-theme-description">' + theme.description + '</span></span></label>').join('');
  return '<section class="panel settings-section appearance-panel" aria-labelledby="appearance-title">' +
    '<header class="art-settings-heading"><span class="art-overline" aria-hidden="true">A LITTLE ROOM FOR WONDER</span>' +
    '<h2 id="appearance-title">让工作台，有一点自己的样子。</h2><p>两种蓝色，一样清楚。选择你喜欢的氛围。</p></header>' +
    '<fieldset class="art-theme-field"><legend>界面主题</legend><div class="art-theme-grid">' + cards + '</div></fieldset>' +
    '<section class="art-companion-section" aria-labelledby="art-companion-title"><div class="art-companion-frame">' +
    '<img data-companion-portrait alt="观星伙伴插画" width="720" height="480" loading="lazy"><div data-companion-hidden hidden><span aria-hidden="true">✦</span><p>留白，也是一种陪伴。</p></div></div>' +
    '<div class="art-companion-controls"><span class="art-overline" data-companion-theme></span><h3 id="art-companion-title">一位观星的同行者</h3>' +
    '<p>只在外观设置里相遇，把工作区留给你的思考。</p><fieldset class="art-companion-field"><legend class="visually-hidden">人物形象</legend>' +
    ['female','male','hidden'].map((id,index) => '<label><input type="radio" name="art-companion" value="' + id + '"><span>' + ['女版','男版','隐藏'][index] + '</span></label>').join('') +
    '</fieldset><p class="field-hint">两套主题会分别记住你的人物选择。</p></div></section>' +
    '<div class="art-motion-row"><div><h3>安静一点</h3><p>保留静态插画，停止星盘动效和图片淡入。也会尊重系统设置。</p></div>' +
    '<label class="art-motion-toggle"><input data-art-motion type="checkbox"><span>减少动态效果</span></label></div>' +
    '<section class="art-moments-section" aria-labelledby="art-moments-title"><div><h3 id="art-moments-title">在日常里，偶遇一幅画。</h3><p>来自校园照片的蓝白切片。只在页面下方停留，滚动到时轻轻出现。</p><fieldset class="art-moment-options"><legend class="visually-hidden">校园图片出现的位置</legend><label><input type="checkbox" data-art-moment="dashboard">首页页尾</label><label><input type="checkbox" data-art-moment="timetable">时间表页尾</label></fieldset></div><img class="art-moment-preview" src="/assets/themes/assets/campus-water.webp" alt="校园湖畔的蓝白网点插画预览" width="720" height="540" loading="lazy" decoding="async"></section>' +
    '<footer class="art-settings-footer"><p>外观偏好保存在当前浏览器。</p><p data-appearance-status role="status" aria-live="polite"></p></footer></section>';
}
export function bindAppearance(host,signal) {
  function draw() {
    const value = getAppearance(), selection = value.companions[value.theme];
    host.querySelectorAll('[name="art-theme"]').forEach(input => {input.checked = input.value === value.theme;});
    host.querySelectorAll('[data-choice-state]').forEach(node => {node.textContent = node.dataset.choiceState === value.theme ? '已启用' : '选择主题';});
    host.querySelectorAll('[name="art-companion"]').forEach(input => {input.checked = input.value === selection;});
    host.querySelector('[data-art-motion]').checked = value.reduceMotion;
    host.querySelectorAll('[data-art-moment]').forEach(input => {input.checked = value.moments[input.dataset.artMoment];});
    host.querySelector('[data-companion-theme]').textContent = themes[value.theme].name;
    const image = host.querySelector('[data-companion-portrait]');
    image.hidden = selection === 'hidden';
    host.querySelector('[data-companion-hidden]').hidden = selection !== 'hidden';
    if (selection !== 'hidden') {
      const src = '/assets/themes/assets/' + value.theme + '-' + selection + '.webp';
      if (image.getAttribute('src') !== src) image.setAttribute('src',src);
      image.alt = themes[value.theme].name + (selection === 'female' ? '女版' : '男版') + '观星伙伴插画';
    }
  }
  host.addEventListener('change',event => {
    const target = event.target;
    let patch;
    if (target.name === 'art-theme') patch = {theme:target.value};
    if (target.name === 'art-companion') patch = {companions:{[state.theme]:target.value}};
    if (target.matches('[data-art-motion]')) patch = {reduceMotion:target.checked};
    if (target.matches('[data-art-moment]')) patch = {moments:{[target.dataset.artMoment]:target.checked}};
    if (!patch) return;
    const saved = setAppearance(patch);
    host.querySelector('[data-appearance-status]').textContent = saved ? '外观已保存。' : '已应用。浏览器限制了保存，下次打开可能需要重新选择。';
  },{signal});
  window.addEventListener('campus:appearance',draw,{signal});
  draw();
}
