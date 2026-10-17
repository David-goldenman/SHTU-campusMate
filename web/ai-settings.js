import {escape as e, safeAction, toast, confirmDialog} from './shared.js';
import {visionSettingsPanel, mountVisionSettings} from './vision-settings.js';

const protocols = {'openai-completions':'OpenAI Chat Completions','openai-responses':'OpenAI Responses','anthropic-messages':'Anthropic Messages'};

export function aiSettingsPanel(ai) {
  const rows = ai.providers || [{provider:'deepseek',display_name:'DeepSeek',model:ai.model,key_saved:ai.key_saved}];
  return `<section class="panel settings-section settings-compact ai-settings">
    <div class="section-heading"><div><h2>模型</h2><p>选择各功能共用的模型。API Key 加密保存在本机。</p></div><button type="button" class="button button-secondary" data-ai-add>＋ 添加提供商</button></div>
    <div class="ai-current"><span>AI 服务<span class="ai-service-state">${ai.enabled ? '已启用' : '已暂停'}</span></span><label class="settings-switch"><input type="checkbox" role="switch" aria-label="启用 AI" data-ai-enabled ${ai.enabled ? 'checked' : ''}><span aria-hidden="true"></span></label></div>
    <div class="ai-provider-list">${rows.map(row => `<article class="ai-provider-card"><div class="ai-provider-info"><div class="ai-provider-name"><h3>${e(row.display_name)}</h3>${row.provider === ai.provider ? '<span class="ai-current-tag">当前使用</span>' : ''}</div><p>${e(row.model)} · ${row.key_saved ? '密钥已保存' : row.provider === 'deepseek' ? '待填写密钥' : '环境认证'}</p></div><div class="form-actions">${row.provider !== ai.provider && (row.key_saved || row.provider !== 'deepseek') ? `<button type="button" class="button button-secondary" data-ai-use="${e(row.provider)}">使用</button>` : ''}<button type="button" class="button button-secondary" data-ai-edit="${e(row.provider)}" aria-label="编辑 ${e(row.display_name)}">编辑</button>${row.provider !== 'deepseek' ? `<button type="button" class="text-button danger-text" data-ai-remove="${e(row.provider)}" aria-label="删除 ${e(row.display_name)}">删除</button>` : ''}</div></article>`).join('')}</div>
    ${visionSettingsPanel(ai.vision)}
    <dialog class="ai-provider-dialog settings-compact" aria-labelledby="ai-editor-title" data-ai-editor>
      <div class="dialog-heading"><h2 id="ai-editor-title" data-ai-editor-title>添加模型提供商</h2><button class="icon-button" type="button" data-ai-close aria-label="关闭模型编辑">×</button></div>
      <form id="ai-form" class="ai-provider-editor" hidden>
        <fieldset class="ai-provider-mode"><legend class="visually-hidden">接入方式</legend><label><input type="radio" name="mode" value="builtin" checked>第三方提供商</label><label><input type="radio" name="mode" value="custom">自定义 API</label></fieldset>
        <label data-ai-builtin>提供商<select name="provider"></select></label>
        <div data-ai-custom hidden><div class="ai-field-grid"><label>提供商 ID<input name="provider_id" pattern="[a-z][a-z0-9-]{0,63}" maxlength="64" placeholder="例如 campus-gateway"></label><label>显示名称<input name="display_name" maxlength="80" placeholder="例如 我的模型服务"></label></div><div class="ai-field-grid"><label>API 地址<input name="base_url" type="url" placeholder="https://api.example.com/v1"></label><label>API 协议<select name="protocol">${Object.entries(protocols).map(([id,name]) => `<option value="${id}">${name}</option>`).join('')}</select></label></div></div>
        <label>模型 ID<input name="model" list="ai-model-options" maxlength="200" placeholder="选择或填写模型 ID" required autocomplete="off"><datalist id="ai-model-options"></datalist></label>
        <label>API Key<input name="api_key" type="password" autocomplete="new-password" maxlength="4096" placeholder="输入 API Key"></label><p class="field-hint" data-ai-key-hint></p><p class="field-hint" data-ai-destination></p><p class="state-error" data-ai-error role="alert" hidden></p>
        <div class="ai-editor-actions"><button class="text-button danger-text" type="button" data-ai-delete-key hidden>删除密钥</button><div class="form-actions"><button class="button button-secondary" type="button" data-ai-cancel>取消</button><button class="button button-primary" type="submit">保存并启用</button></div></div>
      </form>
    </dialog>
  </section>`;
}

export function mountAISettings(panel, ai, {request, refresh, signal}) {
  mountVisionSettings(panel, ai.vision, {request, refresh, signal});
  const editor = panel.querySelector('[data-ai-editor]'), form = panel.querySelector('#ai-form'), f = form.elements;
  let catalog, editing, opener;
  const profiles = ai.providers || [{provider:'deepseek',display_name:'DeepSeek',base_url:'https://api.deepseek.com',custom:false,model:ai.model,key_saved:ai.key_saved}];
  const error = message => {const node = form.querySelector('[data-ai-error]');node.textContent = message;node.hidden = !message;};
  function update() {
    const custom = f.mode.value === 'custom';
    const row = custom ? editing : profiles.find(row => row.provider === f.provider.value);
    form.querySelector('[data-ai-builtin]').hidden = custom;
    form.querySelector('[data-ai-custom]').hidden = !custom;
    for (const field of ['provider_id','display_name','base_url','protocol']) f[field].disabled = !custom;
    f.provider.disabled = custom;
    f.provider_id.required = f.base_url.required = custom;
    f.provider_id.readOnly = Boolean(custom && editing);
    f.model.value = row?.model || '';
    f.api_key.value = '';
    form.querySelector('datalist').innerHTML = (custom ? [] : catalog.providers.find(row => row.id === f.provider.value).models).map(model => `<option value="${e(model)}"></option>`).join('');
    f.api_key.required = !custom && f.provider.value === 'deepseek' && !row?.key_saved;
    f.api_key.placeholder = row?.key_saved ? '已保存，留空沿用' : '输入 API Key';
    form.querySelector('[data-ai-key-hint]').textContent = row?.key_saved ? '密钥仅用于此提供商，页面不会显示已保存的值。' : custom ? '本机服务无需密钥时可留空。' : '留空时使用此提供商支持的本机环境认证。';
    form.querySelector('[data-ai-delete-key]').hidden = !row?.key_saved;
    form.querySelector('[data-ai-destination]').textContent = '使用 AI 时，所需学习资料将发送至' + (custom ? '你填写的 API 地址。' : `所选提供商 ${f.provider.value}。`);
    error('');
  }
  async function edit(row, button) {
    catalog ||= await request('/ai/catalog');
    if (signal.aborted) return;
    opener = button;
    editing = row;
    form.reset();
    f.provider.innerHTML = catalog.providers.map(item => `<option value="${e(item.id)}">${e(item.name)}${item.name === item.id ? '' : ' · ' + e(item.id)}</option>`).join('');
    f.mode.value = row?.custom ? 'custom' : 'builtin';
    f.provider.value = row?.custom ? 'deepseek' : row?.provider || catalog.providers[0].id;
    for (const key of ['provider_id','display_name','base_url','protocol']) f[key].value = key === 'provider_id' ? row?.provider || '' : row?.[key] || (key === 'protocol' ? 'openai-completions' : '');
    editor.querySelector('[data-ai-editor-title]').textContent = row ? '编辑 ' + row.display_name : '添加模型提供商';
    update(); form.hidden = false; editor.showModal(); (row ? f.api_key : f.provider).focus();
  }
  const add = panel.querySelector('[data-ai-add]');
  add.onclick = safeAction(add,() => edit(undefined,add));
  panel.querySelectorAll('[data-ai-edit]').forEach(button => {button.onclick = safeAction(button,() => edit(profiles.find(row => row.provider === button.dataset.aiEdit),button));});
  panel.querySelectorAll('[data-ai-use]').forEach(button => {button.onclick = safeAction(button,async () => {await request('/ai/settings',{method:'PUT',body:{provider:button.dataset.aiUse,enabled:true}});await refresh();});});
  panel.querySelectorAll('[data-ai-remove]').forEach(button => {button.onclick = safeAction(button,async () => {
    if (!await confirmDialog('删除模型提供商','删除此提供商在本机保存的配置和密钥；删除当前提供商会暂停 AI。','删除提供商')) return;
    await request('/ai/providers/' + encodeURIComponent(button.dataset.aiRemove),{method:'DELETE'});await refresh();
  });});
  panel.querySelector('[data-ai-enabled]').onchange = async event => {
    const input = event.target; input.disabled = true;
    try {await request('/ai/settings',{method:'PUT',body:{enabled:input.checked}});await refresh();}
    catch (cause) {if (!signal.aborted) {input.checked = ai.enabled;toast(cause.message);}}
    finally {input.disabled = false;}
  };
  f.provider.onchange = update;
  form.querySelectorAll('[name=mode]').forEach(input => {input.onchange = () => {editing = undefined; f.provider_id.value = ''; f.base_url.value = ''; f.display_name.value = '';update();};});
  editor.onclose = () => {form.reset();form.hidden = true;error('');if (!signal.aborted && opener?.isConnected) opener.focus();};
  editor.onclick = event => {if (event.target === editor) editor.close();};
  editor.querySelector('[data-ai-close]').onclick = () => editor.close();
  form.querySelector('[data-ai-cancel]').onclick = () => editor.close();
  signal.addEventListener('abort',() => {editor.close();form.reset();},{once:true});
  form.onsubmit = safeAction(form.querySelector('[type=submit]'),async () => {
    const custom = f.mode.value === 'custom';
    const body = {provider:custom ? f.provider_id.value.trim() : f.provider.value,model:f.model.value.trim(),custom,enabled:true};
    if (custom) Object.assign(body,{display_name:f.display_name.value.trim() || body.provider,base_url:f.base_url.value.trim(),protocol:f.protocol.value});
    if (f.api_key.value.trim()) body.api_key = f.api_key.value.trim();
    try {await request('/ai/settings',{method:'PUT',body});f.api_key.value = '';toast('模型已保存，AI 已启用。');await refresh();}
    catch (cause) {if (!signal.aborted) error(cause.message);}
  });
  const deleteKey = form.querySelector('[data-ai-delete-key]');
  deleteKey.onclick = safeAction(deleteKey,async () => {
    if (!await confirmDialog('删除 API Key','删除当前编辑提供商的密钥，并暂停 AI 服务。','删除密钥')) return;
    const id = f.mode.value === 'custom' ? editing.provider : f.provider.value;
    await request('/ai/settings',{method:'PUT',body:{provider:id,enabled:false,delete_key:true}});await refresh();
  });
}
