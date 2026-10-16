let token = '';

export function setToken(value) { token = value; }

export function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
}

export async function api(path, options = {}) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('接口路径需要以 / 开头。');
  const url = new URL('/api/v1' + path, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/')) throw new Error('接口路径超出工作台范围。');
  const headers = new Headers(options.headers);
  headers.set('X-Framework-Token', token);
  const request = {...options, headers};
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
    request.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
  }
  const response = await fetch(url, request);
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '请求失败，请检查设置后重试。');
  return value;
}

export function moduleApi(id, signal) {
  const prefix = '/api/v1/modules/' + encodeURIComponent(id);
  return (path = '', options = {}) => {
    if (path.startsWith('//') || (path && !path.startsWith('/') && !path.startsWith('?'))) throw new Error('模块接口需要使用相对路径。');
    const url = new URL(prefix + path, location.origin);
    if (url.pathname !== prefix && !url.pathname.startsWith(prefix + '/')) throw new Error('接口路径超出当前模块范围。');
    return api(url.pathname.slice('/api/v1'.length) + url.search, {...options, signal});
  };
}

export function toast(message) {
  const node = document.querySelector('#toast');
  node.textContent = String(message);
  node.classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove('visible'), 4500);
}

export function dialog(title, content) {
  const node = document.querySelector('#dialog');
  if (node.open) node.close();
  node.returnValue = '';
  const heading = document.createElement('div');
  heading.className = 'dialog-heading';
  heading.innerHTML = '<h2 id="dialog-title"></h2><button class="icon-button" type="button" aria-label="关闭">×</button>';
  heading.querySelector('h2').textContent = title;
  heading.querySelector('button').onclick = () => node.close();
  const body = document.createElement('div');
  body.className = 'dialog-body';
  if (content instanceof Node) body.append(content);
  else body.textContent = String(content ?? '');
  node.replaceChildren(heading, body);
  node.onclick = event => { if (event.target === node) node.close(); };
  node.showModal();
  return node;
}

export function confirmDialog(title, message, confirmLabel = '确认') {
  const body = document.createElement('div');
  const description = document.createElement('p');
  description.textContent = message;
  const form = document.createElement('form');
  form.method = 'dialog';
  form.className = 'dialog-actions';
  form.innerHTML = '<button class="button button-secondary" value="cancel">取消</button><button class="button button-danger" value="confirm"></button>';
  form.lastElementChild.textContent = confirmLabel;
  body.append(description, form);
  const node = dialog(title, body);
  return new Promise(resolve => node.addEventListener('close', () => resolve(node.returnValue === 'confirm'), {once:true}));
}

export function safeAction(control, action) {
  return async event => {
    event?.preventDefault();
    if (control.disabled) return;
    control.disabled = true;
    try { await action(); }
    catch (error) { if (error.name !== 'AbortError') toast(error.message); }
    finally { control.disabled = false; }
  };
}

export function empty(title, description, action = '') {
  return '<div class="empty-state"><span class="empty-symbol" aria-hidden="true">▦</span><h2>' + escape(title) + '</h2><p>' + escape(description) + '</p>' + action + '</div>';
}

export function useStyle(url, signal) {
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = url;
  const cleanup = () => { style.remove(); signal.removeEventListener('abort',cleanup); };
  if (!signal.aborted) {
    signal.addEventListener('abort',cleanup,{once:true});
    document.head.append(style);
  }
  return cleanup;
}

export const ui = Object.freeze({escape, toast, dialog, confirmDialog, safeAction, empty, useStyle});

