import {escape as e} from '../shared.js';

const key = 'campus.appearance.v1';
export let themes = Object.freeze({default:{id:'default',name:'Default · Nord',styles:[],views:{},backgrounds:{}}});
const companion = value => ['female','male','hidden'].includes(value) ? value : 'female';
const campusThemes = ['observatory','star-notes'];
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
function normalizeCampusPreferences(value) {
  value = object(value);
  return {...value,
    moments:{dashboard:value.moments?.dashboard!==false,timetable:value.moments?.timetable!==false},
    rotation:{autoplay:value.rotation?.autoplay!==false,seconds:[10,20,30,60].includes(value.rotation?.seconds)?value.rotation.seconds:20},
  };
}
export function normalizeAppearance(value = {}) {
  const options = {...object(value?.options)};
  // Earlier blue-white themes saved these fields at the root; retain both variants' choices.
  for (const id of campusThemes) {
    const current = object(options[id]);
    options[id] = normalizeCampusPreferences({...current,
      moments:{...object(value?.moments),...object(current.moments)},
      rotation:{...object(value?.rotation),...object(current.rotation)},
    });
  }
  return {
    theme:typeof value?.theme === 'string' && /^[a-z][a-z0-9-]{0,47}$/.test(value.theme) ? value.theme : 'default',
    companions:{observatory:companion(value?.companions?.observatory),'star-notes':companion(value?.companions?.['star-notes'])},
    reduceMotion:value?.reduceMotion === true,
    options,
  };
}
let state;
try {state = normalizeAppearance(JSON.parse(localStorage.getItem(key)));}
catch {state = normalizeAppearance();}
let selected = themes.default, entry = {}, themeStyles = [];
export function getAppearance() {return structuredClone(state);}
export function getCampusPreferences(id = selected.id) {
  return {...structuredClone(normalizeCampusPreferences(state.options[id])),reduceMotion:state.reduceMotion};
}
function apply() {
  document.documentElement.dataset.theme = selected.id;
  if (entry.artTheme) document.documentElement.dataset.artTheme = selected.id;
  else delete document.documentElement.dataset.artTheme;
  document.documentElement.dataset.artMotion = state.reduceMotion ? 'reduced' : 'system';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',entry.themeColor?.(selected.id) || '#2e3440');
  document.querySelectorAll('[data-theme-name]').forEach(node => {node.textContent = selected.name;});
  const logo = document.querySelector('.brand img');
  if (logo) logo.src = entry.icon || '/assets/icon.svg';
}
export function setAppearance(patch) {
  const next = normalizeAppearance({...state,...patch,companions:{...state.companions,...patch.companions}});
  let saved = true;
  try {localStorage.setItem(key,JSON.stringify(next));} catch {saved = false;}
  state = next;
  apply();
  window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
  return saved;
}
export async function initializeThemes(catalog) {
  themes = Object.freeze(Object.fromEntries(catalog.items.map(item => [item.id,Object.freeze(item)])));
  selected = Object.hasOwn(themes,state.theme) ? themes[state.theme] : themes.default;
  if (!selected) throw new Error('Default 主题未安装，请检查主题目录。');
  async function load() {
    themeStyles.forEach(style => style.remove());themeStyles=[];
    await Promise.all(selected.styles.map(url=>new Promise((resolve,reject)=>{
      const link=document.createElement('link'),timer=setTimeout(()=>reject(new Error('主题样式加载超时。')),10000);
      link.rel='stylesheet';link.href=url;themeStyles.push(link);
      link.onload=()=>{clearTimeout(timer);resolve();};link.onerror=()=>{clearTimeout(timer);reject(new Error('主题样式无法加载。'));};document.head.append(link);
    })));
    entry=selected.entry ? await import(selected.entry) : {};
  }
  try {await load();}
  catch(error) {if(selected.id==='default')throw error;selected=themes.default;await load();}
  apply();
  return selected.id !== state.theme ? '已保存的主题暂不可用，当前显示 Default；安装后会继续使用原选择。' : null;
}
export function viewURL(id, background = false) {
  const views = selected[background ? 'backgrounds' : 'views'];
  return Object.hasOwn(views,id) ? views[id] : null;
}
export function themeContext() {
  return Object.freeze({
    id:selected.id,
    list:()=>structuredClone(Object.values(themes)),
    select:id=>{
      if(!Object.hasOwn(themes,id))throw new Error('这个主题尚未安装。');
      if(!setAppearance({theme:id}))throw new Error('浏览器未能保存主题，请允许本站保存数据。');
      location.reload();
    },
    renderSlot:(name,props,fallback='') => entry.renderSlot?.(name,props) ?? fallback,
    preferences:() => Object.hasOwn(state.options,selected.id) ? structuredClone(state.options[selected.id]) : {},
    savePreferences:preferences => setAppearance({options:{...state.options,[selected.id]:preferences}}),
  });
}
window.addEventListener('storage',event => {
  if (event.key !== key && event.key !== null) return;
  let value;
  try {value=normalizeAppearance(event.newValue ? JSON.parse(event.newValue) : null);} catch {value=normalizeAppearance();}
  if (value.theme !== state.theme) {location.reload();return;}
  state=value;apply();window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
});
export function appearancePanel() {
  const cards = Object.entries(themes).map(([id,theme]) => `<label class="art-theme-choice"><input type="radio" name="art-theme" value="${e(id)}"><span class="art-theme-card">${theme.preview ? `<img src="${e(theme.preview)}" alt="" width="720" height="360" loading="lazy">` : '<span class="default-theme-preview" aria-hidden="true"><i></i><span><b></b><b></b><b></b></span></span>'}<span class="art-theme-meta"><strong>${e(theme.name)}</strong><span data-choice-state="${e(id)}"></span></span><span class="art-theme-description">${e(theme.description)}</span></span></label>`).join('');
  return `<section class="panel settings-section appearance-panel" aria-labelledby="appearance-title"><header class="art-settings-heading"><h2 id="appearance-title">主题与外观</h2><p>选择工作台的界面。偏好保存在当前浏览器，重启后继续使用。</p></header>
    <fieldset class="art-theme-field"><legend>界面主题</legend><div class="art-theme-grid">${cards}</div></fieldset>
    <p data-theme-unavailable class="notice" hidden>已保存的主题暂不可用，当前使用 Default。你的原选择仍会保留。</p>
    <section class="art-companion-section" aria-labelledby="art-companion-title"><div class="art-companion-frame"><img data-companion-portrait alt="观星伙伴插画" width="720" height="480" loading="lazy"><div data-companion-hidden hidden><span aria-hidden="true">✦</span><p>留白，也是一种陪伴。</p></div></div><div class="art-companion-controls"><span class="art-overline" data-companion-theme></span><h3 id="art-companion-title">一位观星的同行者</h3><p>只在外观设置里相遇，把工作区留给你的思考。</p><fieldset class="art-companion-field"><legend class="visually-hidden">人物形象</legend>${['female','male','hidden'].map((id,index)=>`<label><input type="radio" name="art-companion" value="${id}"><span>${['女版','男版','隐藏'][index]}</span></label>`).join('')}</fieldset><p class="field-hint">两套主题会分别记住你的人物选择。</p></div></section>
    <div class="art-motion-row"><div><h3>动态效果</h3><p>减少装饰动画，同时尊重系统偏好。</p></div><label class="art-motion-toggle"><input data-art-motion type="checkbox"><span>减少动态效果</span></label></div>
    <section class="art-moments-section" aria-labelledby="art-moments-title" hidden><div><h3 id="art-moments-title">在日常里，偶遇一幅画。</h3><p>只在页面下方显示图片，不添加场景说明。可自动轮播，也可手动切换。</p><div class="art-moment-options"><label><input type="checkbox" data-art-moment="dashboard"><span>首页页尾</span></label><label><input type="checkbox" data-art-moment="timetable"><span>时间表页尾</span></label></div><div class="art-moment-rotation"><label><input type="checkbox" data-art-autoplay><span>自动轮播图片</span></label><label>切换间隔<select data-art-interval>${[10,20,30,60].map(seconds=>`<option value="${seconds}">${seconds} 秒</option>`).join('')}</select></label></div></div><img class="art-moment-preview" src="/assets/themes/assets/campus-water.webp" alt="校园照片蓝白处理预览" width="720" height="480" loading="lazy"></section>
    <footer class="art-settings-footer"><p>主题切换后会重新打开当前页面。</p><p data-appearance-status role="status" aria-live="polite"></p></footer></section>`;
}
export function bindAppearance(host,signal) {
  function draw() {
    const value=getAppearance(), art=Object.hasOwn(value.companions,selected.id), selection=value.companions[selected.id];
    host.querySelectorAll('[name="art-theme"]').forEach(input=>{input.checked=input.value===selected.id;});
    host.querySelectorAll('[data-choice-state]').forEach(node=>{node.textContent=node.dataset.choiceState===selected.id?'已启用':'选择主题';});
    host.querySelector('[data-theme-unavailable]').hidden=selected.id===value.theme;
    host.querySelector('.art-companion-section').hidden=!art;
    host.querySelector('[data-art-motion]').checked=value.reduceMotion;
    host.querySelector('.art-moments-section').hidden=!art;
    if (!art) return;
    const preferences=getCampusPreferences();
    host.querySelectorAll('[data-art-moment]').forEach(input=>{input.checked=preferences.moments[input.dataset.artMoment];});
    host.querySelector('[data-art-autoplay]').checked=preferences.rotation.autoplay;
    host.querySelector('[data-art-interval]').value=String(preferences.rotation.seconds);
    host.querySelectorAll('[name="art-companion"]').forEach(input=>{input.checked=input.value===selection;});
    host.querySelector('[data-companion-theme]').textContent=selected.name;
    const image=host.querySelector('[data-companion-portrait]');image.hidden=selection==='hidden';
    host.querySelector('[data-companion-hidden]').hidden=selection!=='hidden';
    if (selection!=='hidden') {image.src='/assets/themes/assets/'+selected.id+'-'+selection+'.webp';image.alt=selected.name+(selection==='female'?'女版':'男版')+'观星伙伴插画';}
  }
  host.addEventListener('change',event=>{
    const target=event.target;
    const preferences=getCampusPreferences();
    let campusPatch=null;
    if (campusThemes.includes(selected.id)) {
      if (target.matches('[data-art-moment]')) campusPatch={...preferences,moments:{...preferences.moments,[target.dataset.artMoment]:target.checked}};
      else if (target.matches('[data-art-autoplay]')) campusPatch={...preferences,rotation:{...preferences.rotation,autoplay:target.checked}};
      else if (target.matches('[data-art-interval]')) campusPatch={...preferences,rotation:{...preferences.rotation,seconds:Number(target.value)}};
      if(campusPatch) delete campusPatch.reduceMotion;
    }
    const patch=campusPatch?{options:{...state.options,[selected.id]:campusPatch}}:target.name==='art-theme'?{theme:target.value}:target.name==='art-companion'?{companions:{[selected.id]:target.value}}:target.matches('[data-art-motion]')?{reduceMotion:target.checked}:null;
    if (!patch) return;
    const saved=setAppearance(patch);
    host.querySelector('[data-appearance-status]').textContent=saved?'外观已保存。':'浏览器限制了保存，请允许本站保存数据后重试。';
    if (saved && patch.theme && patch.theme!==selected.id) location.reload();
  },{signal});
  window.addEventListener('campus:appearance',draw,{signal});draw();
}
