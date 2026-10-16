import {link, time} from '/assets/campus.js';
import {renderMarkdown} from '/assets/markdown.js';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const card = container.closest('.module-card');
  let busy = false, profileDirty = false, currentRequest, frame, follow = true;
  const cleanup = () => {currentRequest?.abort();cancelAnimationFrame(frame);removeStyle();card.classList.remove('study-chat-card');};
  context.signal.addEventListener('abort',cleanup,{once:true});
  let history, profile, ai, presets;
  try { [history,profile,ai,presets] = await Promise.all([context.api('/chat'),context.api('/profile'),context.services.ai.settings(),context.api('/presets')]); }
  catch (error) {cleanup();throw error;}
  if (context.signal.aborted) return cleanup;
  const configured = ai.enabled && ai.key_saved;
  container.classList.add('academic-chat');
  card.classList.add('study-chat-card');
  container.innerHTML = `
    <header class="study-header"><div><h2>学习助手</h2><a class="study-model" href="#settings?tab=ai" aria-label="AI 设置，当前模型 ${e(ai.model)}">${e(ai.model)}<span> · AI 设置</span></a></div>
      <div class="study-actions"><button class="text-button" data-profile-toggle type="button" aria-expanded="false">学习档案</button><details class="study-menu"><summary aria-label="对话操作">更多</summary><div><button class="text-button danger-text" data-clear-chat type="button">清空对话</button></div></details></div>
    </header>
    <div class="study-layout"><section class="study-conversation" aria-label="与学习助手对话">
      <div class="study-scroll"><div class="study-messages" data-messages role="log" aria-label="聊天记录" aria-live="off" tabindex="0"></div><button class="button button-secondary study-latest" data-latest type="button" hidden>回到最新回复 ↓</button></div>
      <div class="study-composer"><details class="study-progress" data-progress hidden><summary><span class="spinner" aria-hidden="true"></span><span data-progress-text role="status"></span></summary><ol data-steps></ol></details>
        <form data-chat-form><div class="study-composer-heading"><label for="study-message">发消息</label><details class="study-prompts"><summary>常用问题</summary><div>${presets.items.map((item,index) => `<button class="text-button" data-example="${index}" type="button">${e(item.label)}</button>`).join('')}</div></details></div>
          <textarea id="study-message" name="message" rows="2" maxlength="8000" placeholder="问作业、复习或选课，也可以接着追问…" aria-describedby="study-send-hint" required></textarea>
          <p class="study-error danger-text" data-error role="alert"></p><div class="study-send"><span class="field-hint" id="study-send-hint">Ctrl + Enter 发送 · Enter 换行</span><button class="button button-secondary" data-stop type="button" hidden>停止生成</button><button class="button button-primary" data-send type="submit" ${configured ? '' : 'disabled'}>发送</button></div>
        </form><p class="study-privacy">${configured ? '按问题读取所需学习资料，发送至 DeepSeek。' : '<a href="#settings?tab=ai">配置并启用 AI 后开始对话 →</a>'}</p>
      </div>
    </section>
    <aside class="study-profile" aria-label="我的学习档案" hidden><div class="study-profile-heading"><h3>学习档案</h3><button class="text-button" data-profile-close type="button">返回对话</button></div><p class="field-hint">保存在本机，供连续学习建议使用。</p><form data-profile-form><fieldset><label>专业<input name="major" maxlength="120"></label><label>入学年份<input name="cohort_year" type="number" min="2000" max="2100" placeholder="例如 2025"></label><label>未来方向<input name="direction" maxlength="1200" placeholder="例如机器人、芯片设计或继续深造"></label><label>每周可用学习时间（小时）<input name="weekly_hours" type="number" min="0" max="168" step="0.5"></label><label>补充偏好<textarea name="notes" rows="3" maxlength="4000" placeholder="学习节奏、关注领域或希望保留的背景"></textarea></label><div class="form-actions"><button class="button button-secondary" type="submit">保存档案</button><button class="text-button danger-text" data-clear-profile type="button">清除档案</button></div></fieldset></form><p class="field-hint" data-academic-records></p><p class="study-error danger-text" data-profile-error role="alert"></p></aside></div><span class="visually-hidden" data-announcement role="status"></span>`;
  const messages = container.querySelector('[data-messages]');
  const form = container.querySelector('[data-chat-form]');
  const profileForm = container.querySelector('[data-profile-form]');
  const progress = container.querySelector('[data-progress]');
  const progressText = container.querySelector('[data-progress-text]');
  const errorNode = container.querySelector('[data-error]');
  const clearChat = container.querySelector('[data-clear-chat]');
  const send = container.querySelector('[data-send]'), stop = container.querySelector('[data-stop]');
  const profileToggle = container.querySelector('[data-profile-toggle]');
  const latest = container.querySelector('[data-latest]');
  function showProfile(open) {
    container.querySelector('.study-profile').hidden = !open;
    profileToggle.setAttribute('aria-expanded',String(open));
    if (open) profileForm.elements.major.focus();
  }
  profileToggle.onclick = () => showProfile(profileToggle.getAttribute('aria-expanded') !== 'true');
  container.querySelector('[data-profile-close]').onclick = () => {showProfile(false);profileToggle.focus();};
  container.addEventListener('keydown',event => {if (event.key === 'Escape' && profileToggle.getAttribute('aria-expanded') === 'true') {showProfile(false);profileToggle.focus();}},{signal:context.signal});
  function scrollToLatest() {messages.scrollTop = messages.scrollHeight;follow = true;latest.hidden = true;}
  messages.addEventListener('scroll',() => {follow = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;latest.hidden = follow;},{signal:context.signal});
  latest.onclick = scrollToLatest;

  function references(citations) {
    const groups = new Map();
    citations.forEach((source,index) => {
      const key = JSON.stringify([source.record_id || source.download_url || source.url || source.source_id,source.title]);
      if (!groups.has(key)) groups.set(key,{...source,quotes:[]});
      groups.get(key).quotes.push({...source,index:index + 1});
    });
    return citations.length ? `<details class="study-references"><summary>参考资料 <span>${groups.size} 份 · ${citations.length} 处引文</span></summary><div class="study-reference-list">${[...groups.values()].map(source => `<article><h4>${e(source.title)}</h4>${source.quotes.map(quote => `<div class="study-quote-label">[${quote.index}]${quote.page && quote.kind !== 'text' ? ' · 第 ' + quote.page + ' 页' : ''}</div><blockquote>${e(quote.quote)}</blockquote>`).join('')}<div class="study-source-links">${source.url ? link(source.url,'打开来源 ↗',e) : ''}${source.download_url ? link(source.download_url,'下载原文件',e) : ''}</div></article>`).join('')}</div></details>` : '';
  }
  function renderBody(node, text, settled = false) {
    node.innerHTML = renderMarkdown(text);
    node.querySelectorAll('table').forEach(table => {const wrapper=document.createElement('div');wrapper.className='study-table';wrapper.tabIndex=0;wrapper.setAttribute('aria-label','表格，可横向滚动');table.replaceWith(wrapper);wrapper.append(table);});
    if (settled) node.querySelectorAll('pre').forEach(pre => {
      const button = document.createElement('button');button.type='button';button.className='text-button study-copy-code';button.textContent='复制代码';
      const text = pre.textContent;
      button.onclick = context.ui.safeAction(button,async () => {await navigator.clipboard.writeText(text);context.ui.toast('代码已复制。');});
      pre.before(button);
    });
  }
  function append(message) {
    messages.querySelector('.study-welcome')?.remove();
    const node = document.createElement('article');
    node.className = 'study-message study-' + message.role;
    node.innerHTML = `<header><strong>${message.role === 'user' ? '你' : '学习助手'}</strong>${message.created_at ? '<span>' + e(time(message.created_at)) + '</span>' : ''}</header><div class="study-text"></div>${references(message.citations || [])}`;
    const body = node.querySelector('.study-text');
    if (message.role === 'user') body.textContent = message.text;
    else {
      body.classList.add('study-markdown');renderBody(body,message.text || '',!!message.created_at || !!message.model);
      if (message.model) {
        const footer = document.createElement('footer');footer.className='study-message-footer';
        footer.innerHTML = '<span>' + e(message.model) + '</span><button class="text-button" type="button">复制回答</button>';
        const copy = footer.querySelector('button');copy.onclick = context.ui.safeAction(copy,async () => {await navigator.clipboard.writeText(message.text);context.ui.toast('回答已复制。');});node.append(footer);
      }
    }
    messages.append(node);return node;
  }
  function empty() {
    messages.innerHTML = '<div class="study-welcome"><span class="study-welcome-mark" aria-hidden="true">✧</span><h3>今天，先处理哪件学习任务？</h3><p>问问近期作业，梳理复习重点，或一起讨论后续选课。</p><p class="field-hint">描述具体问题，助手会按需查阅资料，并附上原文与页码。</p></div>';
  }
  if (history.messages.length) {history.messages.forEach(append);scrollToLatest();} else empty();
  function fillProfile(value) {
    if (!profileDirty) for (const name of ['major','cohort_year','direction','weekly_hours','notes']) profileForm.elements[name].value = value.profile[name] ?? '';
    container.querySelector('[data-academic-records]').textContent = [value.academic.plan_title || '',value.academic.updated_at ? '记录更新于 ' + time(value.academic.updated_at) : '查询培养方案后会显示方案来源。'].filter(Boolean).join(' · ');
  }
  fillProfile(profile);
  profileForm.oninput = () => {profileDirty = true;};
  stop.onclick = () => {stop.disabled = true;currentRequest?.abort();};
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy || !configured || !form.reportValidity()) return;
    const message = form.elements.message.value.trim();
    if (!message) return;
    busy = true;errorNode.textContent = '';send.hidden = true;stop.hidden = false;stop.disabled = false;
    form.elements.message.disabled = true;profileForm.querySelector('fieldset').disabled = true;clearChat.disabled = true;profileToggle.disabled = true;showProfile(false);
    container.querySelector('.study-prompts').open = false;form.setAttribute('aria-busy','true');
    progress.hidden = false;progress.open = false;progressText.textContent = '正在准备学习工具…';container.querySelector('[data-steps]').replaceChildren();
    const pending = append({role:'user',text:message});
    let draft = append({role:'assistant',text:''}), text = '', answer;
    draft.classList.add('study-streaming');scrollToLatest();
    currentRequest = new AbortController();
    function paint() {
      frame = null;if (context.signal.aborted) return;
      renderBody(draft.querySelector('.study-text'),text);
      if (follow) scrollToLatest();else latest.hidden = false;
    }
    try {
      await context.api('/chat/stream',{method:'POST',body:{message},signal:currentRequest.signal,onEvent(value) {
        if (context.signal.aborted) return;
        if (value.type === 'error') throw new Error(value.detail);
        if (value.type === 'activity') {
          const steps = value.steps;
          progressText.textContent = steps.length ? steps.at(-1).label + (steps.at(-1).status === 'running' ? '…' : ' · 已完成') : '正在准备学习工具…';
          container.querySelector('[data-steps]').innerHTML = steps.map(step => '<li>' + e(step.label) + '<span>' + ({running:'处理中',done:'完成',error:'需补充资料'})[step.status] + '</span></li>').join('');
        }
        if (value.type === 'reset') {text='';if (!frame) frame=requestAnimationFrame(paint);}
        if (value.type === 'delta') {text+=value.text;progressText.textContent='正在撰写回答…';if (!frame) frame=requestAnimationFrame(paint);}
        if (value.type === 'complete') answer = value.message;
      }});
      if (context.signal.aborted) return;
      if (!answer) throw new Error('回复连接中断，请重试。');
      cancelAnimationFrame(frame);frame=null;
      draft.remove();draft = append(answer);
      if (follow) scrollToLatest();else latest.hidden = false;
      form.elements.message.value = '';
      container.querySelector('[data-announcement]').textContent = '回答已完成，参考资料可在回答下方展开。';
      if (answer.navigation) context.navigate(answer.navigation);
      else context.api('/profile').then(current => {if (!context.signal.aborted) fillProfile(current);}).catch(error => {if (!context.signal.aborted) container.querySelector('[data-profile-error]').textContent=error.message;});
    } catch (error) {
      if (context.signal.aborted) return;
      cancelAnimationFrame(frame);frame=null;draft.remove();pending.remove();
      if (!messages.children.length) empty();
      errorNode.textContent = error.name === 'AbortError' ? '已停止生成，问题保留在输入框中。' : error.message;
    } finally {
      busy = false;currentRequest=null;progress.hidden=true;stop.hidden=true;send.hidden=false;
      form.elements.message.disabled=false;profileForm.querySelector('fieldset').disabled=false;clearChat.disabled=false;profileToggle.disabled=false;form.removeAttribute('aria-busy');
      if (!context.signal.aborted && [document.body,stop,form.elements.message].includes(document.activeElement)) form.elements.message.focus({preventScroll:true});
    }
  };
  form.elements.message.addEventListener('keydown',event => {if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.isComposing) {event.preventDefault();form.requestSubmit();}},{signal:context.signal});
  container.querySelectorAll('[data-example]').forEach(button => {button.onclick = () => {if (!busy) {form.elements.message.value=[form.elements.message.value,presets.items[Number(button.dataset.example)].prompt].filter(Boolean).join('\n');container.querySelector('.study-prompts').open=false;form.elements.message.focus({preventScroll:true});}};});
  clearChat.onclick = context.ui.safeAction(clearChat,async () => {
    if (!await context.ui.confirmDialog('清空学习对话','清空当前账号的学习助手聊天记录。学习档案继续保留。','清空对话')) return;
    await context.api('/chat',{method:'DELETE'});empty();latest.hidden=true;container.querySelector('.study-menu').open=false;
  });
  profileForm.onsubmit = context.ui.safeAction(profileForm.querySelector('[type=submit]'),async () => {
    const value = Object.fromEntries(new FormData(profileForm));value.cohort_year=value.cohort_year ? Number(value.cohort_year) : null;value.weekly_hours=value.weekly_hours ? Number(value.weekly_hours) : null;
    container.querySelector('[data-profile-error]').textContent='';
    try {const result=await context.api('/profile',{method:'PUT',body:value});profileDirty=false;fillProfile(result);context.ui.toast('学习档案已保存。');}
    catch (error) {if (!context.signal.aborted) container.querySelector('[data-profile-error]').textContent=error.message;}
  });
  const clearProfile = container.querySelector('[data-clear-profile]');
  clearProfile.onclick = context.ui.safeAction(clearProfile,async () => {
    if (!await context.ui.confirmDialog('清除学习档案','清除当前学校账号的个人偏好与助手保存的学业记录。','清除档案')) return;
    const result=await context.api('/profile',{method:'DELETE'});profileDirty=false;fillProfile(result);
  });
  return cleanup;
}
