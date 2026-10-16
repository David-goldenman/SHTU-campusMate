import {link, time} from '/assets/campus.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  let timer;
  container.innerHTML = '<p class="field-hint">提炼会将当前学期课程与校园邮件的缓存文字发送到设置中的 DeepSeek 服务。开启自动提炼后，资料更新会触发新的分析。</p><div class="campus-toolbar"><button type="button" class="button button-primary" data-generate>提炼重要事项</button><button type="button" class="button button-secondary" data-force>重新分析当前资料</button><label class="checkbox-label"><input type="checkbox" data-auto>自动提炼</label><a class="text-button" href="#settings">AI 设置</a></div><p data-status role="status"></p><div data-error role="status"></div><div class="campus-list" data-notices></div>';
  async function refresh() {
    clearTimeout(timer);
    const value = await context.api('/snapshot');
    if (context.signal.aborted) return;
    container.querySelector('[data-auto]').checked = value.auto_generate;
    container.querySelector('[data-status]').textContent = (value.configured ? 'AI 已配置' : '请先在设置中启用 AI') + (value.generated_at ? ' · 最近提炼 ' + time(value.generated_at) : '') + (value.context?.truncated ? ' · 本次资料范围已限制' : '');
    container.querySelector('[data-error]').textContent = value.error || '';
    container.querySelector('[data-notices]').innerHTML = value.items.map(item => `<article class="campus-item"><h3>${item.read ? '' : '● '}${e(item.title)}</h3><p class="field-hint">${e({urgent:'紧急',important:'重要',normal:'一般'}[item.importance])}${item.event_at ? ' · ' + e(time(item.event_at)) : ''}</p><p>${e(item.summary)}</p><p class="field-hint">${e(item.why)}</p>${item.citations.map(source => link(source.url,source.title,e)).join(' · ')}<p><button type="button" class="text-button" data-read="${e(item.id)}" data-value="${!item.read}">${item.read ? '标记未读' : '标记已读'}</button></p></article>`).join('') || '<p class="field-hint">提炼后，重要事项与原始来源会显示在这里。</p>';
    container.querySelectorAll('[data-read]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
      await context.api('/' + encodeURIComponent(button.dataset.read) + '/read',{method:'PUT',body:{read:button.dataset.value === 'true'}}); await refresh();
    }));
    if (value.auto_generate) timer = setTimeout(() => refresh().catch(error => { if (!context.signal.aborted) context.ui.toast(error.message); }),5000);
  }
  for (const [selector,force] of [['[data-generate]',false],['[data-force]',true]]) {
    const button = container.querySelector(selector);
    button.onclick = context.ui.safeAction(button,async () => { await context.api('/generate?force=' + force,{method:'POST'}); await refresh(); });
  }
  container.querySelector('[data-auto]').onchange = async event => {
    try { await context.api('/settings',{method:'PUT',body:{auto_generate:event.currentTarget.checked}}); await refresh(); }
    catch(error) { if (!context.signal.aborted) context.ui.toast(error.message); }
  };
  context.signal.addEventListener('abort',() => clearTimeout(timer),{once:true});
  await refresh();
  return () => clearTimeout(timer);
}
