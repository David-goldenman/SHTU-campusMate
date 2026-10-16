import {icon} from './icons.js';
import {api, setToken, moduleApi, ui, escape, toast, safeAction, empty} from './shared.js';
import * as settings from './settings.js';

const main = document.querySelector('#main');
const menuButton = document.querySelector('#mobile-menu');
const scrim = document.querySelector('#menu-scrim');
const reloadButton = document.querySelector('#reload-modules');
let state;
let pageScope;
let revision = 0;

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

async function mountModule(module, container, scope) {
  const body = document.createElement('div');
  body.className = 'module-mount';
  body.dataset.moduleId = module.id;
  const card = document.createElement('section');
  card.className = 'panel module-card';
  card.id = 'module-card-' + module.id;
  if (container.dataset.single === 'true') card.classList.add('module-card-single');
  card.innerHTML = '<header class="module-card-heading"><div><h2 tabindex="-1">' + escape(module.name) + '</h2><span class="module-version">v' + escape(module.version) + '</span></div><span class="module-status status-' + escape(module.status) + '">' + moduleStatuses[module.status] + '</span></header>';
  card.append(body);
  container.append(card);
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
    const url = new URL(module.frontend_url,location.origin);
    const prefix = '/module-assets/' + encodeURIComponent(module.id) + '/';
    if (url.origin !== location.origin || !url.pathname.startsWith(prefix)) throw new Error('模块入口需要位于本机模块资源目录。');
    const entry = await import(url.href);
    if (scope.controller.signal.aborted) return;
    if (typeof entry.mount !== 'function') throw new Error('模块入口需要导出 mount(container, context)。');
    body.replaceChildren();
    const cleanup = await entry.mount(body,{
      api:moduleApi(module.id,lifetime.signal), ui, navigate, module:{...module},
      signal:lifetime.signal, services:services(lifetime.signal),
    });
    if (cleanup !== undefined && typeof cleanup !== 'function') throw new Error('模块 mount 需要返回清理函数或不返回值。');
    if (scope.controller.signal.aborted) { if (cleanup) await cleanup(); }
    else if (cleanup) scope.cleanups.push(cleanup);
  } catch (error) {
    abort();
    scope.controller.signal.removeEventListener('abort',abort);
    if (scope.controller.signal.aborted) return;
    body.innerHTML = '<div class="module-error" role="alert"><h3>模块暂时无法打开</h3><p>' + escape(error.message) + '</p></div>';
    card.classList.add('has-error');
    card.querySelector('.module-status').textContent = '加载失败';
    card.querySelector('.module-status').className = 'module-status status-error';
  }
}

async function render() {
  const current = ++revision;
  await dispose();
  if (current !== revision) return;
  const navigation = state.categories.map(item => [item.id,item.icon,item.label]);
  labels = new Map(navigation.map(([id,,label]) => [id,label]));
  const descriptions = new Map(state.categories.map(item => [item.id,item.description]));
  const enabled = state.modules.filter(module => module.enabled && module.has_frontend && (module.status === 'error' || module.status === 'ready'));
  const items = navigation.filter(([id]) => id === 'settings' || enabled.some(module => module.category === id));
  const requested = location.hash.slice(1);
  const page = items.some(([id]) => id === requested) ? requested : items[0][0];
  if (requested !== page) history.replaceState(null,'','#' + page);
  document.querySelector('#navigation').innerHTML = items.map(([id,iconName,label],index) => (id === 'settings' && index ? '<span class="nav-divider"></span>' : '') + '<a href="#' + id + '" data-nav="' + id + '"><span class="nav-icon" aria-hidden="true">' + icon(iconName) + '</span><span class="nav-label">' + escape(label) + '</span>' + '</a>').join('');
  closeMenu();
  document.querySelector('#page-label').textContent = labels.get(page);
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === page;
    link.classList.toggle('active',active);
    if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  });
  main.innerHTML = '<div class="page-heading"><div><p class="eyebrow">CAMPUS WORKSPACE</p><h1 id="page-title">' + escape(labels.get(page)) + '</h1><p class="page-description">' + escape(descriptions.get(page)) + '</p></div><div class="page-heading-note">你的个人学习空间</div></div><div id="settings-area"></div><div class="module-zone" id="module-area"></div>';
  const scope = {controller:new AbortController(),cleanups:[]};
  pageScope = scope;
  const zone = main.querySelector('#module-area');
  const visible = enabled.filter(module => module.category === page);
  zone.dataset.single = String(visible.length === 1 && visible[0].status === 'ready');
  if (visible.length > 1) {
    const shortcuts = document.createElement('nav');
    shortcuts.className = 'module-shortcuts';
    shortcuts.setAttribute('aria-label','页面分区');
    shortcuts.innerHTML = visible.map(module => '<button type="button" data-module-jump="' + escape(module.id) + '">' + escape(module.name) + '</button>').join('');
    zone.before(shortcuts);
    shortcuts.addEventListener('click',event => {
      const button = event.target.closest('[data-module-jump]');
      if (!button) return;
      const card = document.getElementById('module-card-' + button.dataset.moduleJump);
      card.querySelector('h2').focus({preventScroll:true});
      card.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    },{signal:scope.controller.signal});
  }
  const work = visible.map(module => mountModule(module,zone,scope));
  if (page === 'settings') {
    work.push(settings.mount(main.querySelector('#settings-area'),{
      modules:state.modules, labels, signal:scope.controller.signal,
      reload:reloadModules, setEnabled, refresh, beforeClear:dispose,
    }));
  } else {
    main.querySelector('#settings-area').remove();
    if (!visible.length) zone.innerHTML = empty('这个分类已准备好接入模块','在设置中启用此分类的模块后，内容会显示在这里。','<a class="button button-secondary" href="#settings">管理模块 →</a>');
  }
  await Promise.all(work);
  if (current === revision && !scope.controller.signal.aborted) main.focus({preventScroll:true});
}

async function reloadModules() {
  ++revision;
  await dispose();
  main.innerHTML = '<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span>正在刷新模块…</div>';
  try { Object.assign(state,await api('/modules/reload',{method:'POST'})); }
  finally { await render(); }
  toast('模块列表已更新。');
}

async function setEnabled(id, enabled) {
  ++revision;
  await dispose();
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
  document.querySelector('#app-version').textContent = 'v' + state.version;
  const today = new Date();
  document.querySelector('#workspace-date').dateTime = today.toISOString();
  document.querySelector('#workspace-date').textContent = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'short'}).format(today);
  await render();
  reloadButton.disabled = false;
}

document.querySelector('.skip-link').onclick = event => { event.preventDefault(); main.focus(); };

reloadButton.onclick = safeAction(reloadButton,reloadModules);
window.addEventListener('hashchange',() => { if (state) render().catch(error => { if (error.name !== 'AbortError') toast(error.message); }); });
window.addEventListener('pagehide',() => { void dispose(); });

try { await start(); }
catch (error) {
  main.innerHTML = empty('暂时无法打开工作台',error.message,'<button class="button button-primary" id="retry-start" type="button">重新连接</button>');
  const retry = main.querySelector('#retry-start');
  retry.onclick = safeAction(retry,start);
}


