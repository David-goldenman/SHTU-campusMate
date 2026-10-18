import {escape as e} from '../shared.js';

const key = 'campus.appearance.v1';
export let themes = Object.freeze({default:{id:'default',name:'Default · Nord',styles:[],views:{},backgrounds:{}}});
const companion = value => ['female','male','hidden'].includes(value) ? value : 'female';
const campusThemes = ['observatory','star-notes'];
const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
function normalizeCampusPreferences(value) {
  value = object(value);
  return {...value,
    moments:{...object(value.moments),dashboard:value.moments?.dashboard!==false,timetable:value.moments?.timetable!==false},
    rotation:{...object(value.rotation),autoplay:value.rotation?.autoplay!==false,seconds:[10,20,30,60].includes(value.rotation?.seconds)?value.rotation.seconds:20},
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
    companions:{...object(value?.companions),observatory:companion(value?.companions?.observatory),'star-notes':companion(value?.companions?.['star-notes'])},
    reduceMotion:value?.reduceMotion === true,
    options,
  };
}
let state, legacy;
try {
  const saved=JSON.parse(localStorage.getItem(key));
  if (typeof saved?.theme==='string' && /^[a-z][a-z0-9-]{0,47}$/.test(saved.theme)) legacy=normalizeAppearance(saved);
  state=normalizeAppearance(saved);
} catch {state=normalizeAppearance();}
let persistence, record={revision:0,value:null,resetRevision:0}, baseline=state, writes=Promise.resolve(), lastSaveError='', resetReload=false;
const queued=[];
function merge(current, patch) {
  const next={...object(current)};
  for(const [name,value] of Object.entries(object(patch))) {
    const merged=value && typeof value==='object' && !Array.isArray(value) ? merge(next[name],value) : structuredClone(value);
    Object.defineProperty(next,name,{value:merged,enumerable:true,writable:true,configurable:true});
  }
  return next;
}
function changes(current, value) {
  const result={};
  for(const [name,next] of Object.entries(object(value))) {
    const previous=object(current)[name];
    if(next && typeof next==='object' && !Array.isArray(next)) {
      const changed=changes(previous,next);
      if(Object.keys(changed).length)Object.defineProperty(result,name,{value:changed,enumerable:true});
    } else if(JSON.stringify(previous)!==JSON.stringify(next)) Object.defineProperty(result,name,{value:structuredClone(next),enumerable:true});
  }
  return result;
}
function cache(value) {
  try {localStorage.setItem(key,JSON.stringify(value));return true;} catch {return false;}
}
function validRecord(value) {
  const resetRevision=value?.resetRevision ?? 0;
  if(!value || !Number.isSafeInteger(value.revision) || value.revision<0 || !Number.isSafeInteger(resetRevision) || resetRevision<0 || resetRevision>value.revision || value.value!==null && (!value.value || typeof value.value!=='object' || Array.isArray(value.value))) throw new Error('本机外观设置返回无效，请重新连接工作台。');
  return {...structuredClone(value),resetRevision};
}
function adopt(value) {
  const next=validRecord(value);
  if(next.revision<record.revision || next.resetRevision<record.resetRevision)return;
  if(next.resetRevision>record.resetRevision)for(const item of queued)if(item.resetRevision<next.resetRevision) {item.cancelled=true;resetReload=true;}
  record=next;
  if(record.value!==null) {baseline=normalizeAppearance(record.value);legacy=undefined;}
}
function drawState() {
  state=normalizeAppearance(queued.filter(item=>!item.cancelled).reduce((value,item)=>merge(value,item.patch),baseline));
  apply();window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
}
function reloadAfterReset() {
  if(!resetReload)return;
  const pending=writes;
  void pending.then(()=>{
    if(!resetReload)return;
    if(pending!==writes || queued.length) {reloadAfterReset();return;}
    resetReload=false;if(selected.id!==state.theme)location.reload();
  });
}
async function savePatch(item) {
  let saved=false;
  try {
    for(let attempt=0;attempt<3;attempt++) {
      if(item.cancelled) {lastSaveError='本机外观已重置，清除前的修改未重新保存。';break;}
      try {
        adopt(await persistence.save({revision:record.revision,patch:item.patch}));
        if(item.cancelled) {lastSaveError='本机外观已重置，清除前的修改未重新保存。';break;}
        saved=true;lastSaveError='';break;
      } catch(error) {
        if(error.status!==409 || attempt===2)throw error;
        adopt(await persistence.read());
      }
    }
  } catch(error) {lastSaveError=error.message || '本机外观暂未保存，请检查连接后重试。';}
  finally {
    const index=queued.indexOf(item);if(index>=0)queued.splice(index,1);cache(baseline);drawState();reloadAfterReset();
  }
  return saved;
}
async function hydrate(bridge) {
  persistence=bridge;adopt(bridge.record);
  if(record.value!==null) {state=baseline;cache(state);return null;}
  if(!legacy)return null;
  try {adopt(await persistence.save({revision:record.revision,patch:legacy}));}
  catch(error) {
    if(error.status===409)adopt(await persistence.read());
    else return '旧版外观暂未同步到本机，请在外观设置中重试保存。';
  }
  state=baseline;cache(state);return null;
}
let selected = themes.default, entry = {}, themeStyles = [];
export function getAppearance() {return structuredClone(state);}
export function getCampusPreferences(id = selected.id) {
  return {...structuredClone(normalizeCampusPreferences(state.options[id])),reduceMotion:state.reduceMotion};
}
function apply() {
  document.documentElement.dataset.theme = selected.id;
  document.documentElement.dataset.openingLines = entry.openingLines === true ? 'enabled' : 'hidden';
  if (entry.artTheme) document.documentElement.dataset.artTheme = selected.id;
  else delete document.documentElement.dataset.artTheme;
  document.documentElement.dataset.artMotion = state.reduceMotion ? 'reduced' : 'system';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',entry.themeColor?.(selected.id) || '#2e3440');
  document.querySelectorAll('[data-theme-name]').forEach(node => {node.textContent = selected.name;});
  const logo = document.querySelector('.brand img');
  if (logo) logo.src = entry.icon || '/assets/icon.svg';
}
export function setAppearance(patch) {
  const supplied=Object.fromEntries(Object.entries(object(patch)).filter(([name,value])=>['theme','companions','reduceMotion','options'].includes(name) && value!==undefined));
  if(persistence) {
    const item={patch:structuredClone(supplied),resetRevision:record.resetRevision,cancelled:false};queued.push(item);drawState();
    const result=writes.then(()=>savePatch(item));writes=result.then(()=>undefined,()=>undefined);
    return result;
  }
  baseline=normalizeAppearance(merge(state,supplied));state=baseline;
  const saved=cache(state);apply();window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));return saved;
}
export async function initializeThemes(catalog,bridge) {
  const persistenceMessage=bridge ? await hydrate(bridge) : null;
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
  return selected.id !== state.theme ? '已保存的主题暂不可用，当前显示 Default；安装后会继续使用原选择。' : persistenceMessage;
}
export function viewURL(id, background = false) {
  const views = selected[background ? 'backgrounds' : 'views'];
  return Object.hasOwn(views,id) ? views[id] : null;
}
export function themeContext() {
  return Object.freeze({
    id:selected.id,
    list:()=>structuredClone(Object.values(themes)),
    select:async id=>{
      if(!Object.hasOwn(themes,id))throw new Error('这个主题尚未安装。');
      if(!await setAppearance({theme:id}))throw new Error(lastSaveError || '外观未保存，请检查工作台连接或浏览器设置。');
      await writes;location.reload();
    },
    renderSlot:(name,props,fallback='') => entry.renderSlot?.(name,props) ?? fallback,
    preferences:() => Object.hasOwn(state.options,selected.id) ? structuredClone(state.options[selected.id]) : {},
    savePreferences:preferences => setAppearance({options:{[selected.id]:changes(state.options[selected.id],preferences)}}),
  });
}
window.addEventListener('storage',event => {
  if (event.key !== key && event.key !== null) return;
  if(persistence) {
    void writes.then(async()=>{
      const value=validRecord(await persistence.read());if(value.revision<=record.revision)return;
      const previous=state.theme;adopt(value);cache(baseline);drawState();if(previous!==state.theme)location.reload();
    }).catch(()=>{});
    return;
  }
  let value;
  try {value=normalizeAppearance(event.newValue ? JSON.parse(event.newValue) : null);} catch {value=normalizeAppearance();}
  if (value.theme !== state.theme) {location.reload();return;}
  state=value;baseline=value;apply();window.dispatchEvent(new CustomEvent('campus:appearance',{detail:getAppearance()}));
});
export function appearancePanel() {
  const cards = Object.entries(themes).map(([id,theme]) => `<label class="art-theme-choice"><input type="radio" name="art-theme" value="${e(id)}"><span class="art-theme-card">${theme.preview ? `<img src="${e(theme.preview)}" alt="" width="720" height="360" loading="lazy">` : '<span class="default-theme-preview" aria-hidden="true"><i></i><span><b></b><b></b><b></b></span></span>'}<span class="art-theme-meta"><strong>${e(theme.name)}</strong><span data-choice-state="${e(id)}"></span></span><span class="art-theme-description">${e(theme.description)}</span></span></label>`).join('');
  return `<section class="panel settings-section appearance-panel" aria-labelledby="appearance-title"><header class="art-settings-heading"><h2 id="appearance-title">主题与外观</h2><p>选择工作台的界面。${persistence?'偏好保存在本机工作台，更换浏览器或重启后继续使用。':'偏好保存在当前浏览器，重启后继续使用。'}</p></header>
    <fieldset class="art-theme-field"><legend>界面主题</legend><div class="art-theme-grid">${cards}</div></fieldset>
    <p data-theme-unavailable class="notice" hidden>已保存的主题暂不可用，当前使用 Default。你的原选择仍会保留。</p>
    <section class="art-companion-section" aria-labelledby="art-companion-title"><div class="art-companion-frame"><img data-companion-portrait alt="观星伙伴插画" width="720" height="480" loading="lazy"><div data-companion-hidden hidden><span aria-hidden="true">✦</span><p>留白，也是一种陪伴。</p></div></div><div class="art-companion-controls"><span class="art-overline" data-companion-theme></span><h3 id="art-companion-title">一位观星的同行者</h3><p>只在外观设置里相遇，把工作区留给你的思考。</p><fieldset class="art-companion-field"><legend class="visually-hidden">人物形象</legend>${['female','male','hidden'].map((id,index)=>`<label><input type="radio" name="art-companion" value="${id}"><span>${['女版','男版','隐藏'][index]}</span></label>`).join('')}</fieldset><p class="field-hint">两套主题会分别记住你的人物选择。</p></div></section>
    <div class="art-motion-row"><div><h3>动态效果</h3><p>减少装饰动画，同时尊重系统偏好。</p></div><label class="art-motion-toggle"><input data-art-motion type="checkbox"><span>减少动态效果</span></label></div>
    <section class="art-moments-section" aria-labelledby="art-moments-title" hidden><div><h3 id="art-moments-title">在日常里，偶遇一幅画。</h3><p>只在页面下方显示图片，不添加场景说明。可自动轮播，也可手动切换。</p><div class="art-moment-options"><label><input type="checkbox" data-art-moment="dashboard"><span>首页页尾</span></label><label><input type="checkbox" data-art-moment="timetable"><span>时间表页尾</span></label></div><div class="art-moment-rotation"><label><input type="checkbox" data-art-autoplay><span>自动轮播图片</span></label><label>切换间隔<select data-art-interval>${[10,20,30,60].map(seconds=>`<option value="${seconds}">${seconds} 秒</option>`).join('')}</select></label></div></div><img class="art-moment-preview" src="/assets/themes/assets/campus-water.webp" alt="校园照片蓝白处理预览" width="720" height="480" loading="lazy"></section>
    <footer class="art-settings-footer"><p>主题切换后会重新打开当前页面。</p><p data-appearance-status role="status" aria-live="polite"></p></footer></section>`;
}
export function bindAppearance(host,signal) {
  function draw() {
    const value=getAppearance(), art=campusThemes.includes(selected.id), selection=value.companions[selected.id];
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
  host.addEventListener('change',async event=>{
    const target=event.target;
    let campusPatch=null;
    if (campusThemes.includes(selected.id)) {
      if (target.matches('[data-art-moment]')) campusPatch={moments:{[target.dataset.artMoment]:target.checked}};
      else if (target.matches('[data-art-autoplay]')) campusPatch={rotation:{autoplay:target.checked}};
      else if (target.matches('[data-art-interval]')) campusPatch={rotation:{seconds:Number(target.value)}};
    }
    const patch=campusPatch?{options:{[selected.id]:campusPatch}}:target.name==='art-theme'?{theme:target.value}:target.name==='art-companion'?{companions:{[selected.id]:target.value}}:target.matches('[data-art-motion]')?{reduceMotion:target.checked}:null;
    if (!patch) return;
    const status=host.querySelector('[data-appearance-status]');status.textContent=persistence?'正在保存到本机…':'正在保存到浏览器…';
    const saved=await setAppearance(patch);if(persistence)await writes;if(signal.aborted)return;
    status.textContent=saved?(persistence?'外观已保存到本机。':'外观已保存到浏览器。'):lastSaveError || '外观未保存，请检查工作台连接或浏览器设置。';
    if (saved && state.theme!==selected.id && Object.hasOwn(themes,state.theme)) location.reload();
  },{signal});
  window.addEventListener('campus:appearance',draw,{signal});draw();
}
