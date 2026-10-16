import {api, escape, toast, safeAction, confirmDialog, empty} from './shared.js';

const authStatuses = {not_connected:'待连接',ready:'已连接',verification_required:'等待验证',login_required:'需要登录'};
const targetNames = {blackboard:'Blackboard',elrc:'虚拟教学社区',timetable:'教务课表'};
const moduleStatuses = {ready:'可用',disabled:'已停用',error:'加载失败'};

function providerCard(provider) {
  const target = provider.targets?.length ? '<label>登录服务<select data-auth-target>' + provider.targets.map(id => '<option value="' + escape(id) + '" ' + (provider.target === id ? 'selected' : '') + '>' + escape(targetNames[id] || id) + '</option>').join('') + '</select></label>' : '';
  const credentials = provider.id === 'coremail' ? '' : `<details class="auth-alternative"><summary>可选：保存密码用于重新登录</summary><form class="credential-form" data-credentials="${escape(provider.id)}"><label>账号<input name="username" autocomplete="username" value="${escape(provider.username)}" required></label><label>密码<input name="password" type="password" autocomplete="current-password" placeholder="${provider.has_password ? '填写新密码以更新账号' : '填写登录密码'}" required></label><button class="button button-secondary" type="submit">保存账号</button></form><button class="button button-secondary" data-auth-action="login" type="button">用已保存方式登录</button></details>`;
  const device = provider.id !== 'ids' ? '' : `<section class="auth-device"><h4>本机免密码登录</h4><p class="field-hint">为课表、Blackboard 和虚拟教学社区自动恢复登录。使用学校的设备凭据，在本机加密保存，无需保存学校密码。</p>${provider.device.configured ? `<p>${provider.device.enabled ? '已绑定 · 过期后自动续期' : '已绑定其他账号 · 当前账号不使用此凭据'}</p><button class="text-button danger-text" data-device-action="forget" type="button">删除本机凭据</button>` : provider.device.pending ? '<p>上次绑定结果待确认，凭据已加密保留。</p><button class="button button-secondary" data-device-action="recover" type="button">检查上次绑定结果</button><button class="text-button danger-text" data-device-action="forget" type="button">清除待确认凭据</button>' : `<button class="button button-primary" data-device-action="start" type="button" ${provider.device.setup?.status === 'waiting' ? 'disabled' : ''}>连接并绑定本机</button><p class="field-hint">自动进入学校账号安全页并引导身份复核。请完成学校要求的登录或验证，应用随后自动绑定；无需手动创建 Windows 凭据。这是应用的软件设备凭据，无需调用 Windows Hello。</p>`}<p class="field-hint" data-device-progress role="status">${escape(provider.device.setup?.message || '')}</p></section>`;
  const recovery = provider.automatic_recovery ? '同步前检查登录，过期后自动尝试恢复一次。' : provider.id === 'ids' ? '当前仅保存会话；绑定本机设备后可自动续期。' : provider.id === 'coremail' ? '邮箱会话失效时会提示重新打开官方登录窗口。' : '当前仅保存会话；失效后提示重新连接，也可选择保存密码。';
  return `<article class="provider-card" data-provider="${escape(provider.id)}"><header><h3>${escape(provider.name)}</h3><span class="status-badge auth-${escape(provider.status)}">${authStatuses[provider.status]}</span></header>${provider.message ? '<p class="provider-message">' + escape(provider.message) + '</p>' : ''}${target}<p class="field-hint">${recovery}</p><div class="provider-actions"><button class="button button-primary" data-auth-action="browser" type="button">1. 打开官方登录窗口</button><button class="button button-secondary" data-auth-action="import-session" type="button">2. 登录完成，连接账号</button><button class="button button-secondary" data-auth-action="refresh" type="button">检查连接与恢复</button></div>${device}${credentials}<div class="provider-footer"><span>${provider.has_session ? '登录状态已在本机加密保存' : '完成官方登录后连接'}${provider.identity_verified ? ' · 账号已确认' : ''}</span><button class="text-button danger-text" data-forget-auth type="button">删除账号</button></div></article>`;
}

function moduleManager(modules, labels) {
  return '<section class="panel settings-section"><div class="section-heading"><div><h2>模块管理</h2><p>每个模块在自己的分类中独立打开。</p></div><button class="button button-secondary" id="settings-reload" type="button">刷新模块</button></div>' + (modules.length ? '<div class="module-list">' + modules.map(module => '<article class="module-row"><div class="module-info"><div><h3>' + escape(module.name) + '</h3><span class="module-version">v' + escape(module.version) + '</span><span class="module-status status-' + escape(module.status) + '">' + moduleStatuses[module.status] + '</span></div><p><a href="#' + escape(module.category) + '">' + escape(labels.get(module.category)) + '</a><span>' + escape(module.id) + '</span>' + (module.harness ? '<span>AI 插件</span>' : !module.frontend_url && module.status === 'ready' ? '<span>后台模块</span>' : '') + '</p>' + (module.error ? '<p class="danger-text">' + escape(module.error) + '</p>' : '') + '</div><label class="module-toggle"><input type="checkbox" data-module-toggle="' + escape(module.id) + '" aria-label="' + escape(module.name) + '启用状态" ' + (module.enabled ? 'checked' : '') + '><span>启用</span></label></article>').join('') + '</div>' : empty('模块目录已准备就绪','添加模块后，刷新列表即可在这里启用和管理。')) + '</section>';
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
    moduleManager(context.modules,context.labels) +
    '<div class="settings-columns"><section class="panel settings-section"><h2>本地服务</h2><p class="field-hint">端口修改会在下次启动工作台时生效。</p><form id="port-form"><label>服务端口<input name="port" type="number" min="1024" max="65535" value="' + settings.port + '" required></label><p class="field-hint">当前运行端口：' + settings.active_port + '</p><button class="button button-primary" type="submit">保存端口</button></form>' + (settings.restart_required ? '<p class="notice">端口已更新，下次启动使用 ' + settings.port + '。</p>' : '') + '</section>' +
    '<section class="panel settings-section"><h2>本地数据</h2><p class="field-hint">保存位置 <code>' + escape(settings.storage.directory) + '</code><br>加密方式 ' + escape(settings.storage.encryption) + '</p><form id="data-form"><label>清除范围<select name="scope"><option value="credentials">账号、登录状态和 API Key</option><option value="modules">模块本地数据</option><option value="all">全部本地数据</option></select></label><p class="field-hint" id="clear-description"></p><button class="button button-danger" type="submit">清除所选数据</button></form></section></div>' +
    '<section class="panel settings-section"><div class="section-heading"><div><h2>账号与登录</h2><p>在官方窗口登录后，返回连接账号。登录状态加密保存在本机；同一账号续期保留缓存，切换账号自动隔离。</p></div></div><div class="provider-grid">' + auth.providers.map(providerCard).join('') + '</div></section>' +
    '<section class="panel settings-section"><h2>统一 AI 服务</h2><p class="field-hint">各模块共用这个服务。API Key 加密保存在本机。</p><form id="ai-form" class="ai-form"><label>DeepSeek API Key<input name="api_key" type="password" autocomplete="off" placeholder="' + (ai.key_saved ? '已保存，填写可更新' : '填写 API Key') + '"></label><label>模型<select name="model">' + ['deepseek-flash','deepseek-v4-pro'].map(model => '<option value="' + model + '" ' + (ai.model === model ? 'selected' : '') + '>' + model + '</option>').join('') + '</select></label><label class="checkbox-label"><input name="enabled" type="checkbox" ' + (ai.enabled ? 'checked' : '') + '>启用统一 AI 服务</label><div class="form-actions"><button class="button button-primary" type="submit">保存 AI 设置</button>' + (ai.key_saved ? '<button class="text-button danger-text" id="delete-ai-key" type="button">删除 API Key</button>' : '') + '</div></form></section>';

  container.querySelector('#settings-reload').onclick = safeAction(container.querySelector('#settings-reload'),context.reload);
  container.querySelectorAll('[data-module-toggle]').forEach(toggle => {
    toggle.onchange = safeAction(toggle,() => context.setEnabled(toggle.dataset.moduleToggle,toggle.checked));
  });

  const portForm = container.querySelector('#port-form');
  portForm.onsubmit = safeAction(portForm.querySelector('button'),async () => {
    const result = await request('/settings',{method:'PUT',body:{port:Number(new FormData(portForm).get('port'))}});
    toast(result.restart_required ? '端口已保存，下次启动生效。' : '端口设置已保存。');
    await context.refresh();
  });

  container.querySelectorAll('[data-credentials]').forEach(form => {
    form.onsubmit = safeAction(form.querySelector('button'),async () => {
      const fields = new FormData(form);
      await request('/auth/' + encodeURIComponent(form.dataset.credentials) + '/credentials',{
        method:'PUT',body:{username:fields.get('username'),password:fields.get('password')},
      });
      form.elements.password.value = '';
      toast('账号已保存。');
      await context.refresh();
    });
  });

  container.querySelectorAll('[data-auth-action]').forEach(button => {
    button.onclick = safeAction(button,async () => {
      const card = button.closest('[data-provider]');
      const target = card.querySelector('[data-auth-target]')?.value;
      try {
        await request('/auth/' + encodeURIComponent(card.dataset.provider) + '/' + button.dataset.authAction,{method:'POST',body:target ? {target} : {}});
      } finally {
        if (!context.signal.aborted) await context.refresh();
      }
    });
  });

  container.querySelectorAll('[data-forget-auth]').forEach(button => {
    button.onclick = safeAction(button,async () => {
      const card = button.closest('[data-provider]');
      if (!await confirmDialog('删除账号','删除 ' + card.querySelector('h3').textContent + ' 保存的账号与登录状态。','删除账号')) return;
      await request('/auth/' + encodeURIComponent(card.dataset.provider),{method:'DELETE'});
      toast('账号已删除。');
      await context.refresh();
    });
  });

  container.querySelectorAll('[data-device-action]').forEach(button => {
    button.onclick = safeAction(button,async () => {
      const action = button.dataset.deviceAction;
      if (['bind','start'].includes(action) && !await confirmDialog('绑定本机免密码登录','将在学校账号中注册“Campus 工作台 · 本机”设备，并在当前 Windows 用户下加密保存私钥。之后应用可自动恢复学校登录，不保存学校密码。','确认绑定本机')) return;
      if (action === 'forget' && !await confirmDialog('删除本机设备凭据','删除本机保存的设备私钥。学校端登记仍保留，可到学校账号安全页撤销对应设备。','删除本机凭据')) return;
      try {
        await request('/auth/ids/device' + (action === 'forget' ? '' : '/' + action), {method:action === 'forget' ? 'DELETE' : 'POST',body:['bind','start'].includes(action) ? {confirmation:'REGISTER_THIS_DEVICE'} : undefined});
        toast(['browser','start'].includes(action) ? '请在学校窗口完成登录和验证，应用会自动继续。' : action === 'forget' ? '本机设备凭据已删除。' : '本机免密码登录已连接。');
      } finally {
        if (!context.signal.aborted) await context.refresh();
      }
    });
  });

  let deviceTimer;
  if (auth.providers.find(provider => provider.id === 'ids')?.device?.setup?.status === 'waiting') {
    const pollDevice = async () => {
      try {
        const result = await request('/auth/ids/status');
        if (context.signal.aborted) return;
        container.querySelector('[data-device-progress]').textContent = result.device.setup.message || '';
        if (result.device.setup.status !== 'waiting') { await context.refresh(); return; }
      } catch (error) {
        if (context.signal.aborted) return;
        container.querySelector('[data-device-progress]').textContent = '暂时无法读取绑定进度，请稍后刷新设置。';
        return;
      }
      deviceTimer = setTimeout(pollDevice, 2000);
    };
    deviceTimer = setTimeout(pollDevice, 2000);
    context.signal.addEventListener('abort', () => clearTimeout(deviceTimer), {once:true});
  }

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
    modules:'清除模块保存的本地数据，然后重新加载模块。',
    all:'删除账号、登录状态、API Key 和模块数据，将端口设置恢复为 16666。当前运行端口在重启后改变。',
  };
  const dataForm = container.querySelector('#data-form');
  const scopeInput = dataForm.elements.scope;
  scopeInput.onchange = () => { container.querySelector('#clear-description').textContent = clearDescriptions[scopeInput.value]; };
  scopeInput.onchange();
  dataForm.onsubmit = safeAction(dataForm.querySelector('button'),async () => {
    const scope = scopeInput.value;
    if (!await confirmDialog('清除本地数据',clearDescriptions[scope],'清除数据')) return;
    await context.beforeClear();
    await api('/data/clear',{method:'POST',body:{scope,confirmation:'CLEAR'}});
    toast('所选数据已清除。');
    await context.refresh();
  });
}

