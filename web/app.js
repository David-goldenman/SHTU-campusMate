import {api, setToken, moduleApi, ui, escape, toast, safeAction, empty} from './shared.js';
import * as settings from './settings.js';

const navigation = [
  ['dashboard','◫','总览'], ['mail','✉','邮箱'], ['timetable','▦','课程表'],
  ['courses','▥','课程中心'], ['assignments','◷','作业管理'],
  ['notifications','☷','通知'], ['assistant','✧','AI助手'], ['settings','⚙','设置'],
];
const main = document.querySelector('#main');
const menuButton = document.querySelector('#mobile-menu');
const scrim = document.querySelector('#menu-scrim');
const reloadButton = document.querySelector('#reload-modules');
let state;
let pageScope;
let revision = 0;

const labels = new Map(navigation.map(([id,,label]) => [id,label]));
const moduleStatuses = {ready:'可用',disabled:'已停用',error:'加载失败'};
const categoryDescriptions = {
  dashboard:'总览模块的内容会显示在这里。', mail:'邮箱模块的内容会显示在这里。',
  timetable:'课程表模块的内容会显示在这里。', courses:'课程中心模块的内容会显示在这里。',
  assignments:'作业管理模块的内容会显示在这里。', notifications:'通知模块的内容会显示在这里。',
  assistant:'AI助手模块的内容会显示在这里。', settings:'管理模块、账号、AI服务和本地数据。',
};

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
    }),
  });
}

async function mountModule(module, container, scope) {
  const body = document.createElement('div');
  body.className = 'module-mount';
  body.dataset.moduleId = module.id;
  const card = document.createElement('section');
  card.className = 'panel module-card';
  card.innerHTML = '<header class="module-card-heading"><div><h2>' + escape(module.name) + '</h2><span class="module-version">v' + escape(module.version) + '</span></div><span class="module-status status-' + escape(module.status) + '">' + moduleStatuses[module.status] + '</span></header>';
  card.append(body);
  container.append(card);
  if (module.status === 'error') {
    body.innerHTML = '<div class="module-error" role="alert"><h3>模块需要检查</h3><p>' + escape(module.error || '请查看模块配置和服务入口。') + '</p></div>';
    return;
  }
  body.innerHTML = '<div class="module-loading" role="status"><span class="spinner" aria-hidden="true"></span>正在打开模块…</div>';
  try {
    const url = new URL(module.frontend_url,location.origin);
    const prefix = '/module-assets/' + encodeURIComponent(module.id) + '/';
    if (url.origin !== location.origin || !url.pathname.startsWith(prefix)) throw new Error('模块入口需要位于本机模块资源目录。');
    const entry = await import(url.href);
    if (scope.controller.signal.aborted) return;
    if (typeof entry.mount !== 'function') throw new Error('模块入口需要导出 mount(container, context)。');
    body.replaceChildren();
    const cleanup = await entry.mount(body,{
      api:moduleApi(module.id,scope.controller.signal), ui, navigate, module:{...module},
      signal:scope.controller.signal, services:services(scope.controller.signal),
    });
    if (cleanup !== undefined && typeof cleanup !== 'function') throw new Error('模块 mount 需要返回清理函数或不返回值。');
    if (scope.controller.signal.aborted) { if (cleanup) await cleanup(); }
    else if (cleanup) scope.cleanups.push(cleanup);
  } catch (error) {
    if (scope.controller.signal.aborted) return;
    body.innerHTML = '<div class="module-error" role="alert"><h3>模块暂时无法打开</h3><p>' + escape(error.message) + '</p></div>';
    card.querySelector('.module-status').textContent = '加载失败';
    card.querySelector('.module-status').className = 'module-status status-error';
  }
}

async function render() {
  const current = ++revision;
  await dispose();
  if (current !== revision) return;
  const requested = location.hash.slice(1);
  const page = labels.has(requested) ? requested : 'dashboard';
  closeMenu();
  document.querySelector('#page-label').textContent = labels.get(page);
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === page;
    link.classList.toggle('active',active);
    if (active) link.setAttribute('aria-current','page'); else link.removeAttribute('aria-current');
  });
  main.innerHTML = '<div class="page-heading"><div><p class="eyebrow">LOCAL WORKSPACE</p><h1>' + labels.get(page) + '</h1><p class="page-description">' + categoryDescriptions[page] + '</p></div></div><div id="settings-area"></div><div class="module-zone" id="module-area"></div>';
  const scope = {controller:new AbortController(),cleanups:[]};
  pageScope = scope;
  const zone = main.querySelector('#module-area');
  const visible = state.modules.filter(module => module.category === page && module.enabled && (module.status === 'error' || (module.status === 'ready' && module.frontend_url)));
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
}

async function reloadModules() {
  ++revision;
  await dispose();
  main.innerHTML = '<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span>正在刷新模块…</div>';
  try { state.modules = (await api('/modules/reload',{method:'POST'})).modules; }
  finally { await render(); }
  toast('模块列表已更新。');
}

async function setEnabled(id, enabled) {
  ++revision;
  await dispose();
  try { state.modules = (await api('/modules/' + encodeURIComponent(id),{method:'PUT',body:{enabled}})).modules; }
  finally { await render(); }
  toast(enabled ? '模块已启用。' : '模块已停用。');
}

async function refresh() {
  state.modules = (await api('/modules')).modules;
  await render();
}

async function start() {
  state = await api('/bootstrap');
  setToken(state.csrf_token);
  document.querySelector('#app-version').textContent = 'v' + state.version;
  document.querySelector('#navigation').innerHTML = navigation.map(([id,icon,label],index) => (index === 7 ? '<span class="nav-divider"></span>' : '') + '<a href="#' + id + '" data-nav="' + id + '"><span class="nav-icon" aria-hidden="true">' + icon + '</span>' + label + '</a>').join('');
  await render();
  reloadButton.disabled = false;
}

reloadButton.onclick = safeAction(reloadButton,reloadModules);
window.addEventListener('hashchange',() => { if (state) render().catch(error => { if (error.name !== 'AbortError') toast(error.message); }); });
window.addEventListener('pagehide',() => { void dispose(); });

try { await start(); }
catch (error) {
  main.innerHTML = empty('暂时无法打开工作台',error.message,'<button class="button button-primary" id="retry-start" type="button">重新连接</button>');
  const retry = main.querySelector('#retry-start');
  retry.onclick = safeAction(retry,start);
}


