import {escape as e, safeAction, toast, confirmDialog} from './shared.js';

export function visionSettingsPanel(value = {}) {
  return `<details class="auth-alternative"><summary>图片识别模型</summary><form class="credential-form" data-vision-form>
    <p class="field-hint">可使用独立的 OpenAI 兼容 API。图片只发送到这里配置的服务，对话模型保持原来的设置。</p>
    <label>API 地址<input name="base_url" type="url" required maxlength="2048" value="${e(value.base_url || 'https://api.openai.com/v1')}"></label>
    <label>API 协议<select name="protocol">${Object.entries({'openai-completions':'OpenAI Chat Completions','openai-responses':'OpenAI Responses','anthropic-messages':'Anthropic Messages'}).map(([id,label]) => `<option value="${id}" ${value.protocol === id ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    <label>图片模型 ID<input name="model" maxlength="200" value="${e(value.model || '')}" placeholder="填写支持图片输入的模型 ID" autocomplete="off"></label>
    <label>图片模型 API Key<input name="api_key" type="password" autocomplete="new-password" maxlength="4096" placeholder="${value.key_saved ? '已保存，留空沿用' : '本机无认证服务可留空'}"></label>
    <label class="checkbox-label"><input type="checkbox" name="supports_images" ${value.supports_images ? 'checked' : ''}>该接口和模型支持图片输入</label>
    <label class="checkbox-label"><input type="checkbox" name="quality_confirmed" ${value.quality_confirmed ? 'checked' : ''}>我已确认此模型的识图效果适合使用</label>
    <label class="checkbox-label"><input type="checkbox" name="enabled" ${value.enabled ? 'checked' : ''}>允许向此接口发送所需图片</label>
    <p class="field-hint">${value.ready ? '图片模型已就绪。' : '确认接口能力、识图效果并启用 AI 后，自动模式才会使用图片模型。'}更换地址或模型后需重新确认；应用不会仅凭模型名称判断效果。</p>
    <p class="danger-text" data-vision-error role="alert" hidden></p><div class="form-actions"><button type="submit" class="button button-primary">保存图片模型</button>${value.key_saved ? '<button type="button" class="text-button danger-text" data-vision-delete>删除图片模型密钥</button>' : ''}</div>
  </form></details>`;
}

export function mountVisionSettings(panel, value, {request, refresh, signal}) {
  const form = panel.querySelector('[data-vision-form]'), fields = form.elements;
  const error = form.querySelector('[data-vision-error]');
  for (const name of ['base_url','protocol','model']) fields[name].addEventListener('input', () => {
    fields.supports_images.checked = fields.quality_confirmed.checked = false;
  }, {signal});
  signal.addEventListener('abort', () => {fields.api_key.value = '';}, {once:true});
  form.onsubmit = safeAction(form.querySelector('[type=submit]'), async () => {
    if (!form.reportValidity()) return;
    const body = {base_url:fields.base_url.value.trim(), protocol:fields.protocol.value, model:fields.model.value.trim(),
      enabled:fields.enabled.checked, supports_images:fields.supports_images.checked, quality_confirmed:fields.quality_confirmed.checked};
    if (fields.api_key.value.trim()) body.api_key = fields.api_key.value.trim();
    try {await request('/ai/vision/settings', {method:'PUT',body});fields.api_key.value='';toast('图片模型设置已保存。');await refresh();}
    catch (cause) {if(!signal.aborted){error.textContent=cause.message;error.hidden=false;}}
  });
  const remove = form.querySelector('[data-vision-delete]');
  if (remove) remove.onclick = safeAction(remove, async () => {
    if (!await confirmDialog('删除图片模型密钥','清除已保存的密钥并停用图片模型。','删除密钥')) return;
    const {base_url,protocol,model,supports_images,quality_confirmed} = value;
    await request('/ai/vision/settings',{method:'PUT',body:{base_url,protocol,model,supports_images,quality_confirmed,enabled:false,delete_key:true}});
    fields.api_key.value='';await refresh();
  });
}
