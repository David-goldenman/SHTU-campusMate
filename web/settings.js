import {api, escape, toast, safeAction, confirmDialog, empty, dialog} from './shared.js';
import {aiSettingsPanel, mountAISettings} from './ai-settings.js';
import {networkPanel, bindNetwork} from './network.js';
import {generatePassword} from './password-generator.js';
import {appearancePanel, bindAppearance} from './themes/appearance.js';

const authStatuses = {not_connected:'待连接',ready:'已连接',verification_required:'等待验证',login_required:'需要登录'};
const targetNames = {blackboard:'Blackboard',elrc:'虚拟教学社区',ecourse:'E 云课堂',timetable:'教务系统'};
const moduleStatuses = {ready:'已加载',disabled:'已停用',error:'异常',stopping:'正在停止'};
let selectedTab = 'accounts';

function recoveryHint(provider) {
  if (provider.id === 'coremail' && provider.imap?.configured) return 'IMAP 专用密码已加密保存，读取邮件时直接连接，不需要重新验证。';
  return provider.automatic_recovery ? '同步前检查登录，过期后自动尝试恢复一次。' : provider.id === 'ids' ? '绑定本机设备或保存密码后，可在过期时自动恢复登录。' : provider.id === 'coremail' ? '邮箱会话失效时，请重新打开官方登录窗口。' : '仅连接会话时，过期需重新登录；保存密码后可自动尝试恢复。';
}

function imapPanel(provider) {
  const imap = provider.imap || {};
  const configured = imap.configured === true;
  const username = imap.username || provider.username || '';
  return `<section class="imap-login" data-imap>
    <header class="imap-login-heading"><div><h4>IMAP 登录<span class="imap-recommend">推荐</span></h4><p>用学校生成的客户端专用密码直连邮箱，不依赖容易过期的网页会话。</p></div><button class="text-button" data-imap-guide type="button">设置指引</button></header>
    <p class="imap-note">使用 IMAP 登录邮箱，推荐此方法，不会出现验证失败或者重新认证的问题。</p>
    <form class="imap-form" data-imap-form>
      <label for="imap-username">邮箱账号</label>
      <input id="imap-username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="320" value="${escape(username)}" placeholder="例如 name@shanghaitech.edu.cn" required>
      <label for="imap-password">客户端专用密码</label>
      <div class="password-field"><input id="imap-password" name="password" type="password" autocomplete="off" maxlength="4096" aria-describedby="imap-password-hint" ${configured ? '' : 'required'}><button class="text-button" data-show-password type="button" aria-label="显示密码" aria-pressed="false">显示</button></div>
      <p class="field-hint" id="imap-password-hint">${imap.password_saved ? '专用密码已加密保存；留空继续使用，填写新密码可更新。' : '请先在学校邮箱“安全设置 → 客户端专用密码”生成，不要填写统一认证密码。'}</p>
      <div class="imap-server-grid">
        <label for="imap-host">收件服务器<input id="imap-host" value="${escape(imap.host || 'imap.shanghaitech.edu.cn')}" readonly aria-readonly="true"></label>
        <label for="imap-port">端口<input id="imap-port" name="port" type="number" inputmode="numeric" min="1" max="65535" step="1" value="${Number(imap.port) || 993}" required></label>
        <label class="imap-ssl" for="imap-ssl"><input id="imap-ssl" name="ssl" type="checkbox" ${imap.ssl === false ? '' : 'checked'}> 使用 SSL/TLS</label>
      </div>
      <div class="form-actions">
        <button class="button button-primary" type="submit">保存并登录</button>
        <button class="button button-secondary" data-imap-check type="button" ${configured ? '' : 'hidden'}>检查连接</button>
        <button class="text-button danger-text" data-imap-forget type="button" ${configured ? '' : 'hidden'}>删除 IMAP 登录</button>
      </div>
      <p class="field-hint imap-state" data-imap-state role="status">${configured ? 'IMAP 已配置并优先使用；官方网页登录缓存已停用。' : '尚未配置 IMAP。保存后会优先使用此登录方式。'}</p>
    </form>
  </section>`;
}

function openImapGuide() {
  const body = document.createElement('div');
  body.className = 'imap-guide';
  body.innerHTML = `<div class="imap-guide-pages">
      <section class="imap-guide-page" data-guide-page="1" aria-label="第一页：生成客户端专用密码">
        <div class="imap-guide-copy"><span class="imap-guide-step">步骤 1 · 生成专用密码</span><h3>在学校邮箱安全设置中生成</h3><ol><li>打开学校邮箱，点击左下角“设置”。</li><li>进入“安全设置”，选择“客户端专用密码”。</li><li>点击“生成专用密码”，填写便于识别的名称并确认。</li></ol><p>专用密码只在生成时完整显示一次，请立即复制。</p></div>
        <figure class="imap-guide-figure"><img src="/assets/mail-imap-guide-1.png" alt="学校邮箱设置入口、安全设置与客户端专用密码生成位置示意图" width="1908" height="1072"><figcaption>图中标出了从设置到生成专用密码的完整入口。</figcaption></figure>
      </section>
      <section class="imap-guide-page" data-guide-page="2" aria-label="第二页：填写 IMAP 登录信息" hidden>
        <div class="imap-guide-copy"><span class="imap-guide-step">步骤 2 · 填写登录信息</span><h3>复制专用密码并核对服务器</h3><ol><li>复制刚生成的客户端专用密码。</li><li>回到本页，在 IMAP 登录中填写邮箱账号和专用密码。</li><li>确认服务器为 <code>imap.shanghaitech.edu.cn</code>，SSL 端口为 <code>993</code>。</li></ol><p>不要把专用密码发给他人；如怀疑泄露，请在学校邮箱中移除并重新生成。</p></div>
        <figure class="imap-guide-figure"><img src="/assets/mail-imap-guide-2.png" alt="客户端专用密码生成结果、复制按钮与 IMAP 服务器端口示意图" width="752" height="590"><figcaption>第二张图对应复制专用密码和核对 IMAP 参数的位置。</figcaption></figure>
      </section>
    </div>
    <footer class="imap-guide-footer"><span data-guide-count aria-live="polite">第 1 / 2 页</span><div class="form-actions"><button class="button button-secondary" data-guide-prev type="button" disabled>上一页</button><button class="button button-secondary" data-guide-next type="button">下一页</button><button class="button button-primary" data-guide-done type="button" hidden>我已知晓</button></div></footer>`;
  const pages = [...body.querySelectorAll('[data-guide-page]')];
  const prev = body.querySelector('[data-guide-prev]'), next = body.querySelector('[data-guide-next]'), done = body.querySelector('[data-guide-done]'), count = body.querySelector('[data-guide-count]');
  let page = 1;
  const draw = () => {
    pages.forEach(section => { section.hidden = Number(section.dataset.guidePage) !== page; });
    prev.disabled = page === 1;
    next.hidden = page === pages.length;
    done.hidden = page !== pages.length;
    count.textContent = `第 ${page} / ${pages.length} 页`;
    pages[page - 1].querySelector('h3')?.focus?.();
  };
  prev.onclick = () => { if (page > 1) { page -= 1; draw(); } };
  next.onclick = () => { if (page < pages.length) { page += 1; draw(); } };
  done.onclick = () => node.close();
  const node = dialog('使用 IMAP 登录学校邮箱', body);
  node.classList.add('imap-guide-dialog');
  node.addEventListener('close', () => node.classList.remove('imap-guide-dialog'), {once:true});
  draw();
  return node;
}

function deviceCard(provider) {
  return `<details class="auth-device" ${provider.device.setup?.status === 'waiting' ? 'open' : ''}><summary>本机免密码登录 <span>${provider.device.configured && provider.device.enabled ? '已绑定' : provider.device.pending ? '待确认' : '未绑定'}</span></summary><div><p class="field-hint">用于自动恢复学校服务登录，设备凭据加密保存在本机。</p>${provider.device.configured ? `<p>${provider.device.enabled ? '已绑定 · 过期后自动续期' : '已绑定其他账号 · 当前账号不使用此凭据'}</p><button class="text-button danger-text" data-device-action="forget" type="button">删除本机凭据</button>` : provider.device.pending ? '<p>上次绑定结果待确认。</p><button class="button button-secondary" data-device-action="recover" type="button">检查绑定结果</button><button class="text-button danger-text" data-device-action="forget" type="button">清除待确认凭据</button>' : `<button class="button button-secondary" data-device-action="start" type="button" ${provider.device.setup?.status === 'waiting' ? 'disabled' : ''}>连接并绑定本机</button><p class="field-hint">在学校窗口完成身份复核后自动绑定。</p>`}<p class="field-hint" data-device-progress role="status">${escape(provider.device.setup?.message || '')}</p></div></details>`;
}

function providerCard(provider) {
  const id = escape(provider.id);
  const target = provider.targets?.length ? '<label>登录服务<select data-auth-target>' + provider.targets.map(id => '<option value="' + escape(id) + '" ' + (provider.target === id ? 'selected' : '') + '>' + escape(targetNames[id] || id) + '</option>').join('') + '</select></label>' : '';
  const credentials = provider.id === 'coremail' ? '' : `<details class="auth-alternative"><summary>账号密码登录</summary><form class="credential-form" data-credentials="${id}"><p class="field-hint">提交后加密保存账号密码，并立即登录。需要验证码时，请使用官方窗口继续验证。</p><label for="auth-${id}-username">账号</label><input id="auth-${id}-username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="320" value="${escape(provider.username)}" required><label for="auth-${id}-password">密码</label><div class="password-field"><input id="auth-${id}-password" name="password" type="password" autocomplete="current-password" maxlength="4096" aria-describedby="auth-${id}-password-hint"><button class="text-button" data-show-password type="button" aria-label="显示密码" aria-pressed="false">显示</button><button class="text-button" data-generate-password type="button" aria-label="由种子生成密码" title="同一种子、平台和长度会生成同一密码">生成</button></div><p class="field-hint" id="auth-${id}-password-hint" data-password-hint></p><button class="button button-primary" type="submit">登录</button></form></details>`;
  const description = provider.id === 'ids' ? '课表、Blackboard、E 云课堂与教学社区' : provider.id === 'coremail' ? '校园邮件与智能分类' : provider.id === 'gradescope' ? '作业、题目与提交状态' : '课程讨论与公告';
  const imap = provider.id === 'coremail' ? imapPanel(provider) : '';
  const browserSummary = provider.id === 'coremail' ? '改用官方网页登录' : '使用官方窗口连接';
  const browserHint = provider.id === 'coremail' ? '网页会话过期后需要重新验证；配置 IMAP 后此入口会停用。' : '在本机 Edge 中登录后连接，后续复用此服务的浏览器资料。';
  return `<article class="provider-card" data-provider="${id}"><details class="provider-connection"><summary><div><h3>${escape(provider.name)}</h3><p>${description}</p></div><span class="status-badge auth-${escape(provider.status)}">${authStatuses[provider.status]}</span><span class="provider-chevron" aria-hidden="true">⌄</span></summary><div class="provider-expanded"><p class="provider-message" data-auth-feedback role="status">${escape(provider.message || '')}</p><fieldset class="provider-controls" aria-label="${escape(provider.name)}登录操作">${imap}${target}<p class="field-hint" data-recovery-hint>${recoveryHint(provider)}</p><details class="auth-alternative" data-browser-options><summary>${browserSummary}</summary><div class="provider-actions"><button class="button button-primary" data-auth-action="browser" type="button">打开登录窗口</button><button class="button button-secondary" data-auth-action="import-session" type="button">登录完成，连接账号</button></div><p class="field-hint">${browserHint}</p></details><button class="text-button" data-auth-action="refresh" type="button">检查连接</button>${credentials}${provider.id === 'ids' ? deviceCard(provider) : ''}<div class="provider-footer"><span data-auth-summary></span><button class="text-button danger-text" data-forget-auth type="button">删除账号</button></div></fieldset></div></details></article>`;
}

const localTime = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '暂无';

function runtimeInfo(runtime) {
  if (!runtime) return '';
  const last = runtime.last_request, error = runtime.last_error;
  const workers = {running:'运行中',stopped:'已退出',idle:'已结束',cancelled:'已取消',error:'失败'};
  return `<details class="module-runtime"><summary class="${error ? 'danger-text' : ''}">运行详情${error ? ' · 最近有失败' : ''}</summary><div><p>进行中请求 ${runtime.active_requests} · 等待调用 ${runtime.pending_calls}</p><p>最近接口成功：${escape(localTime(runtime.last_success_at))}${last ? ' · 最近请求 ' + last.status + ' / ' + last.duration_ms + ' ms' : ''}</p>${runtime.workers.map(worker => `<p class="${['stopped','error'].includes(worker.status) ? 'danger-text' : ''}">${worker.kind === 'thread' ? '后台线程' : '后台任务'} · ${escape(worker.name)}：${escape(workers[worker.status])}</p>`).join('')}${error ? `<p class="danger-text">最近失败：${escape(localTime(error.at))} · HTTP ${error.status}${error.request_id ? ' · 错误编号 ' + escape(error.request_id) : ''}</p>` : ''}</div></details>`;
}

function moduleManager(modules, labels) {
  return `<section class="panel settings-section settings-compact" id="module-manager">
    <div class="section-heading"><div><h2>模块与插件</h2><p>管理工作台功能及 AI 插件。</p></div><div class="form-actions"><button class="button button-secondary" id="settings-status" type="button">刷新状态</button><button class="button button-secondary" id="settings-reload" type="button">重新加载</button></div></div>
    ${modules.length ? '<div class="module-list">' + modules.map(module => `<article class="module-row"><div class="module-info"><div><h3>${escape(module.name)}</h3><span class="module-status status-${escape(module.status)}">${moduleStatuses[module.status]}</span></div><p><span>${escape(module.id)} · v${escape(module.version)}</span>${module.harness ? '<span>AI 插件</span>' : !module.frontend_url && module.status === 'ready' ? '<span>后台模块</span>' : ''}${module.frontend_url ? `<a href="#${escape(module.category)}">打开${escape(labels.get(module.category) || '页面')}</a>` : ''}</p>${module.error ? `<p class="danger-text">${escape(module.error)}</p>` : ''}${runtimeInfo(module.runtime)}</div><label class="settings-switch"><input type="checkbox" role="switch" data-module-toggle="${escape(module.id)}" aria-label="${escape(module.name)}启用状态" ${module.enabled ? 'checked' : ''}><span aria-hidden="true"></span></label></article>`).join('') + '</div>' : empty('模块目录已准备就绪','添加模块后，刷新列表即可在这里启用和管理。')}
    <p class="settings-updated">状态更新于 ${escape(localTime(new Date().toISOString()))}</p>
  </section>`;
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
    aiSettingsPanel(ai);

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
  async function dataAction(path, options, message, reload = false) {
    let completed=false;
    try {
      await context.beforeClear();
      await api(path,options);
      completed=true;toast(message);
    } finally { if(completed && reload)location.reload();else await context.refresh(); }
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
    const imapForm = card.querySelector('[data-imap-form]');
    const path = '/auth/' + provider.id;
    const targetBody = () => { const target = card.querySelector('[data-auth-target]')?.value; return target ? {target} : {}; };
    function passwordRequirement() {
      if (!form) return;
      form.elements.password.required = !provider.has_password || form.elements.username.value.trim() !== provider.username;
      card.querySelector('[data-password-hint]').textContent = form.elements.password.required ? '请输入此账号的密码。' : '已保存此账号密码，留空可直接登录；填写新密码可更新。';
      form.querySelector('[type=submit]').textContent = form.elements.password.value || !provider.has_password ? '保存并登录' : '登录';
    }
    function imapPasswordRequirement() {
      if (!imapForm) return;
      const imap = provider.imap || {};
      const changed = imapForm.elements.username.value.trim() !== (imap.username || '');
      imapForm.elements.password.required = !imap.configured || changed;
      const hint = card.querySelector('#imap-password-hint');
      if (hint) hint.textContent = imapForm.elements.password.required ? '请填写学校邮箱“客户端专用密码”，不要使用统一认证密码。' : '专用密码已加密保存；留空继续使用，填写新密码可更新。';
      imapForm.querySelector('[type=submit]').textContent = imap.configured ? '更新并登录' : '保存并登录';
    }
    function update(result) {
      provider = result;
      if (['verification_required','login_required'].includes(provider.status)) card.querySelector('.provider-connection').open = true;
      const badge = card.querySelector('.status-badge');
      badge.textContent = authStatuses[provider.status];
      badge.className = 'status-badge auth-' + provider.status;
      card.querySelector('[data-recovery-hint]').textContent = recoveryHint(provider);
      const imap = provider.imap || {};
      card.querySelector('[data-auth-summary]').textContent = (provider.id === 'coremail' ? imap.configured ? 'IMAP 专用密码已加密保存' : '尚未配置 IMAP' : provider.has_session ? '登录状态已在本机加密保存' : '尚未连接') + (provider.identity_verified ? ' · 账号已确认' : '');
      card.querySelector('[data-browser-options]').open = provider.status !== 'ready';
      card.querySelector('[data-browser-options]').hidden = provider.id === 'coremail' && imap.configured;
      card.querySelector('[data-auth-action=refresh]').hidden = !provider.has_session;
      if (imapForm) {
        if (imap.configured) {
          imapForm.elements.username.value = imap.username || '';
          imapForm.elements.port.value = Number(imap.port) || 993;
          imapForm.elements.ssl.checked = imap.ssl !== false;
        }
        imapForm.querySelector('[data-imap-check]').hidden = !imap.configured;
        imapForm.querySelector('[data-imap-forget]').hidden = !imap.configured;
        const state = imapForm.querySelector('[data-imap-state]');
        if (state) state.textContent = imap.configured
          ? `IMAP 已配置并优先使用（${imap.username} · ${imap.host}:${imap.port}${imap.ssl === false ? ' · 非 SSL' : ' · SSL'}）。官方网页登录缓存已停用。`
          : '尚未配置 IMAP。保存后会优先使用此登录方式。';
        imapPasswordRequirement();
      }
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
    if (imapForm) {
      imapForm.oninput = imapPasswordRequirement;
      imapForm.onsubmit = event => {
        event.preventDefault();
        if (!imapForm.reportValidity()) return;
        const data = new FormData(imapForm);
        return run('正在验证 IMAP 登录…',async () => {
          const result = await request('/auth/coremail/imap',{method:'PUT',body:{
            username:String(data.get('username') || '').trim(), password:String(data.get('password') || ''),
            port:Number(data.get('port')), ssl:data.get('ssl') === 'on',
          }});
          imapForm.elements.password.value = '';
          imapForm.elements.password.type = 'password';
          const show = imapForm.querySelector('[data-show-password]');
          show.textContent = '显示'; show.setAttribute('aria-label','显示密码'); show.setAttribute('aria-pressed','false');
          return result;
        },'IMAP 登录已保存。');
      };
    }
    card.onclick = async event => {
      const button = event.target.closest('button');
      if (!button || controls.disabled) return;
      if (button.hasAttribute('data-show-password')) {
        const targetForm = button.closest('form');
        const input = targetForm?.elements.password;
        if (!input) return;
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        button.textContent = show ? '隐藏' : '显示';
        button.setAttribute('aria-label',show ? '隐藏密码' : '显示密码');
        button.setAttribute('aria-pressed',String(show));
      } else if (button.hasAttribute('data-imap-guide')) {
        openImapGuide();
      } else if (button.hasAttribute('data-imap-check')) {
        await run('正在检查 IMAP 连接…',() => request('/auth/coremail/imap/check',{method:'POST'}),'IMAP 连接正常。');
      } else if (button.hasAttribute('data-imap-forget')) {
        if (!await confirmDialog('删除 IMAP 登录','删除加密保存的邮箱账号和客户端专用密码，并停止使用 IMAP 读取邮件。','删除 IMAP 登录')) return;
        await run('正在删除 IMAP 登录…',async () => {
          const result = await request('/auth/coremail/imap',{method:'DELETE'});
          imapForm.elements.username.value = '';
          imapForm.elements.password.value = '';
          return result;
        },'IMAP 登录已删除。');
      } else if (button.hasAttribute('data-generate-password')) {
        const lengthRaw = window.prompt('密码长度（12-32，默认 16）：','16');
        if (lengthRaw === null) return;
        const length = Number(lengthRaw.trim() || 16);
        if (!Number.isInteger(length) || length < 12 || length > 32) {
          feedback.textContent = '请输入 12 到 32 之间的整数。';
          feedback.classList.add('danger-text');
          return;
        }
        const seed = window.prompt('输入种子密码（仅在本机计算，不保存种子）：','');
        if (seed === null) return;
        if (!seed.trim()) {
          feedback.textContent = '请输入非空的种子密码。';
          feedback.classList.add('danger-text');
          return;
        }
        await safeAction(controls,async () => {
          const password = await generatePassword(provider.id,seed,length);
          if (context.signal.aborted) return;
          form.elements.password.value = password;
          form.elements.password.type = 'text';
          const show = card.querySelector('[data-show-password]');
          show.textContent = '隐藏';show.setAttribute('aria-label','隐藏密码');show.setAttribute('aria-pressed','true');
          passwordRequirement();
          feedback.classList.remove('danger-text');
          feedback.textContent = '密码已生成并填入，平台现有密码不会自动更改。';
        })();
      } else if (button.dataset.authAction) {
        const action = button.dataset.authAction, body = targetBody();
        const messages = {browser:'正在打开官方登录窗口…','import-session':'正在验证并连接账号…',refresh:'正在检查连接与恢复…'};
        await run(messages[action],() => request(path + '/' + action,{method:'POST',body}));
      } else if (button.hasAttribute('data-forget-auth')) {
        if (!await confirmDialog('删除账号','删除 ' + provider.name + ' 保存的账号与登录状态。','删除账号')) return;
        await run('正在删除账号…',async () => {
          const result = await request(path,{method:'DELETE'});
          if (form) { form.elements.username.value = ''; form.elements.password.value = ''; }
          if (imapForm) { imapForm.elements.username.value = ''; imapForm.elements.password.value = ''; }
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

  mountAISettings(container.querySelector('.ai-settings'),ai,{request,refresh:context.refresh,signal:context.signal});

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
    await dataAction('/data/clear',{method:'POST',body:{scope,confirmation:'CLEAR'}},scope === 'credentials' ? '所选凭据已清除。' : '模块数据已备份，所选数据已清除。',scope === 'all');
  });
}

