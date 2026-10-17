import {link, time} from '/assets/campus.js';
import {renderMarkdown} from '/assets/markdown.js';
import {sendOnEnter, fitComposer} from './composer.js';

const icons = {
  history:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16m4-10h4m-4 4h4"/>',
  new:'<path d="M12 5v14M5 12h14"/>',
  send:'<path d="m6 12 6-6 6 6M12 6v13"/>',
  stop:'<rect x="7" y="7" width="10" height="10" rx="1" fill="currentColor" stroke="none"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  prompts:'<path d="M8 4h8a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Zm1 5h6m-6 4h6"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const card = container.closest('.module-card');
  const title = card.querySelector('.module-card-heading');
  let busy = false, profileDirty = false, currentRequest, frame, observer, follow = true;
  const cleanup = () => {currentRequest?.abort();cancelAnimationFrame(frame);observer?.disconnect();context.focus(false);removeStyle();card.classList.remove('study-chat-card');title.hidden=false;};
  context.signal.addEventListener('abort',cleanup,{once:true});
  let history, profile, ai, presets, conversations;
  try { [history,profile,ai,presets,conversations] = await Promise.all([context.api('/chat'),context.api('/profile'),context.services.ai.settings(),context.api('/presets'),context.api('/conversations')]); }
  catch (error) {cleanup();throw error;}
  if (context.signal.aborted) return cleanup;
  const configured = ai.enabled && ai.key_saved;
  let activeId = history.conversation_id, archived = false, showArchived = false;
  const drafts = new Map();
  container.classList.add('academic-chat');
  card.classList.add('study-chat-card');
  title.hidden = true;
  container.innerHTML = `
    <header class="study-header"><div class="study-heading"><button class="study-icon-button" data-history-toggle type="button" aria-label="历史对话" title="历史对话" aria-expanded="false">${icon('history')}</button><div><h2 data-chat-title>学习助手</h2><a class="study-model" href="#settings?tab=ai" aria-label="AI 设置，当前模型 ${e(ai.model)}">${e(ai.model)} <span aria-hidden="true">⌄</span></a></div></div>
      <div class="study-actions"><button class="text-button study-home" data-home type="button">校园概览</button><button class="study-new-button" data-new-chat type="button">${icon('new')}<span>新对话</span></button><details class="study-menu"><summary class="study-icon-button" aria-label="对话操作" title="对话操作">${icon('more')}</summary><div><button class="text-button" data-profile-toggle type="button" aria-expanded="false">学习档案</button><button class="text-button danger-text" data-clear-chat type="button">删除当前对话</button></div></details></div>
    </header>
    <div class="study-layout"><aside class="study-history" aria-label="历史对话" hidden><div class="study-profile-heading"><h3>历史对话</h3><button class="study-icon-button" data-history-close type="button" aria-label="关闭历史对话">${icon('close')}</button></div><input type="search" data-history-search aria-label="搜索对话" placeholder="搜索对话"><div class="study-history-tabs"><button class="text-button" data-history-filter="active" type="button">进行中</button><button class="text-button" data-history-filter="archived" type="button">已归档</button></div><div data-conversations></div></aside><section class="study-conversation" aria-label="与学习助手对话">
      <div class="study-scroll"><div class="study-messages" data-messages role="log" aria-label="聊天记录" aria-live="off" tabindex="0"></div><button class="button button-secondary study-latest" data-latest type="button" hidden>回到最新回复 ↓</button></div>
      <div class="study-composer"><details class="study-progress" data-progress hidden><summary><span class="spinner" aria-hidden="true"></span><span data-progress-text role="status"></span></summary><ol data-steps></ol></details>
        <form data-chat-form><label class="visually-hidden" for="study-message">发消息</label>
          <textarea id="study-message" name="message" rows="2" maxlength="8000" placeholder="给学习助手发消息…" aria-describedby="study-send-hint" required></textarea>
          <div class="study-error-row"><p class="study-error danger-text" data-error role="alert"></p><button class="text-button" data-retry type="button" hidden>重新发送</button></div><div class="study-send"><details class="study-prompts"><summary>${icon('prompts')}<span>常用问题</span></summary><div>${presets.items.map((item,index) => `<button class="text-button" data-example="${index}" type="button">${e(item.label)}</button>`).join('')}</div></details><span class="field-hint" id="study-send-hint">Enter 发送 · Shift + Enter 换行</span><button class="study-send-button" data-stop type="button" aria-label="停止生成" title="停止生成" hidden>${icon('stop')}</button><button class="study-send-button" data-send type="submit" aria-label="发送" title="发送（Enter）" disabled>${icon('send')}</button></div>
        </form><div class="study-starters">${presets.items.map((item,index) => `<button type="button" data-example="${index}">${e(item.label)}<span aria-hidden="true">↗</span></button>`).join('')}</div><p class="study-privacy">${configured ? '所需学习资料将发送至 DeepSeek' : '<a href="#settings?tab=ai">配置并启用 AI 后开始对话 →</a>'}</p>
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
  const historyPanel = container.querySelector('.study-history');
  const historyToggle = container.querySelector('[data-history-toggle]');
  const newChat = container.querySelector('[data-new-chat]');
  const conversation = container.querySelector('.study-conversation');
  const input = form.elements.message;
  const retry = container.querySelector('[data-retry]');
  const search = container.querySelector('[data-history-search]');
  function resizeInput() {fitComposer(input);send.disabled=!configured||archived||!input.value.trim();}
  input.addEventListener('input',resizeInput,{signal:context.signal});
  search.addEventListener('input',drawConversations,{signal:context.signal});
  retry.onclick = () => form.requestSubmit();
  function focusChat(active) {context.focus(active);const home=container.querySelector('[data-home]');home.setAttribute('aria-pressed',String(!active));home.textContent=active?'校园概览':'返回对话';}
  container.querySelector('[data-home]').onclick = event => focusChat(event.currentTarget.getAttribute('aria-pressed') === 'true');
  function showHistory(open) {historyPanel.hidden=!open;historyToggle.setAttribute('aria-expanded',String(open));if(open) {focusChat(true);showProfile(false);}}
  historyToggle.onclick = context.ui.safeAction(historyToggle,async () => {showHistory(historyPanel.hidden);if(!historyPanel.hidden) await refreshConversations();});
  container.querySelector('[data-history-close]').onclick = () => {showHistory(false);historyToggle.focus();};
  container.querySelectorAll('[data-history-filter]').forEach(button => button.onclick=()=>{showArchived=button.dataset.historyFilter==='archived';drawConversations();});
  async function refreshConversations() {conversations=await context.api('/conversations');if (!context.signal.aborted) drawConversations();}
  async function openConversation(identity) {
    if (busy) return;
    drafts.set(activeId || '',form.elements.message.value);
    const value=await context.api('/conversations/'+identity+'/select',{method:'POST'});
    if (context.signal.aborted) return;
    activeId=identity;archived=value.conversation.archived;messages.replaceChildren();
    if(value.messages.length)value.messages.forEach(append);else empty();
    form.elements.message.value=drafts.get(identity)||'';resizeInput();retry.hidden=true;
    errorNode.textContent=archived?'这段对话已归档。恢复后可以继续提问。':'';
    focusChat(true);scrollToLatest();drawConversations();showHistory(false);
  }
  function drawConversations() {
    const selected=conversations.items.find(item=>item.id===activeId);
    container.querySelector('[data-chat-title]').textContent=selected?.title && selected.title!=='新对话' ? selected.title : '学习助手';
    container.querySelectorAll('[data-history-filter]').forEach(button=>button.setAttribute('aria-pressed',String((button.dataset.historyFilter==='archived')===showArchived)));
    const query=search.value.trim().toLocaleLowerCase();
    container.querySelector('[data-conversations]').innerHTML=conversations.items.filter(item=>item.archived===showArchived&&item.title.toLocaleLowerCase().includes(query)).sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))).map(item=>`<article class="study-history-item ${item.id===activeId?'selected':''}"><button class="text-button" data-open-chat="${e(item.id)}" type="button" ${item.id===activeId?'aria-current="true"':''} ${busy?'disabled':''}><strong>${e(item.title)}</strong><span>${e(time(item.updated_at))}</span></button><details class="study-menu study-history-menu"><summary class="study-icon-button" aria-label="管理对话：${e(item.title)}">${icon('more')}</summary><div><button class="text-button" data-archive-chat="${e(item.id)}" type="button" ${busy?'disabled':''}>${item.archived?'恢复':'归档'}</button><button class="text-button danger-text" data-delete-chat="${e(item.id)}" type="button" ${busy?'disabled':''}>删除</button></div></details></article>`).join('')||`<p class="field-hint">${query?'没有找到匹配的对话。':'这里暂时没有对话。'}</p>`;
    container.querySelectorAll('[data-open-chat]').forEach(button=>button.onclick=context.ui.safeAction(button,()=>openConversation(button.dataset.openChat)));
    container.querySelectorAll('[data-archive-chat]').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{
      const item=conversations.items.find(item=>item.id===button.dataset.archiveChat);
      await context.api('/conversations/'+item.id,{method:'PUT',body:{archived:!item.archived}});await refreshConversations();
      if(item.id===activeId){archived=!item.archived;resizeInput();errorNode.textContent=archived?'这段对话已归档。恢复后可以继续提问。':'';}
    }));
    container.querySelectorAll('[data-delete-chat]').forEach(button=>button.onclick=context.ui.safeAction(button,()=>deleteConversation(button.dataset.deleteChat)));
  }
  async function deleteConversation(identity) {
    if (!await context.ui.confirmDialog('删除对话','删除这段对话及其本地消息，学习档案继续保留。','删除对话')) return;
    await context.api('/conversations/'+identity,{method:'DELETE'});drafts.delete(identity);await refreshConversations();
    if(activeId===identity){form.elements.message.value='';const next=conversations.active_id;activeId=null;if(next)await openConversation(next);else{archived=false;empty();resizeInput();focusChat(true);}}
  }
  newChat.onclick=context.ui.safeAction(newChat,async()=>{if(busy)return;const item=await context.api('/conversations',{method:'POST'});await refreshConversations();await openConversation(item.id);form.elements.message.focus({preventScroll:true});});
  observer = new ResizeObserver(() => {container.style.setProperty('--study-top',Math.max(0,card.getBoundingClientRect().top + window.scrollY) + 'px');resizeInput();});
  observer.observe(card.parentElement);
  function showProfile(open) {
    if(open){showHistory(false);container.querySelector('.study-menu').open=false;}
    container.querySelector('.study-profile').hidden = !open;
    profileToggle.setAttribute('aria-expanded',String(open));
    if (open) profileForm.elements.major.focus();
  }
  profileToggle.onclick = () => showProfile(profileToggle.getAttribute('aria-expanded') !== 'true');
  container.querySelector('[data-profile-close]').onclick = () => {showProfile(false);profileToggle.focus();};
  container.addEventListener('keydown',event => {if(event.key!=='Escape')return;if(profileToggle.getAttribute('aria-expanded')==='true'){showProfile(false);profileToggle.focus();}else if(!historyPanel.hidden){showHistory(false);historyToggle.focus();}},{signal:context.signal});
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
    conversation.classList.remove('is-empty');
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
    conversation.classList.add('is-empty');
    messages.innerHTML = '<div class="study-welcome"><div><span class="study-welcome-mark" aria-hidden="true">✧</span><h3>今天，想一起解决什么？</h3></div><p>聊作业、复习和选课，让每个问题都有据可依。</p></div>';
  }
  if (history.messages.length) {history.messages.forEach(append);scrollToLatest();} else empty();
  archived=conversations.items.find(item=>item.id===activeId)?.archived || false;
  resizeInput();drawConversations();focusChat(true);
  function fillProfile(value) {
    if (!profileDirty) for (const name of ['major','cohort_year','direction','weekly_hours','notes']) profileForm.elements[name].value = value.profile[name] ?? '';
    container.querySelector('[data-academic-records]').textContent = [value.academic.plan_title || '',value.academic.updated_at ? '记录更新于 ' + time(value.academic.updated_at) : '查询培养方案后会显示方案来源。'].filter(Boolean).join(' · ');
  }
  fillProfile(profile);
  profileForm.oninput = () => {profileDirty = true;};
  stop.onclick = () => {stop.disabled = true;currentRequest?.abort();};
  form.onsubmit = async event => {
    event.preventDefault();
    if (busy || archived || !configured || !form.reportValidity()) return;
    const message = form.elements.message.value.trim();
    if (!message) return;
    busy = true;retry.hidden=true;newChat.disabled=true;showHistory(false);drawConversations();focusChat(true);errorNode.textContent = '';send.hidden = true;stop.hidden = false;stop.disabled = false;
    form.elements.message.disabled = true;profileForm.querySelector('fieldset').disabled = true;clearChat.disabled = true;profileToggle.disabled = true;showProfile(false);
    container.querySelector('.study-prompts').open = false;form.setAttribute('aria-busy','true');
    progress.hidden = false;progress.open = false;progressText.textContent = '正在准备学习工具…';container.querySelector('[data-steps]').replaceChildren();
    const pending = append({role:'user',text:message});
    let draft = append({role:'assistant',text:''}), text = '', answer;
    draft.querySelector('.study-text').before(progress);
    draft.classList.add('study-streaming');scrollToLatest();
    currentRequest = new AbortController();
    function paint() {
      frame = null;if (context.signal.aborted) return;
      renderBody(draft.querySelector('.study-text'),text);
      if (follow) scrollToLatest();else latest.hidden = false;
    }
    try {
      if(!activeId)activeId=(await context.api('/conversations',{method:'POST'})).id;
      await context.api('/chat/stream',{method:'POST',body:{message,conversation_id:activeId},signal:currentRequest.signal,onEvent(value) {
        if (context.signal.aborted) return;
        if (value.type === 'error') throw new Error(value.detail);
        if (value.type === 'activity') {
          const steps = value.steps;
          progressText.textContent = steps.length ? steps.at(-1).label + (steps.at(-1).status === 'running' ? '…' : ' · 已完成') : '正在准备学习工具…';
          container.querySelector('[data-steps]').innerHTML = steps.map(step => '<li>' + e(step.label) + '<span>' + ({running:'处理中',done:'完成',error:'需补充资料'})[step.status] + '</span></li>').join('');
        }
        if (value.type === 'reset') {text='';if (!frame) frame=requestAnimationFrame(paint);}
        if (value.type === 'delta') {text+=value.text;if (progressText.textContent !== '正在撰写回答…') progressText.textContent='正在撰写回答…';if (!frame) frame=requestAnimationFrame(paint);}
        if (value.type === 'complete') answer = value.message;
      }});
      if (context.signal.aborted) return;
      if (!answer) throw new Error('回复连接中断，请重试。');
      cancelAnimationFrame(frame);frame=null;
      draft.remove();draft = append(answer);
      if (follow) scrollToLatest();else latest.hidden = false;
      form.elements.message.value = '';
      resizeInput();
      refreshConversations().catch(error=>context.ui.toast(error.message));
      container.querySelector('[data-announcement]').textContent = '回答已完成，参考资料可在回答下方展开。';
      if (answer.navigation) context.navigate(answer.navigation);
      else context.api('/profile').then(current => {if (!context.signal.aborted) fillProfile(current);}).catch(error => {if (!context.signal.aborted) container.querySelector('[data-profile-error]').textContent=error.message;});
    } catch (error) {
      if (context.signal.aborted) return;
      cancelAnimationFrame(frame);frame=null;draft.remove();pending.remove();
      if (!messages.children.length) empty();
      errorNode.textContent = error.name === 'AbortError' ? '已停止生成，问题保留在输入框中。' : error.message;
      retry.hidden=error.name==='AbortError';
    } finally {
      busy = false;newChat.disabled=false;drawConversations();currentRequest=null;progress.hidden=true;stop.hidden=true;send.hidden=false;
      form.elements.message.disabled=false;profileForm.querySelector('fieldset').disabled=false;clearChat.disabled=false;profileToggle.disabled=false;form.removeAttribute('aria-busy');
      container.querySelector('.study-composer').prepend(progress);resizeInput();
      if (!context.signal.aborted && [document.body,stop,form.elements.message].includes(document.activeElement)) form.elements.message.focus({preventScroll:true});
    }
  };
  form.elements.message.addEventListener('keydown',event => sendOnEnter(event,form),{signal:context.signal});
  container.querySelectorAll('[data-example]').forEach(button => {button.onclick = () => {if (!busy) {form.elements.message.value=[form.elements.message.value,presets.items[Number(button.dataset.example)].prompt].filter(Boolean).join('\n');resizeInput();container.querySelector('.study-prompts').open=false;form.elements.message.focus({preventScroll:true});}};});
  clearChat.onclick = context.ui.safeAction(clearChat,async () => {
    if(activeId)await deleteConversation(activeId);latest.hidden=true;container.querySelector('.study-menu').open=false;
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
