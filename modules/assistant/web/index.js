import {link} from '/assets/campus.js';

export async function mount(container,context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
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
    course.value = selected;
    container.querySelector('[data-coverage]').textContent = `本次可用资料 ${data.context.included} 条${data.context.truncated ? ' · 已限制范围' : ''}`;
    const kinds = {courses:'课程',assignments:'作业',materials:'资料',announcements:'公告',messages:'邮件',posts:'讨论',lessons:'录播',timetable:'课表'};
    container.querySelector('[data-items]').innerHTML = data.items.map(item => `<label class="checkbox-label"><input type="checkbox" data-context value="${e(item.id)}" checked>${e(kinds[item.kind])} · ${e(item.title)}${item.body_text ? ' · 已缓存文字' : ''}</label>`).join('') || '<p>先连接账号并同步资料，即可选择分析范围。</p>';
    const history = await context.api('/chat?' + new URLSearchParams(course.value ? {course_id:course.value} : {}));
    container.querySelector('[data-history]').innerHTML = history.messages.map(show).join('');
    const plugins = await context.services.ai.plugins();
    const ready = plugins.plugins.filter(item => item.status === 'ready');
    container.querySelector('[name=plugin]').innerHTML = ready.filter(item => !item.has_frontend).map(item => `<option value="${e(item.id)}">${e(item.name)}</option>`).join('') || '<option value="">请启用工具插件，或打开下方专用页面</option>';
    pluginPages.innerHTML = ready.filter(item => item.has_frontend).map(item => `<a href="#${e(item.category)}">打开${e(item.name)}</a>`).join(' · ');
    container.querySelector('[data-result]').replaceChildren();
  }
  course.onchange = () => refresh().catch(error => { if (!context.signal.aborted) context.ui.toast(error.message); });
  const refreshButton = container.querySelector('[data-refresh]');
  refreshButton.onclick = context.ui.safeAction(refreshButton,refresh);
  const clear = container.querySelector('[data-clear]');
  clear.onclick = context.ui.safeAction(clear,async () => {
    if (!await context.ui.confirmDialog('清除当前对话','将删除当前资料范围的本地对话记录。')) return;
    await context.api('/chat?' + new URLSearchParams(course.value ? {course_id:course.value} : {}),{method:'DELETE'}); await refresh();
  });
  const form = container.querySelector('[data-form]');
  form.elements.task.onchange = () => { container.querySelector('[data-plugins]').hidden = form.elements.task.value !== 'run'; pluginPages.hidden = form.elements.task.value !== 'run' || !pluginPages.childElementCount; };
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
      if (mode === 'chat') {
        const history = await context.api('/chat?' + new URLSearchParams(course.value ? {course_id:course.value} : {}));
        container.querySelector('[data-history]').innerHTML = history.messages.map(show).join('');
      } else container.querySelector('[data-result]').innerHTML = '<h3>本次结果</h3>' + show(result);
      form.elements.message.value = '';
    } catch(error) { if (!context.signal.aborted) context.ui.toast(error.message); }
    finally { button.disabled = false; course.disabled = false; refreshButton.disabled = false; clear.disabled = false; }
  };
  try { await refresh(); } catch(error) { removeStyle(); throw error; }
  return () => removeStyle();
}
