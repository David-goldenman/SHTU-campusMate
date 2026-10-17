import {api, escape, toast, safeAction, confirmDialog, empty} from './shared.js';
import {networkPanel, bindNetwork} from './network.js';
import {appearancePanel, bindAppearance} from './themes/appearance.js';

const authStatuses = {not_connected:'待连接',ready:'已连接',verification_required:'等待验证',login_required:'需要登录'};
const targetNames = {blackboard:'Blackboard',elrc:'虚拟教学社区',ecourse:'E 云课堂',timetable:'教务系统'};
const moduleStatuses = {ready:'已加载',disabled:'已停用',error:'异常',stopping:'正在停止'};
let selectedTab = 'accounts';

function recoveryHint(provider) {
  return provider.automatic_recovery ? '同步前检查登录，过期后自动尝试恢复一次。' : provider.id === 'ids' ? '绑定本机设备或保存密码后，可在过期时自动恢复登录。' : provider.id === 'coremail' ? '邮箱会话失效时，请重新打开官方登录窗口。' : '仅连接会话时，过期需重新登录；保存密码后可自动尝试恢复。';
}

function deviceCard(provider) {
  return `<section class="auth-device"><h4>本机免密码登录</h4><p class="field-hint">为课表、Blackboard 和虚拟教学社区自动恢复登录。设备私钥加密保存在本机。</p>${provider.device.configured ? `<p>${provider.device.enabled ? '已绑定 · 过期后自动续期' : '已绑定其他账号 · 当前账号不使用此凭据'}</p><button class="text-button danger-text" data-device-action="forget" type="button">删除本机凭据</button>` : provider.device.pending ? '<p>上次绑定结果待确认，凭据已加密保留。</p><button class="button button-secondary" data-device-action="recover" type="button">检查上次绑定结果</button><button class="text-button danger-text" data-device-action="forget" type="button">清除待确认凭据</button>' : `<button class="button button-secondary" data-device-action="start" type="button" ${provider.device.setup?.status === 'waiting' ? 'disabled' : ''}>连接并绑定本机</button><p class="field-hint">在学校窗口完成身份复核后自动绑定应用设备，无需创建 Windows 凭据。</p>`}<p class="field-hint" data-device-progress role="status">${escape(provider.device.setup?.message || '')}</p></section>`;
}

function providerCard(provider) {
  const id = escape(provider.id);
  const target = provider.targets?.length ? '<label>登录服务<select data-auth-target>' + provider.targets.map(id => '<option value="' + escape(id) + '" ' + (provider.target === id ? 'selected' : '') + '>' + escape(targetNames[id] || id) + '</option>').join('') + '</select></label>' : '';
  const credentials = provider.id === 'coremail' ? '' : `<details class="auth-alternative"><summary>账号密码登录</summary><form class="credential-form" data-credentials="${id}"><p class="field-hint">提交后加密保存账号密码，并立即登录。需要验证码时，请使用官方窗口继续验证。</p><label for="auth-${id}-username">账号</label><input id="auth-${id}-username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="320" value="${escape(provider.username)}" required><label for="auth-${id}-password">密码</label><div class="password-field"><input id="auth-${id}-password" name="password" type="password" autocomplete="current-password" maxlength="4096" aria-describedby="auth-${id}-password-hint"><button class="text-button" data-show-password type="button" aria-label="显示密码" aria-pressed="false">显示</button></div><p class="field-hint" id="auth-${id}-password-hint" data-password-hint></p><button class="button button-primary" type="submit">登录</button></form></details>`;
  return `<article class="provider-card" data-provider="${id}"><header><h3>${escape(provider.name)}</h3><span class="status-badge auth-${escape(provider.status)}">${authStatuses[provider.status]}</span></header><p class="provider-message" data-auth-feedback role="status">${escape(provider.message || '')}</p><fieldset class="provider-controls" aria-label="${escape(provider.name)}登录操作">${target}<p class="field-hint" data-recovery-hint>${recoveryHint(provider)}</p><details class="auth-alternative" data-browser-options><summary>使用官方窗口连接</summary><div class="provider-actions"><button class="button button-secondary" data-auth-action="browser" type="button">1. 打开官方登录窗口</button><button class="button button-secondary" data-auth-action="import-session" type="button">2. 登录完成，连接账号</button></div><p class="field-hint">在本机 Edge 中登录后连接，后续复用此服务的浏览器资料。</p></details><button class="button button-secondary" data-auth-action="refresh" type="button">检查连接</button>${credentials}${provider.id === 'ids' ? deviceCard(provider) : ''}<div class="provider-footer"><span data-auth-summary></span><button class="text-button danger-text" data-forget-auth type="button">删除账号</button></div></fieldset></article>`;
}

const localTime = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '暂无';

function runtimeInfo(runtime) {
  if (!runtime) return '';
  const last = runtime.last_request, error = runtime.last_error;
  const workers = {running:'运行中',stopped:'已退出',idle:'已结束',cancelled:'已取消',error:'失败'};
  return `<div class="module-runtime"><p>进行中请求 ${runtime.active_requests} · 等待调用 ${runtime.pending_calls}</p><p>最近接口成功：${escape(localTime(runtime.last_success_at))}${last ? ' · 最近请求 ' + last.status + ' / ' + last.duration_ms + ' ms' : ''}</p>${runtime.workers.map(worker => `<p class="${['stopped','error'].includes(worker.status) ? 'danger-text' : ''}">${worker.kind === 'thread' ? '后台线程' : '后台任务'} · ${escape(worker.name)}：${escape(workers[worker.status])}</p>`).join('')}${error ? `<p class="danger-text">最近失败：${escape(localTime(error.at))} · HTTP ${error.status}${error.request_id ? ' · 错误编号 ' + escape(error.request_id) : ''}</p>` : ''}</div>`;
}

function moduleManager(modules, labels) {
  return '<section class="panel settings-section" id="module-manager"><div class="section-heading"><div><h2>模块管理</h2><p>状态读取于 ' + escape(localTime(new Date().toISOString())) + '。同步结果请在对应页面查看。</p></div><div class="form-actions"><button class="button button-secondary" id="settings-status" type="button">读取运行状态</button><button class="button button-secondary" id="settings-reload" type="button">重新加载模块</button></div></div>' + (modules.length ? '<div class="module-list">' + modules.map(module => '<article class="module-row"><div class="module-info"><div><h3>' + escape(module.name) + '</h3><span class="module-version">v' + escape(module.version) + '</span><span class="module-status status-' + escape(module.status) + '">' + moduleStatuses[module.status] + '</span></div><p><a href="#' + escape(module.category) + '">' + escape(labels.get(module.category) || '') + '</a><span>' + escape(module.id) + '</span>' + (module.harness ? '<span>AI 插件</span>' : !module.frontend_url && module.status === 'ready' ? '<span>后台模块</span>' : '') + '</p>' + (module.error ? '<p class="danger-text">' + escape(module.error) + '</p>' : '') + runtimeInfo(module.runtime) + '</div><label class="module-toggle"><input type="checkbox" data-module-toggle="' + escape(module.id) + '" aria-label="' + escape(module.name) + '启用状态" ' + (module.enabled ? 'checked' : '') + '><span>启用</span></label></article>').join('') + '</div>' : empty('模块目录已准备就绪','添加模块后，刷新列表即可在这里启用和管理。')) + '</section>';
}

export async function mount(container, context) {
  const request = (path, options = {}) => api(path,{...options,signal:context.signal});
  let settings, auth, ai;
  try { [settings,auth,ai] = await Promise.all([request('/settings'),request('/auth/providers'),request('/ai/settings')]); }
  catch (error) {
    if (context.signal.aborted) return;
    container.innerHTML = '<section class="panel"><div class="state-error" role="alert"><h2>设置暂时无法读取</h2><p>' + escape(error.message) + '</p><button class="button button-secondary" id="retry-settings" type="button">重新读取</button></div></section>';
    const retry = container.querySelector('#retry-settings');
    retry.onclick = safeAction(retry,context.refresh);
    return;
  }
  if (context.signal.aborted) return;
  container.innerHTML =
    appearancePanel() +
    networkPanel() +
    moduleManager(context.modules,context.labels) +
    '<div class="settings-columns"><section class="panel settings-section"><h2>本地服务</h2><p class="field-hint">端口修改会在下次启动工作台时生效。</p><form id="port-form"><label>服务端口<input name="port" type="number" min="1024" max="65535" value="' + settings.port + '" required></label><p class="field-hint">当前运行端口：' + settings.active_port + '</p><button class="button button-primary" type="submit">保存端口</button></form>' + (settings.restart_required ? '<p class="notice">端口已更新，下次启动使用 ' + settings.port + '。</p>' : '') + '</section>' +
    '<section class="panel settings-section"><h2>本地数据</h2><p class="field-hint">保存位置 <code>' + escape(settings.storage.directory) + '</code><br>加密方式 ' + escape(settings.storage.encryption) + '</p><form id="data-form"><label>清除范围<select name="scope"><option value="credentials">账号、登录状态和 API Key</option><option value="modules">模块本地数据</option><option value="all">当前数据（保留备份）</option></select></label><p class="field-hint" id="clear-description"></p><button class="button button-danger" type="submit">清除所选数据</button></form></section>' +
    '<section class="panel settings-section backup-section"><div class="section-heading"><h2>备份与恢复</h2><button class="button button-secondary" id="create-backup" type="button">创建备份</button></div><p class="field-hint">备份模块数据和文件，保存在本机 .private/backups。账号、登录状态和 API Key 不包含在内，恢复后仍使用当前账号。清除或恢复模块数据前会自动备份；备份会保留到你手动删除。</p><p class="field-hint">创建或恢复时会短暂重新加载模块。请先结束正在执行的任务。</p><div id="backup-list" role="status">正在读取备份…</div><button class="text-button" id="refresh-backups" type="button">重新读取列表</button></section></div>' +
    '<section class="panel settings-section"><div class="section-heading"><div><h2>账号与登录</h2><p>已保存的连接会在读取时复用。首次连接请使用官方窗口，或展开账号密码登录。</p></div></div><div class="provider-grid">' + auth.providers.map(providerCard).join('') + '</div></section>' +
    '<section class="panel settings-section"><h2>统一 AI 服务</h2><p class="field-hint">各模块共用这个服务。API Key 加密保存在本机。</p><form id="ai-form" class="ai-form"><label>DeepSeek API Key<input name="api_key" type="password" autocomplete="off" placeholder="' + (ai.key_saved ? '已保存，填写可更新' : '填写 API Key') + '"></label><label>模型<select name="model">' + ['deepseek-flash','deepseek-v4-pro'].map(model => '<option value="' + model + '" ' + (ai.model === model ? 'selected' : '') + '>' + model + '</option>').join('') + '</select></label><label class="checkbox-label"><input name="enabled" type="checkbox" ' + (ai.enabled ? 'checked' : '') + '>启用统一 AI 服务</label><div class="form-actions"><button class="button button-primary" type="submit">保存 AI 设置</button>' + (ai.key_saved ? '<button class="text-button danger-text" id="delete-ai-key" type="button">删除 API Key</button>' : '') + '</div></form></section>';

  bindAppearance(container.querySelector('.appearance-panel'),context.signal);
  const network = bindNetwork(container.querySelector('#network-panel'),context.signal);
  const groups = [
    ['appearance','外观',container.querySelector('.appearance-panel')],
    ['accounts','账号连接',container.querySelector('.provider-grid').closest('section')],
    ['network','网络检测',container.querySelector('#network-panel')],
    ['ai','AI 服务',container.querySelector('#ai-form').closest('section')],
    ['modules','功能模块',container.querySelector('#settings-reload').closest('section')],
    ['local','本地设置',container.querySelector('.settings-columns')],
  ];
  const tabs = document.createElement('div');
  tabs.className = 'settings-tabs';
  tabs.setAttribute('role','tablist');
  tabs.setAttribute('aria-label','设置分类');
  tabs.innerHTML = groups.map(([id,label]) => `<button id="settings-tab-${id}" role="tab" aria-controls="settings-pane-${id}" data-settings-tab="${id}" type="button">${label}</button>`).join('');
  container.prepend(tabs);
  for (const [id,,node] of groups) {
    const panel = document.createElement('div');
    panel.id = 'settings-pane-' + id;
    panel.setAttribute('role','tabpanel');
    panel.setAttribute('aria-labelledby','settings-tab-' + id);
    panel.append(node);container.append(panel);
  }
  function selectTab(id) {
    selectedTab = id;
    history.replaceState(null,'','#settings?tab=' + id);
    tabs.querySelectorAll('button').forEach(button => {const selected = button.dataset.settingsTab === id;button.setAttribute('aria-selected',String(selected));button.tabIndex = selected ? 0 : -1;});
    groups.forEach(([key]) => {container.querySelector('#settings-pane-' + key).hidden = key !== id;});
    if (id === 'network') network.open();
  }
  tabs.querySelectorAll('button').forEach((button,index) => {
    button.onclick = () => selectTab(button.dataset.settingsTab);
    button.onkeydown = event => {
      const offset = {ArrowLeft:-1,ArrowRight:1}[event.key];
      if (offset) {event.preventDefault();const target = tabs.children[(index + offset + groups.length) % groups.length];target.click();target.focus();}
    };
  });
  const requestedTab = new URLSearchParams(location.hash.split('?')[1]).get('tab');
  selectTab(groups.some(([id]) => id === requestedTab) ? requestedTab : selectedTab);

  function bindModules() {
    container.querySelector('#settings-reload').onclick = safeAction(container.querySelector('#settings-reload'),context.reload);
    container.querySelector('#settings-status').onclick = safeAction(container.querySelector('#settings-status'),async () => {
      const result = await request('/modules');
      if (context.signal.aborted) return;
      container.querySelector('#module-manager').outerHTML = moduleManager(result.modules,context.labels);
      bindModules();
      container.querySelector('#settings-status').focus();
    });
    container.querySelectorAll('[data-module-toggle]').forEach(toggle => {
      toggle.onchange = safeAction(toggle,() => context.setEnabled(toggle.dataset.moduleToggle,toggle.checked));
    });
  }
  bindModules();

  // Reload the frontend after lifecycle changes, including rejected or failed operations.
  async function dataAction(path, options, message) {
    try {
      await context.beforeClear();
      await api(path,options);
      toast(message);
    } finally { await context.refresh(); }
  }
  async function loadBackups() {
    const list = container.querySelector('#backup-list');
    try {
      const result = await request('/data/backups');
      if (context.signal.aborted) return;
      const reasons = {manual:'手动备份',before_clear:'清除前自动备份',before_restore:'恢复前自动备份',invalid:'备份损坏或不完整'};
      list.innerHTML = result.backups.length ? result.backups.map(backup => `<article class="backup-row"><div><strong>${escape(reasons[backup.reason])}</strong><p>${escape(backup.created_at ? localTime(backup.created_at) : backup.id)}${backup.valid ? ' · ' + (backup.size_bytes / 1024).toFixed(1) + ' KB · ' + backup.file_count + ' 个文件' : ''}</p></div><div class="form-actions"><button class="button button-secondary" type="button" data-restore="${escape(backup.id)}" ${backup.valid ? '' : 'disabled'}>恢复</button><button class="text-button danger-text" type="button" data-delete-backup="${escape(backup.id)}">删除</button></div></article>`).join('') : '<p class="field-hint">还没有备份。可现在创建一份，之后也会在清除或恢复前自动保存。</p>';
      list.querySelectorAll('[data-restore]').forEach(button => {button.onclick = safeAction(button,async () => {
        if (!await confirmDialog('恢复模块数据','用这份备份替换当前模块数据和文件。当前数据会先自动备份，账号和密钥保持现状。','恢复数据')) return;
        await dataAction('/data/backups/' + button.dataset.restore + '/restore',{method:'POST',body:{confirmation:'RESTORE'}},'模块数据已恢复，恢复前的数据也已备份。');
      });});
      list.querySelectorAll('[data-delete-backup]').forEach(button => {button.onclick = safeAction(button,async () => {
        if (!await confirmDialog('删除备份','永久删除这份备份，当前正在使用的数据不会改变。','删除备份')) return;
        await request('/data/backups/' + button.dataset.deleteBackup,{method:'DELETE',body:{confirmation:'DELETE_BACKUP'}});
        await loadBackups();
      });});
    } catch (error) {if (!context.signal.aborted) list.textContent = error.message;}
  }
  container.querySelector('#create-backup').onclick = safeAction(container.querySelector('#create-backup'),() => dataAction('/data/backups',{method:'POST'},'模块数据已备份。'));
  container.querySelector('#refresh-backups').onclick = safeAction(container.querySelector('#refresh-backups'),loadBackups);
  void loadBackups();

  const portForm = container.querySelector('#port-form');
  portForm.onsubmit = safeAction(portForm.querySelector('button'),async () => {
    const result = await request('/settings',{method:'PUT',body:{port:Number(new FormData(portForm).get('port'))}});
    toast(result.restart_required ? '端口已保存，下次启动生效。' : '端口设置已保存。');
    await context.refresh();
  });

  auth.providers.forEach(initial => {
    let provider = initial, deviceTimer;
    const card = container.querySelector('[data-provider="' + provider.id + '"]');
    const controls = card.querySelector('fieldset');
    const feedback = card.querySelector('[data-auth-feedback]');
    const form = card.querySelector('[data-credentials]');
    const path = '/auth/' + provider.id;
    const targetBody = () => { const target = card.querySelector('[data-auth-target]')?.value; return target ? {target} : {}; };
    function passwordRequirement() {
      if (!form) return;
      form.elements.password.required = !provider.has_password || form.elements.username.value.trim() !== provider.username;
      card.querySelector('[data-password-hint]').textContent = form.elements.password.required ? '请输入此账号的密码。' : '已保存此账号密码，留空可直接登录；填写新密码可更新。';
      form.querySelector('[type=submit]').textContent = form.elements.password.value || !provider.has_password ? '保存并登录' : '登录';
    }
    function update(result) {
      provider = result;
      const badge = card.querySelector('.status-badge');
      badge.textContent = authStatuses[provider.status];
      badge.className = 'status-badge auth-' + provider.status;
      card.querySelector('[data-recovery-hint]').textContent = recoveryHint(provider);
      card.querySelector('[data-auth-summary]').textContent = (provider.has_session ? '登录状态已在本机加密保存' : '尚未连接') + (provider.identity_verified ? ' · 账号已确认' : '');
      card.querySelector('[data-browser-options]').open = provider.status !== 'ready';
      card.querySelector('[data-auth-action=refresh]').hidden = !provider.has_session;
      passwordRequirement();
      if (provider.id === 'ids') card.querySelector('.auth-device').outerHTML = deviceCard(provider);
      clearTimeout(deviceTimer);
      if (provider.device?.setup?.status === 'waiting') deviceTimer = setTimeout(pollDevice,2000);
    }
    async function pollDevice() {
      try {
        const result = await request(path + '/status');
        if (context.signal.aborted) return;
        if (controls.disabled) { deviceTimer = setTimeout(pollDevice,2000); return; }
        update(result);
      } catch (error) {
        if (!context.signal.aborted) card.querySelector('[data-device-progress]').textContent = '暂时无法读取绑定进度，请点击检查连接与恢复。';
      }
    }
    const run = (message, action, success) => {
      const focused = document.activeElement;
      return safeAction(controls,async () => {
        card.setAttribute('aria-busy','true');
        feedback.classList.remove('danger-text');
        feedback.textContent = message;
        try {
          const result = await action();
          if (context.signal.aborted) return;
          update(result);
          feedback.textContent = result.status === 'ready' ? '' : success || result.message || result.device?.setup?.message || '操作已完成。';
        } catch (error) {
          if (context.signal.aborted) return;
          feedback.textContent = error.message;
          feedback.classList.add('danger-text');
          update(await request(path + '/status'));
        } finally { card.removeAttribute('aria-busy'); }
      })().finally(() => {
        if (!context.signal.aborted && document.activeElement === document.body && card.contains(focused)) focused.focus();
      });
    };
    if (form) {
      form.oninput = passwordRequirement;
      form.onsubmit = event => {
        event.preventDefault();
        passwordRequirement();
        if (!form.reportValidity()) return;
        const username = form.elements.username.value.trim(), password = form.elements.password.value;
        const body = targetBody();
        return run('正在登录，请稍候…',async () => {
          if (password) {
            await request(path + '/credentials',{method:'PUT',body:{username,password}});
            form.elements.password.value = '';
            form.elements.password.type = 'password';
            const show = card.querySelector('[data-show-password]');
            show.textContent = '显示'; show.setAttribute('aria-label','显示密码'); show.setAttribute('aria-pressed','false');
          }
          return request(path + '/login',{method:'POST',body});
        });
      };
    }
    card.onclick = async event => {
      const button = event.target.closest('button');
      if (!button || controls.disabled) return;
      if (button.hasAttribute('data-show-password')) {
        const show = form.elements.password.type === 'password';
        form.elements.password.type = show ? 'text' : 'password';
        button.textContent = show ? '隐藏' : '显示';
        button.setAttribute('aria-label',show ? '隐藏密码' : '显示密码');
        button.setAttribute('aria-pressed',String(show));
      } else if (button.dataset.authAction) {
        const action = button.dataset.authAction, body = targetBody();
        const messages = {browser:'正在打开官方登录窗口…','import-session':'正在验证并连接账号…',refresh:'正在检查连接与恢复…'};
        await run(messages[action],() => request(path + '/' + action,{method:'POST',body}));
      } else if (button.hasAttribute('data-forget-auth')) {
        if (!await confirmDialog('删除账号','删除 ' + provider.name + ' 保存的账号与登录状态。','删除账号')) return;
        await run('正在删除账号…',async () => {
          const result = await request(path,{method:'DELETE'});
          if (form) { form.elements.username.value = ''; form.elements.password.value = ''; }
          return result;
        },'账号已删除。');
      } else if (button.dataset.deviceAction) {
        const action = button.dataset.deviceAction;
        if (action === 'start' && !await confirmDialog('绑定本机免密码登录','将在学校账号中注册“Campus 工作台 · 本机”设备，并在当前 Windows 用户下加密保存私钥。之后应用可自动恢复学校登录，不保存学校密码。','确认绑定本机')) return;
        if (action === 'forget' && !await confirmDialog('删除本机设备凭据','删除本机保存的设备私钥。学校端登记仍保留，可到学校账号安全页撤销对应设备。','删除本机凭据')) return;
        await run('正在处理本机设备…',() => request('/auth/ids/device' + (action === 'forget' ? '' : '/' + action),{method:action === 'forget' ? 'DELETE' : 'POST',body:action === 'start' ? {confirmation:'REGISTER_THIS_DEVICE'} : undefined}),action === 'start' ? '请在学校窗口完成登录和验证，应用会自动继续。' : action === 'forget' ? '本机设备凭据已删除。' : '本机免密码登录已连接。');
      }
    };
    update(provider);
    context.signal.addEventListener('abort',() => clearTimeout(deviceTimer),{once:true});
  });

  const aiForm = container.querySelector('#ai-form');
  aiForm.onsubmit = safeAction(aiForm.querySelector('[type=submit]'),async () => {
    const fields = new FormData(aiForm);
    const body = {enabled:fields.has('enabled'),model:fields.get('model')};
    if (fields.get('api_key')) body.api_key = fields.get('api_key');
    await request('/ai/settings',{method:'PUT',body});
    aiForm.elements.api_key.value = '';
    toast('AI 设置已保存。');
    await context.refresh();
  });
  const deleteKey = container.querySelector('#delete-ai-key');
  if (deleteKey) deleteKey.onclick = safeAction(deleteKey,async () => {
    if (!await confirmDialog('删除 API Key','删除已保存的 API Key 并停用统一 AI 服务。','删除密钥')) return;
    await request('/ai/settings',{method:'PUT',body:{enabled:false,model:aiForm.elements.model.value,delete_key:true}});
    toast('API Key 已删除。');
    await context.refresh();
  });

  const clearDescriptions = {
    credentials:'删除所有账号、登录状态和 API Key，并关闭登录窗口。',
    modules:'先备份模块数据和文件，再清除当前模块数据及模块秘密，然后重新加载。秘密不包含在备份内。',
    all:'先备份模块数据和文件，再删除当前账号、登录状态、API Key 和模块数据，恢复默认设置。已有备份保留，凭据无法从备份恢复。当前端口在重启后改变。',
  };
  const dataForm = container.querySelector('#data-form');
  const scopeInput = dataForm.elements.scope;
  scopeInput.onchange = () => { container.querySelector('#clear-description').textContent = clearDescriptions[scopeInput.value]; };
  scopeInput.onchange();
  dataForm.onsubmit = safeAction(dataForm.querySelector('button'),async () => {
    const scope = scopeInput.value;
    if (!await confirmDialog('清除本地数据',clearDescriptions[scope],'清除数据')) return;
    await dataAction('/data/clear',{method:'POST',body:{scope,confirmation:'CLEAR'}},scope === 'credentials' ? '所选凭据已清除。' : '模块数据已备份，所选数据已清除。');
  });
}

