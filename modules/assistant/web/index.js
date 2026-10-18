import {link} from '/assets/campus.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const cleanup = () => removeStyle();
  context.signal.addEventListener('abort',cleanup,{once:true});
  const sounds = await import('/web/sounds.js').catch(() => null);
  if (context.signal.aborted) return cleanup;
  container.innerHTML = '<p class="field-hint">回答使用所选缓存文字，并发送至设置中选择的模型服务。邮件、讨论与转写按已读取范围提供。</p><div class="campus-toolbar"><label>资料范围<select data-course><option value="">本学期与校园邮件</option></select></label><button type="button" class="button button-secondary" data-refresh>刷新资料</button><a class="text-button" href="#settings">AI 设置</a><button type="button" class="text-button" data-clear>清除当前对话</button></div><details><summary data-coverage>选择资料</summary><div class="assistant-context" data-items></div></details><div class="assistant-messages" data-history aria-live="polite"></div><form class="campus-form" data-form><label>处理方式<select name="task"><option value="chat">连续对话</option><option value="summarize">总结资料</option><option value="classify">分类建议</option><option value="report">生成报告</option><option value="run">插件任务</option></select></label><label data-plugins hidden>执行插件<select name="plugin"></select></label><label>问题或要求<textarea name="message" required maxlength="8000" placeholder="概括本周课程安排，整理仍可处理的作业并标注来源。"></textarea></label><button class="button button-primary" type="submit">发送</button></form><section data-result aria-live="polite"></section>';
  const course = container.querySelector('[data-course]');
  const pluginPages = document.createElement('p');
  pluginPages.className = 'field-hint'; pluginPages.hidden = true;
  container.querySelector('[data-plugins]').after(pluginPages);
  const show = value => `<article class="campus-item"><h4>${value.role === 'user' ? '你' : '助手'}</h4><p>${e(value.text)}</p>${(value.citations || []).map(item => link(item.url,item.title,e)).join(' · ')}${value.tools?.length ? '<p class="field-hint">调用工具：' + value.tools.map(item => e(item.name) + (item.is_error ? '（失败）' : '（完成）')).join('、') + '</p>' : ''}${value.context?.truncated ? '<p class="field-hint">资料较多，本次处理了所选范围的一部分。</p>' : ''}${value.labels?.length ? '<ul>' + value.labels.map(item => '<li>' + e(item.label) + '：' + e(item.reason) + '</li>').join('') + '</ul>' : ''}</article>`;
  async function refresh() {
    const data = await context.api('/context?' + new URLSearchParams(course.value ? {course_id:course.value} : {}));
    const selected = course.value;
    course.innerHTML = '<option value="">本学期与校园邮件</option>' + data.courses.map(item => `<option value="${e(item.id)}">${e(item.title + ' · ' + item.term)}</option>`).join('');
    course.value = data.courses.some(item => item.id === selected) ? selected : '';
    container.querySelector('[data-items]').innerHTML = data.items.map(item => `<label><input type="checkbox" data-context value="${e(item.id)}" checked> ${e(item.title)}</label>`).join('');
    if (!data.items.length) container.querySelector('[data-coverage]').textContent = '暂无可用资料';
    const plugins = await context.api('/plugins');
    const select = form.elements.plugin;
    select.innerHTML = plugins.map(item => `<option value="${e(item.id)}">${e(item.name)}</option>`).join('');
    container.querySelector('[data-plugins]').hidden = !plugins.length;
    pluginPages.hidden = true;
  }
  const form = container.querySelector('[data-form]');
  const clear = container.querySelector('[data-clear]');
  const refreshButton = container.querySelector('[data-refresh]');
  refreshButton.onclick = () => refresh().catch(error => context.ui.toast(error.message));
  course.onchange = refreshButton.onclick;
  form.elements.task.onchange = () => { container.querySelector('[data-plugins]').hidden = form.elements.task.value !== 'run'; };
  clear.onclick = async () => {
    if (!await confirmDialog('清除当前对话','当前课程的对话记录将被清空，此操作无法撤销。','清除')) return;
    await context.api('/chat',{method:'DELETE',body:course.value ? {course_id:course.value} : {}});
    container.querySelector('[data-history]').innerHTML = '';container.querySelector('[data-result]').innerHTML = '';
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const button = form.querySelector('button');
    if (button.disabled) return;
    button.disabled = true; course.disabled = true; refreshButton.disabled = true; clear.disabled = true;
    const message = form.elements.message.value;
    const body = {course_id:course.value || null,context_ids:[...container.querySelectorAll('[data-context]:checked')].map(item => item.value)};
    try {
      const mode = form.elements.task.value;
      const payload = mode === 'chat' ? {...body,message} : mode === 'run' ? {...body,prompt:message,plugins:form.elements.plugin.value ? [form.elements.plugin.value] : []} : {...body,prompt:message,task:mode};
      const result = await context.api(mode === 'chat' ? '/chat' : mode === 'run' ? '/run' : '/generate',{method:'POST',body:payload,timeoutMs:600000});
      if (context.signal.aborted) return;
      sounds?.playSound('assistant');
      if (mode === 'chat') {
        const history = await context.api('/chat?' + new URLSearchParams(course.value ? {course_id:course.value} : {}));
        container.querySelector('[data-history]').innerHTML = history.messages.map(show).join('');
      } else container.querySelector('[data-result]').innerHTML = '<h3>本次结果</h3>' + show(result);
      form.elements.message.value = '';
    } catch(error) { if (!context.signal.aborted) context.ui.toast(error.message); }
    finally { button.disabled = false; course.disabled = false; refreshButton.disabled = false; clear.disabled = false; }
  };
  try { await refresh(); } catch(error) { cleanup(); throw error; }
  return cleanup;
}
