let token = '';

export function setToken(value) { token = value; }

export function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
}

export async function api(path, {onEvent, timeoutMs, idleTimeoutMs = 240000, ...options} = {}) {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('接口路径需要以 / 开头。');
  const url = new URL('/api/v1' + path, location.origin);
  if (url.origin !== location.origin || !url.pathname.startsWith('/api/v1/')) throw new Error('接口路径超出工作台范围。');
  const headers = new Headers(options.headers);
  headers.set('X-Framework-Token', token);
  const deadline = new AbortController();
  const reading = !options.method || ['GET','HEAD'].includes(options.method.toUpperCase());
  const request = {...options, headers, signal:options.signal ? AbortSignal.any([options.signal,deadline.signal]) : deadline.signal};
  const expired = () => deadline.abort(new DOMException('请求等待超时，请先检查结果再重试。','TimeoutError'));
  const timer = setTimeout(expired,timeoutMs ?? (onEvent ? 600000 : reading ? 30000 : 120000));
  let idle;
  const progress = () => {clearTimeout(idle);if(onEvent)idle=setTimeout(expired,idleTimeoutMs);};
  try {
    if (options.body !== undefined) {
      headers.set('Content-Type', 'application/json');
      request.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
    }
    progress();
    let response;
    try {response=await fetch(url, request);}
    catch(error) {if(error.name==='TypeError'&&!request.signal.aborted)throw new Error('无法连接本地服务，请检查服务是否仍在运行。');throw error;}
    if (response.ok && onEvent) {
      if (!response.headers.get('Content-Type')?.startsWith('application/x-ndjson')) throw new Error('回复格式不正确，请重试。');
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let buffer = '';
      try {
        while (true) {
          const {value, done} = await reader.read();
          buffer += decoder.decode(value,{stream:!done});
          const lines = buffer.split('\n');
          buffer = lines.pop();
          for (const line of lines) if (line.trim()) {
            let event;
            try {event=JSON.parse(line);} catch {throw new Error('回复数据不完整，请重试。');}
            progress();onEvent(event);
          }
          if (done) break;
        }
        if (buffer.trim()) {
          let event;
          try {event=JSON.parse(buffer);} catch {throw new Error('回复数据不完整，请重试。');}
          onEvent(event);
        }
      } finally { void reader.cancel().catch(()=>{}); reader.releaseLock(); }
      return;
    }
    if(response.status===204)return null;
    let value;
    try {value=await response.json();}
    catch(error) {
      if(request.signal.aborted)throw error;
      throw new Error(response.ok ? '服务返回了无法读取的数据，请重试。' : '服务请求失败（'+response.status+'），请稍后重试。');
    }
    if (!response.ok) {
      const detail = typeof value?.detail === 'string' ? value.detail : Array.isArray(value?.detail) ? value.detail.map(item => (item.loc || []).filter(key => key !== 'body').join('.') + '：' + item.msg).join('；') : typeof value?.detail?.message === 'string' ? value.detail.message : '请求失败。';
      const message = [detail,value?.action,value?.request_id ? '错误编号：' + value.request_id : ''].filter(Boolean).join(' ');
      const error = new Error(message);
      Object.assign(error,{status:response.status,code:value?.code,requestId:value?.request_id,action:value?.action,details:value?.detail});
      throw error;
    }
    return value;
  } catch(error) {
    if(deadline.signal.aborted)throw deadline.signal.reason;
    throw error;
  } finally {clearTimeout(timer);clearTimeout(idle);}
}

export function moduleApi(id, signal) {
  const prefix = '/api/v1/modules/' + encodeURIComponent(id);
  return (path = '', options = {}) => {
    if (path.startsWith('//') || (path && !path.startsWith('/') && !path.startsWith('?'))) throw new Error('模块接口需要使用相对路径。');
    const url = new URL(prefix + path, location.origin);
    if (url.pathname !== prefix && !url.pathname.startsWith(prefix + '/')) throw new Error('接口路径超出当前模块范围。');
    return api(url.pathname.slice('/api/v1'.length) + url.search, {...options, signal:options.signal ? AbortSignal.any([signal,options.signal]) : signal});
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

export function bindMenus(container, signal) {
  const selector = 'details[data-action-menu]';
  document.addEventListener('pointerdown',event => {
    for (const menu of container.querySelectorAll(selector + '[open]')) {
      if (!menu.contains(event.target)) menu.open = false;
    }
  }, {signal});
  container.addEventListener('click',event => {
    const menu = event.target.closest(selector);
    if (menu && !event.target.closest('summary') && event.target.closest('a,button')) menu.open = false;
  }, {signal});
  container.addEventListener('keydown',event => {
    if (event.key !== 'Escape') return;
    const menu = event.target.closest(selector + '[open]');
    if (!menu) return;
    event.preventDefault();event.stopPropagation();menu.open = false;
    menu.querySelector('summary').focus();
  }, {signal});
}

export const ui = Object.freeze({escape, toast, dialog, confirmDialog, safeAction, empty, useStyle, bindMenus});

