import {link, time} from '/assets/campus.js';

const toolNames = {study_query:'学习资料查询',study_search:'课程原文检索',study_document:'作业与课件读取',study_course_search:'课程与大纲查询',study_remember:'学习档案更新',study_navigate:'页面导航',study_finish:'回答与引用核对'};
const examples = ['核对本周未完成的作业，结合截止时间和课表帮我安排完成计划。','帮我分析一份待完成作业，告诉我先复习哪些课件页码和录播内容。','结合我的历史修读记录、专业培养方案和未来方向，给我后续选课建议。'];

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  let timer, busy = false, profileDirty = false;
  const cleanup = () => {clearTimeout(timer);removeStyle();};
  context.signal.addEventListener('abort',cleanup,{once:true});
  let history, profile, ai;
  try { [history,profile,ai] = await Promise.all([context.api('/chat'),context.api('/profile'),context.services.ai.settings()]); }
  catch (error) {cleanup();throw error;}
  if (context.signal.aborted) return cleanup;
  container.classList.add('academic-chat');
  container.innerHTML = `<div class="study-intro"><div><h3>一起处理今天的学习安排</h3><p>查询作业与课表、定位课件原文，或结合培养方案讨论接下来的选课。</p></div><button class="text-button" data-clear-chat type="button">清空对话</button></div><div class="study-layout"><section class="study-conversation" aria-label="与学习助手对话"><div class="study-messages" data-messages role="log" aria-label="聊天记录" aria-live="polite" tabindex="0"></div><div class="study-progress" data-progress hidden role="status" aria-live="polite"><p data-progress-text></p><ol data-steps></ol></div><div class="study-examples">${examples.map((text,index) => `<button class="button button-secondary" data-example="${index}" type="button">${['规划作业','准备复习','讨论选课'][index]}</button>`).join('')}</div><form data-chat-form><label for="study-message">你想先处理什么？</label><textarea id="study-message" name="message" rows="3" maxlength="8000" placeholder="例如：这周有哪些作业还没完成？帮我留出复习和完成作业的时间。" required></textarea><p class="study-error danger-text" data-error role="alert"></p><div class="study-send"><span class="field-hint">Ctrl + Enter 发送，Enter 换行</span><button class="button button-primary" type="submit" ${ai.enabled && ai.key_saved ? '' : 'disabled'}>发送</button></div><p class="field-hint">助手按问题读取所需资料，并发送至已配置的 DeepSeek 服务。${ai.enabled && ai.key_saved ? '' : '请先在设置中配置并启用统一 AI 服务。'}</p></form></section><aside class="study-profile"><details><summary>我的学习档案</summary><p class="field-hint">保存在本机，供连续学习建议使用；可随时编辑。</p><form data-profile-form><fieldset><label>专业<input name="major" maxlength="120"></label><label>入学年份<input name="cohort_year" type="number" min="2000" max="2100" placeholder="例如 2025"></label><label>未来方向<input name="direction" maxlength="1200" placeholder="例如机器人、芯片设计或继续深造"></label><label>每周可用学习时间（小时）<input name="weekly_hours" type="number" min="0" max="168" step="0.5"></label><label>补充偏好<textarea name="notes" rows="3" maxlength="4000" placeholder="学习节奏、关注领域或希望保留的背景"></textarea></label><div class="form-actions"><button class="button button-secondary" type="submit">保存档案</button><button class="text-button danger-text" data-clear-profile type="button">清除档案</button></div></fieldset></form><p class="field-hint" data-academic-records></p><p class="study-error danger-text" data-profile-error role="alert"></p></details><p class="field-hint">学校要求与学习建议会分别说明。资料不完整时，助手会指出需要补充的内容。</p></aside></div>`;
  const messages = container.querySelector('[data-messages]');
  const form = container.querySelector('[data-chat-form]');
  const profileForm = container.querySelector('[data-profile-form]');
  const progress = container.querySelector('[data-progress]');
  const progressText = container.querySelector('[data-progress-text]');
  const errorNode = container.querySelector('[data-error]');
  const clearChat = container.querySelector('[data-clear-chat]');

  function append(message) {
    messages.querySelector('.study-welcome')?.remove();
    const node = document.createElement('article');
    node.className = 'study-message study-' + message.role;
    const citations = message.citations || [];
    const tools = [...new Map((message.tools || []).map(tool => [tool.name,tool])).values()];
    node.innerHTML = `<header><strong>${message.role === 'user' ? '你' : '学习助手'}</strong>${message.created_at ? '<span>' + e(time(message.created_at)) + '</span>' : ''}</header><div class="study-text">${e(message.text)}</div>${citations.length ? `<details class="study-references"><summary>参考资料（${citations.length}）</summary>${citations.map(source => `<article><h4>${e(source.title)}${source.page && source.kind !== 'text' ? ' · 第 ' + source.page + ' 页' : ''}</h4><blockquote>${e(source.quote)}</blockquote><div>${source.url ? link(source.url,'打开来源',e) : ''}${source.download_url ? link(source.download_url,'下载原文件',e) : ''}</div></article>`).join('')}</details>` : ''}${tools.length ? '<p class="study-used-tools">' + tools.map(tool => e(toolNames[tool.name]) + (tool.is_error ? '：需补充资料' : '：完成')).join(' · ') + '</p>' : ''}`;
    messages.append(node);
    return node;
  }
  function empty() {
    messages.innerHTML = '<div class="study-welcome"><h4>从一件具体的事开始</h4><p>可以安排作业、先复习一道题涉及的知识，或讨论适合你的后续课程。</p></div>';
  }
  if (history.messages.length) {history.messages.forEach(append);messages.scrollTop = messages.scrollHeight;} else empty();

  function fillProfile(value) {
    if (!profileDirty) for (const name of ['major','cohort_year','direction','weekly_hours','notes']) profileForm.elements[name].value = value.profile[name] ?? '';
    container.querySelector('[data-academic-records]').textContent = [value.courses_count ? '已读取 ' + value.courses_count + ' 条历史修读记录' : '',value.academic.plan_title || '',value.academic.updated_at ? '记录更新于 ' + time(value.academic.updated_at) : '询问成绩或培养方案后，会保留本账号的学业记录。'].filter(Boolean).join(' · ');
  }
  fillProfile(profile);
  profileForm.oninput = () => {profileDirty = true;};
  async function poll() {
    try {
      const value = await context.api('/activity');
      if (context.signal.aborted || !busy) return;
      const text = value.steps.length ? '正在核对资料并整理回答…' : '正在准备学习工具并理解问题…';
      if (progressText.textContent !== text) progressText.textContent = text;
      const steps = container.querySelector('[data-steps]');
      const html = value.steps.map(step => '<li>' + e(step.label) + ' · ' + ({running:'处理中',done:'完成',error:'需补充资料'})[step.status] + '</li>').join('');
      if (steps.innerHTML !== html) steps.innerHTML = html;
    } catch (error) {
      if (!context.signal.aborted && busy) progressText.textContent = '正在等待回答，暂时无法读取查询进度。';
    }
    if (busy && !context.signal.aborted) timer = setTimeout(poll,1500);
  }
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy || !ai.enabled || !ai.key_saved || !form.reportValidity()) return;
    const message = form.elements.message.value.trim();
    if (!message) return;
    busy = true;
    errorNode.textContent = '';
    form.querySelector('button').disabled = true;
    form.elements.message.disabled = true;
    profileForm.querySelector('fieldset').disabled = true;
    clearChat.disabled = true;
    form.setAttribute('aria-busy','true');
    progress.hidden = false;
    progressText.textContent = '正在准备学习工具并理解问题…';
    container.querySelector('[data-steps]').replaceChildren();
    const pending = append({role:'user',text:message});
    messages.scrollTop = messages.scrollHeight;
    timer = setTimeout(poll,500);
    try {
      const answer = await context.api('/chat',{method:'POST',body:{message}});
      if (context.signal.aborted) return;
      const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
      append(answer);
      if (nearBottom) messages.scrollTop = pending.offsetTop;
      form.elements.message.value = '';
      if (answer.navigation) context.navigate(answer.navigation);
      else context.api('/profile').then(current => {if (!context.signal.aborted) fillProfile(current);}).catch(error => {if (!context.signal.aborted) container.querySelector('[data-profile-error]').textContent = error.message;});
    } catch (error) {
      if (context.signal.aborted) return;
      pending.remove();
      if (!messages.children.length) empty();
      errorNode.textContent = error.message;
    } finally {
      busy = false;
      clearTimeout(timer);
      progress.hidden = true;
      form.querySelector('button').disabled = false;
      form.elements.message.disabled = false;
      profileForm.querySelector('fieldset').disabled = false;
      clearChat.disabled = false;
      form.removeAttribute('aria-busy');
      if (!context.signal.aborted) form.elements.message.focus();
    }
  };
  form.elements.message.addEventListener('keydown',event => {if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {event.preventDefault();form.requestSubmit();}},{signal:context.signal});
  container.querySelectorAll('[data-example]').forEach(button => {button.onclick = () => {if (!busy) {form.elements.message.value = [form.elements.message.value,examples[Number(button.dataset.example)]].filter(Boolean).join('\n');form.elements.message.focus();}};});
  clearChat.onclick = context.ui.safeAction(clearChat,async () => {
    if (!await context.ui.confirmDialog('清空学习对话','清空当前账号的学习助手聊天记录。学习档案继续保留。','清空对话')) return;
    await context.api('/chat',{method:'DELETE'});empty();
  });
  profileForm.onsubmit = context.ui.safeAction(profileForm.querySelector('[type=submit]'),async () => {
    const fields = new FormData(profileForm);
    const value = Object.fromEntries(fields);
    value.cohort_year = value.cohort_year ? Number(value.cohort_year) : null;
    value.weekly_hours = value.weekly_hours ? Number(value.weekly_hours) : null;
    container.querySelector('[data-profile-error]').textContent = '';
    try {const result = await context.api('/profile',{method:'PUT',body:value});profileDirty = false;fillProfile(result);context.ui.toast('学习档案已保存。');}
    catch (error) {if (!context.signal.aborted) container.querySelector('[data-profile-error]').textContent = error.message;}
  });
  const clearProfile = container.querySelector('[data-clear-profile]');
  clearProfile.onclick = context.ui.safeAction(clearProfile,async () => {
    if (!await context.ui.confirmDialog('清除学习档案','清除当前学校账号的个人偏好与助手保存的学业记录。','清除档案')) return;
    const result = await context.api('/profile',{method:'DELETE'});profileDirty = false;fillProfile(result);
  });
  return cleanup;
}
