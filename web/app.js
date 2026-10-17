import {api, setToken, moduleApi, ui, escape, toast, safeAction, empty} from './shared.js';
import * as settings from './settings.js';
import {icon as navIcon} from './icons.js';

const main = document.querySelector('#main');
const menuButton = document.querySelector('#mobile-menu');
const scrim = document.querySelector('#menu-scrim');
document.querySelector('.skip-link').addEventListener('click',event => { event.preventDefault(); main.focus(); });
let state;
let pageScope;
let backgroundScope, backgroundKey = '';
let revision = 0;
const selectedViews = new Map();

let labels = new Map();
const moduleStatuses = {ready:'可用',disabled:'已停用',error:'加载失败'};

function closeMenu() {
  document.body.classList.remove('menu-open');
  document.querySelector('.shell').inert = false;
  menuButton.setAttribute('aria-expanded','false');
  scrim.hidden = true;
}
menuButton.onclick = () => {
  const open = document.body.classList.toggle('menu-open');
  document.querySelector('.shell').inert = open;
  menuButton.setAttribute('aria-expanded',String(open));
  scrim.hidden = !open;
  if (open) document.querySelector('#navigation a')?.focus();
};
scrim.onclick = () => { closeMenu(); menuButton.focus(); };
document.addEventListener('keydown',event => { if (event.key === 'Escape' && document.body.classList.contains('menu-open')) { closeMenu(); menuButton.focus(); } });

function navigate(category) {
  if (!labels.has(category)) throw new Error('这个分类不在工作台导航中。');
  location.hash = category;
}

async function dispose() {
  const previous = pageScope;
  pageScope = null;
  if (!previous) return;
  previous.controller.abort();
  const results = await Promise.allSettled(previous.cleanups.map(cleanup => Promise.resolve().then(cleanup)));
  if (results.some(result => result.status === 'rejected')) toast('一个模块的清理过程发生错误，请检查模块实现。');
  document.querySelector('#dialog').close();
}

function services(signal) {
  const request = (path,options = {}) => api(path,{...options,signal});
  return Object.freeze({
    auth:Object.freeze({
      providers:() => request('/auth/providers'),
      status:id => request('/auth/' + encodeURIComponent(id) + '/status'),
    }),
    ai:Object.freeze({
      settings:() => request('/ai/settings'),
      generate:body => request('/ai/generate',{method:'POST',body}),
      chat:body => request('/ai/chat',{method:'POST',body}),
      plugins:() => request('/ai/plugins'),
      run:body => request('/ai/run',{method:'POST',body}),
    }),
  });
}

async function mountModule(module, container, scope, background = false) {
  const body = document.createElement('div');
  body.className = 'module-mount';
  body.dataset.moduleId = module.id;
  const card = document.createElement('section');
  card.className = 'panel module-card';
  card.innerHTML = '<header class="module-card-heading"><h2>' + escape(module.name) + '</h2><span class="module-status status-' + escape(module.status) + '"' + (module.status === 'ready' ? ' hidden' : '') + '>' + moduleStatuses[module.status] + '</span></header>';
  card.append(body);
  container.append(card);
  if (background) {card.className='background-module';card.querySelector('header').remove();}
  if (module.status === 'error') {
    body.innerHTML = '<div class="module-error" role="alert"><h3>模块需要检查</h3><p>' + escape(module.error || '请查看模块配置和服务入口。') + '</p></div>';
    return;
  }
  body.innerHTML = '<div class="module-loading" role="status"><span class="spinner" aria-hidden="true"></span>正在打开模块…</div>';
  const lifetime = new AbortController();
  const abort = () => lifetime.abort();
  scope.controller.signal.addEventListener('abort',abort,{once:true});
  if (scope.controller.signal.aborted) abort();
  try {
    const url = new URL(background ? module.background_url : module.frontend_url,location.origin);
    const prefix = '/module-assets/' + encodeURIComponent(module.id) + '/';
    if (url.origin !== location.origin || !url.pathname.startsWith(prefix)) throw new Error('模块入口需要位于本机模块资源目录。');
    const entry = await import(url.href);
    if (scope.controller.signal.aborted) return;
    if (typeof entry.mount !== 'function') throw new Error('模块入口需要导出 mount(container, context)。');
    body.replaceChildren();
    const cleanup = await entry.mount(body,{
      api:moduleApi(module.id,lifetime.signal), ui, navigate, module:{...module},
      focus:active => {card.classList.toggle('module-focused',active);container.classList.toggle('module-focus',!!container.querySelector('.module-focused'));},
      signal:lifetime.signal, services:services(lifetime.signal),
    });
    if (cleanup !== undefined && typeof cleanup !== 'function') throw new Error('模块 mount 需要返回清理函数或不返回值。');
    if (scope.controller.signal.aborted) { if (cleanup) await cleanup(); }
    else if (cleanup) scope.cleanups.push(cleanup);
  } catch (error) {
    abort();
    scope.controller.signal.removeEventListener('abort',abort);
    if (scope.controller.signal.aborted) return;
    if (background) {card.remove();toast(module.name + '暂时无法打开：' + error.message);return;}
    body.innerHTML = '<div class="module-error" role="alert"><h3>模块暂时无法打开</h3><p>' + escape(error.message) + '</p></div>';
    card.querySelector('.module-status').textContent = '加载失败';
    card.querySelector('.module-status').hidden = false;
    card.querySelector('.module-status').className = 'module-status status-error';
  }
}

async function stopBackground() {
  const scope=backgroundScope;backgroundScope=null;backgroundKey='';
  if (!scope) return;
  scope.controller.abort();
  for (const cleanup of scope.cleanups) await cleanup();
  scope.root.remove();
}

async function syncBackground() {
  const modules=state.modules.filter(item=>item.enabled&&item.status==='ready'&&item.background_url);
  const key=modules.map(item=>item.background_url).join('|');
  if (key===backgroundKey) return;
  await stopBackground();backgroundKey=key;
  const root=document.createElement('div');document.body.append(root);
  const scope={controller:new AbortController(),cleanups:[],root};backgroundScope=scope;
  await Promise.all(modules.map(module=>mountModule(module,root,scope,true)));
}

async function render() {
  const current = ++revision;
  await dispose();
  if (current !== revision) return;
  await syncBackground();
  if (current !== revision) return;
  const navigation = state.categories.map(item => [item.id,item.icon,item.label]);
  labels = new Map(navigation.map(([id,,label]) => [id,label]));
  const enabled = state.modules.filter(module => module.enabled && module.has_frontend && (module.status === 'error' || module.status === 'ready'));
  const items = navigation.filter(([id]) => id === 'settings' || enabled.some(module => module.category === id));
  const requested = location.hash.slice(1).split('?')[0];
  const page = items.some(([id]) => id === requested) ? requested : items[0][0];
  if (requested !== page) history.replaceState(null,'','#' + page);
  document.querySelector('#navigation').innerHTML = items.map(([id,icon,label],index) => (id === 'settings' && index ? '<span class="nav-divider"></span>' : '') + '<a href="#' + id + '" data-nav="' + id + '"><span class="nav-icon" aria-hidden="true">' + navIcon(icon) + '</span>' + escape(label) + '</a>').join('');
  closeMenu();
  document.querySelector('#page-label').textContent = labels.get(page);
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === page;
    link.classList.toggle('active',active);
    if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  });
  main.innerHTML = '<div class="page-heading"><h1>' + escape(labels.get(page)) + '</h1></div><div id="settings-area"></div><div class="module-zone" id="module-area"></div>';
  const scope = {controller:new AbortController(),cleanups:[]};
  pageScope = scope;
  const zone = main.querySelector('#module-area');
  const visible = enabled.filter(module => module.category === page);
  zone.dataset.count = String(visible.length);
  const layout = state.categories.find(item => item.id === page)?.layout;
  const tabbed = layout === 'tabs' && visible.length > 1;
  let mounted = visible;
  if (layout === 'primary' && visible.length) {mounted=[visible.find(item=>item.id===page)||visible[0]];zone.dataset.count='1';}
  if (tabbed) {
    const selected = visible.find(item => item.id === selectedViews.get(page)) || visible.find(item => item.id === page) || visible[0];
    mounted = [selected];
    zone.dataset.count = '1';
    zone.setAttribute('role','tabpanel');
    zone.setAttribute('aria-labelledby','view-' + selected.id);
    const tabs = document.createElement('div');
    tabs.className = 'settings-tabs module-tabs';
    tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label',labels.get(page));
    tabs.innerHTML = visible.map(item => '<button type="button" id="view-' + item.id + '" role="tab" aria-controls="module-area" data-view="' + item.id + '" aria-selected="' + (item.id === selected.id) + '" tabindex="' + (item.id === selected.id ? '0' : '-1') + '">' + escape(item.name) + '</button>').join('');
    zone.before(tabs);
    tabs.querySelectorAll('button').forEach((button,index) => {
      button.onclick = async () => {selectedViews.set(page,button.dataset.view);await render();main.querySelector('#view-' + button.dataset.view)?.focus();};
      button.onkeydown = event => {const offset = {ArrowLeft:-1,ArrowRight:1}[event.key];if (offset) {event.preventDefault();tabs.children[(index + offset + visible.length) % visible.length].click();}};
    });
  }
  if (layout !== 'primary' && !tabbed && visible.length > 1) {
    const shortcuts = document.createElement('nav');
    shortcuts.className = 'module-shortcuts';
    shortcuts.setAttribute('aria-label','页面分区');
    shortcuts.innerHTML = visible.map(module => '<button type="button" data-module-section="' + escape(module.id) + '">' + escape(module.name) + '</button>').join('');
    shortcuts.addEventListener('click',event => {
      const button = event.target.closest('[data-module-section]');
      if (!button) return;
      const card = [...zone.querySelectorAll('.module-card')].find(card => card.querySelector('[data-module-id]')?.dataset.moduleId === button.dataset.moduleSection);
      const heading = card?.querySelector('.module-mount h2') || card?.querySelector('h2');
      if (!heading) return;
      heading.tabIndex = -1;
      heading.closest('.module-card').scrollIntoView({block:'start'});
      heading.focus({preventScroll:true});
    },{signal:scope.controller.signal});
    main.querySelector('.page-heading').append(shortcuts);
  }
  const work = mounted.map(module => mountModule(module,zone,scope));
  if (page === 'settings') {
    work.push(settings.mount(main.querySelector('#settings-area'),{
      modules:state.modules, labels, signal:scope.controller.signal,
      reload:reloadModules, setEnabled, refresh, beforeClear:async()=>{await dispose();await stopBackground();},
    }));
  } else {
    main.querySelector('#settings-area').remove();
    if (!visible.length) zone.innerHTML = empty('这个分类已准备好接入模块','在设置中启用此分类的模块后，内容会显示在这里。','<a class="button button-secondary" href="#settings">管理模块 →</a>');
  }
  await Promise.all(work);
  if (current === revision) main.focus({preventScroll:true});
}

async function reloadModules() {
  ++revision;
  await dispose();
  await stopBackground();
  main.innerHTML = '<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span>正在刷新模块…</div>';
  try { Object.assign(state,await api('/modules/reload',{method:'POST'})); }
  finally { await render(); }
  toast('模块列表已更新。');
}

async function setEnabled(id, enabled) {
  ++revision;
  await dispose();
  await stopBackground();
  try { Object.assign(state,await api('/modules/' + encodeURIComponent(id),{method:'PUT',body:{enabled}})); }
  finally { await render(); }
  toast(enabled ? '模块已启用。' : '模块已停用。');
}

async function refresh() {
  Object.assign(state,await api('/modules'));
  await render();
}

async function start() {
  state = await api('/bootstrap');
  setToken(state.csrf_token);
  document.querySelector('#workspace-date').textContent = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(new Date());
  await render();
}

window.addEventListener('hashchange',() => { if (state) render().catch(error => { if (error.name !== 'AbortError') toast(error.message); }); });
window.addEventListener('pagehide',() => { void dispose();void stopBackground(); });

try { await start(); }
catch (error) {
  main.innerHTML = empty('暂时无法打开工作台',error.message,'<button class="button button-primary" id="retry-start" type="button">重新连接</button>');
  const retry = main.querySelector('#retry-start');
  retry.onclick = safeAction(retry,start);
}


