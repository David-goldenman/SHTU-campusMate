import {sourcePanel, link, time} from '/assets/campus.js';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('mail-view');
  context.ui.bindMenus(container,context.signal);
  let selected = new URLSearchParams(location.hash.split('?')[1] || '').get('message'), bucket = selected ? 'all' : 'focus', query = '', busy = false;
  let view = 'messages', readVersion = 0, anchor = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
  let reviewTimer, contentVersion = 0;
  context.signal.addEventListener('abort',()=>clearTimeout(reviewTimer),{once:true});
  const dispose = await sourcePanel(container, context, async body => {
    clearTimeout(reviewTimer);
    const version = ++contentVersion;
    let state = await context.api('/intelligence');
    const back = '<button class="text-button mail-back" data-mail-back type="button">← 返回邮件列表</button>';
    body.innerHTML = `<div class="mail-toolbar"><input data-search type="search" aria-label="搜索当前文件夹" placeholder="搜索邮件主题、发件人或摘要"><button class="button button-secondary" data-preferences type="button">分类偏好</button><details class="mail-options" data-action-menu><summary>更多操作</summary><div><button class="text-button" data-batch type="button">AI 复核最近邮件</button><a href="https://mail.shanghaitech.edu.cn/coremail/" target="_blank" rel="noopener noreferrer">打开学校邮箱</a></div></details><span data-progress role="status"></span></div>
      <div class="mail-columns"><nav class="mail-folders" aria-label="邮件文件夹"><h3>智能分类</h3><div data-filters></div><h3>邮箱</h3><div data-inbox-folders></div><h3>邮件总结</h3><button class="mail-folder" type="button" data-digest="day">日总结</button><button class="mail-folder" type="button" data-digest="week">周总结</button><a class="mail-official" href="https://mail.shanghaitech.edu.cn/coremail/" target="_blank" rel="noopener noreferrer">学校邮箱 ↗</a></nav>
      <section class="mail-inbox" aria-label="邮件列表"><header class="mail-list-heading"><div><h3 data-folder-title>重点关注</h3><p data-folder-description></p></div><span data-folder-count></span></header><div class="mail-table-heading" aria-hidden="true"><span></span><span>发件人</span><span>主题与摘要</span><span>分类</span><span>日期</span></div><div data-messages></div></section><section class="mail-reader" data-reader aria-label="邮件阅读区"></section></div>`;
    const search = body.querySelector('[data-search]'); search.value = query;
    const filtered = () => state.messages.filter(item => (bucket === 'all' || bucket === 'unread' && item.unread === true || item.classification.bucket === bucket) && [item.title,item.sender,item.classification.summary].join(' ').toLowerCase().includes(query.toLowerCase()));
    const refresh = async () => { state = await context.api('/intelligence'); if (!context.signal.aborted && version === contentVersion) {draw();scheduleReview();} };
    function scheduleReview() {
      clearTimeout(reviewTimer);
      if (busy) return;
      const pending=state.messages.filter(item=>item.classification.review_pending).length, status=state.review_status || {};
      body.querySelector('[data-progress]').textContent=pending ? status.available===false ? `${pending} 封待复核 · 请启用后台助手` : status.enabled===false ? `${pending} 封待复核 · 后台助手已暂停` : status.error ? 'AI 复核稍后重试，已应用当前规则' : `AI 待复核 ${pending} 封` : '';
      if (!pending || status.available===false || status.enabled===false) return;
      reviewTimer=setTimeout(async()=>{
        if(context.signal.aborted || version!==contentVersion)return;
        if(busy){scheduleReview();return;}
        const before=JSON.stringify(state.messages.find(item=>item.id===selected)?.classification);
        try {await refresh();if(view==='messages' && selected && before!==JSON.stringify(state.messages.find(item=>item.id===selected)?.classification))await read(false);}
        catch(error){if(!context.signal.aborted){body.querySelector('[data-progress]').textContent='复核进度暂时无法读取';reviewTimer=setTimeout(scheduleReview,10000);}}
      },5000);
    }
    function showList() {const previous=selected;view='messages';selected=undefined;readVersion++;body.querySelector('.mail-columns').classList.remove('mail-reading');draw();([...body.querySelectorAll('[data-message]')].find(row=>row.dataset.message===previous)||search).focus({preventScroll:true});}
    function draw() {
      const folderButtons = entries => Object.entries(entries).map(([id,title]) => `<button class="mail-folder" type="button" data-bucket="${id}" aria-pressed="${view === 'messages' && bucket === id}"><span>${e(title)}</span><span class="mail-folder-count">${state.messages.filter(item => id === 'all' || id === 'unread' && item.unread === true || item.classification.bucket === id).length}</span></button>`).join('');
      body.querySelector('[data-inbox-folders]').innerHTML = folderButtons({all:'收件箱',unread:'未读邮件'});
      body.querySelector('[data-filters]').innerHTML = folderButtons(state.buckets);
      body.querySelectorAll('[data-bucket]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {view='messages';bucket = button.dataset.bucket;selected=undefined;body.querySelector('.mail-columns').classList.remove('mail-reading');draw();await read();}));
      body.querySelectorAll('[data-digest]').forEach(button => button.setAttribute('aria-pressed',String(view === button.dataset.digest)));
      const items = filtered();
      body.querySelector('[data-folder-title]').textContent = ({all:'收件箱',unread:'未读邮件',...state.buckets})[bucket];
      body.querySelector('[data-folder-count]').textContent = `${items.length} 封`;
      body.querySelector('[data-folder-description]').textContent=({focus:'按偏好优先呈现的邮件',recommend:'感兴趣的活动与学习机会',digest:'常规通知，按需查阅',filter:'按偏好收起，原件仍保留',all:'最近同步的收件箱邮件',unread:'学校邮箱中尚未阅读的邮件'})[bucket];
      body.querySelector('[data-messages]').innerHTML = items.map(item => `<button type="button" class="mail-row ${item.unread ? 'is-unread' : ''} ${selected === item.id ? 'selected' : ''}" data-message="${e(item.id)}" aria-pressed="${selected === item.id}"><span class="mail-unread" aria-label="${item.unread ? '未读' : '已读'}">${item.unread ? '●' : ''}</span><span class="mail-sender" title="${e(item.sender)}">${e(item.sender)}</span><span class="mail-row-message"><strong>${e(item.title)}</strong><span class="mail-row-summary">${e(item.classification.summary || '')}</span></span><span class="mail-tag" title="${e(item.classification.reason)}">${e(item.classification.category)}${item.classification.by === 'manual' ? ' · 手动' : ''}</span><time title="${e(time(item.received_at))}">${e(item.received_at ? new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit'}).format(new Date(item.received_at)) : '日期待定')}</time></button>`).join('') || '<div class="mail-empty"><h3>此文件夹暂无邮件</h3><p>可以切换其他分类，或同步学校邮箱。</p></div>';
      body.querySelectorAll('[data-message]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {view='messages';selected = button.dataset.message;body.querySelector('.mail-columns').classList.add('mail-reading');draw(); await read();}));
    }
    async function read(focus = true) {
      const version = ++readVersion;
      if (view !== 'messages') {await showDigest(view);return;}
      const item = state.messages.find(item => item.id === selected);
      const reader = body.querySelector('[data-reader]');
      const scroll = reader.scrollTop;
      if (!item) {reader.innerHTML = back + `<div class="mail-empty"><h3>选择一封邮件开始阅读</h3><p>收件箱 ${state.messages.length} 封，其中 ${state.messages.filter(item=>item.classification.bucket==='focus').length} 封重点关注。</p><p class="field-hint">左侧可切换分类文件夹，或查看日总结与周总结。</p></div>`;reader.querySelector('[data-mail-back]').onclick=showList;return;}
      const identity = item.id;
      reader.innerHTML = back + '<p class="mail-empty" role="status">正在读取邮件…</p>';
      reader.querySelector('[data-mail-back]').onclick = showList;
      let detail;
      try {detail = await context.api('/message?message_id=' + encodeURIComponent(identity));}
      catch(error) {
        if (version !== readVersion || context.signal.aborted) return;
        reader.innerHTML = back + `<div class="mail-empty" role="alert"><h3>邮件暂时无法读取</h3><p>${e(error.message)}</p><button type="button" class="button button-secondary" data-retry-mail>重试</button></div>`;
        reader.querySelector('[data-mail-back]').onclick = showList;
        reader.querySelector('[data-retry-mail]').onclick = context.ui.safeAction(reader.querySelector('[data-retry-mail]'),read);return;
      }
      if (selected !== identity || version !== readVersion || context.signal.aborted) return;
      const c = item.classification;
      reader.innerHTML = `${back}<header class="mail-reader-header"><span class="mail-reader-tag">${e(state.buckets[c.bucket])} · ${e(c.category)}${c.needs_check ? ' · 需核对' : ''}</span><h3>${e(item.title)}</h3><dl class="mail-envelope"><dt>发件人</dt><dd>${e(item.sender)}</dd><dt>收件时间</dt><dd>${e(time(item.received_at))}</dd></dl><div class="campus-toolbar"><button type="button" class="text-button" data-review ${busy ? 'disabled' : ''}>AI 复核</button><button type="button" class="text-button" data-label>调整分类</button>${link(item.url,'打开学校邮箱 ↗',e)}</div></header>${c.summary ? `<section class="mail-summary"><h4>内容摘要</h4><p>${e(c.summary)}</p></section>` : ''}<details class="mail-decision"><summary>分类依据</summary><p>${e(c.reason)}</p>${(c.evidence || []).map(source => '<blockquote>' + e(source.quote) + '</blockquote>').join('')}</details><article class="mail-body">${detail.body_html}</article><p class="field-hint mail-footer">附件、原图及完整原件请在学校邮箱查看。</p>`;
      reader.querySelector('[data-mail-back]').onclick = showList;
      reader.querySelector('h3').tabIndex=-1;if(focus)reader.querySelector('h3').focus({preventScroll:true});else reader.scrollTop=scroll;
      const review = reader.querySelector('[data-review]');
      review.onclick = context.ui.safeAction(review, async () => {await context.api('/review',{method:'POST',body:{message_id:identity,force:true},timeoutMs:600000});await refresh();await read();});
      reader.querySelector('[data-label]').onclick = () => {
        const form = document.createElement('form');form.className = 'campus-form';
        form.innerHTML = `<label>显示位置<select name="bucket">${Object.entries(state.buckets).map(([id,title]) => `<option value="${id}" ${c.bucket === id ? 'selected' : ''}>${e(title)}</option>`).join('')}</select></label><label>分类名称<input name="label" required maxlength="32" value="${e(c.category)}"></label><p class="field-hint">手动分类优先于自动复核。</p><button class="button button-primary">保存分类</button>`;
        const dialog = context.ui.dialog('调整邮件分类',form);
        form.onsubmit = async event => {event.preventDefault();try {await context.api('/labels',{method:'POST',body:{message_id:identity,label:form.elements.label.value,bucket:form.elements.bucket.value,by:'manual'}});dialog.close();await refresh();await read();}catch(error){if (!context.signal.aborted)context.ui.toast(error.message);}};
        context.signal.addEventListener('abort',() => dialog.close(),{once:true});
      };
    }
    async function showDigest(period, generate = false) {
      const version = ++readVersion, reader = body.querySelector('[data-reader]');
      reader.innerHTML = back + '<p class="mail-empty" role="status">' + (generate ? '正在生成邮件总结…' : '正在读取邮件总结…') + '</p>';
      reader.querySelector('[data-mail-back]').onclick = showList;
      let result;
      try {result = await context.api('/digests' + (generate ? '' : `?period=${period}&anchor=${anchor}`),generate ? {method:'POST',body:{period,anchor},timeoutMs:180000} : {});}
      catch(error) {
        if (version === readVersion && !context.signal.aborted) {reader.innerHTML = back + `<div class="mail-empty" role="alert"><p>${e(error.message)}</p><button type="button" class="button button-secondary" data-retry-digest>重新读取</button></div>`;reader.querySelector('[data-mail-back]').onclick=showList;reader.querySelector('[data-retry-digest]').onclick = context.ui.safeAction(reader.querySelector('[data-retry-digest]'),() => showDigest(period));}return;
      }
      if (version !== readVersion || context.signal.aborted) return;
      const report = result.report, byId = new Map(result.entries.map(item=>[item.id,item]));
      reader.innerHTML = `${back}<header class="mail-reader-header"><h3>${period === 'day' ? '日总结' : '周总结'}</h3><div class="mail-digest-controls"><label>选择日期<input type="date" data-digest-anchor value="${anchor}"></label><button type="button" class="button button-primary" data-generate-digest ${result.entries.length ? '' : 'disabled'}>${report ? '重新生成 AI 总结' : '生成 AI 总结'}</button></div><p class="field-hint">${e(result.start)}${result.end !== result.start ? ' 至 ' + e(result.end) : ''} · 已同步 ${result.coverage.included_count} 封${report ? ' · 生成于 ' + e(time(report.generated_at)) : ''}</p></header><div class="mail-digest-counts">${Object.entries(state.buckets).map(([id,name])=>`<span>${e(name)} <strong>${result.counts[id]}</strong></span>`).join('')}</div>${report ? `<section class="mail-digest-overview"><h4>本期总结</h4><p>${e(report.overview)}</p></section><section><h4>重点事项</h4>${report.highlights.map(item=>digestItem(byId.get(item.message_id),item.summary)).join('') || '<p class="field-hint">本期没有额外的重点事项。</p>'}</section>` : '<p class="field-hint">可以先浏览下方分类结果；生成 AI 总结时会将本期标题、分类和已有摘要发送至设置中选择的模型服务。</p>'}<details class="mail-digest-sources" ${report ? '' : 'open'}><summary>本期邮件 · ${result.entries.length} 封</summary>${result.entries.map(item=>digestItem(item,item.summary || '尚无正文摘要，打开邮件查看。')).join('') || '<p class="mail-empty">这段时间没有已同步邮件。</p>'}</details><p class="field-hint mail-footer">范围为本机已同步的最近 ${result.coverage.cached_count} 封收件箱邮件${result.coverage.inbox_total != null ? '，学校收件箱共 ' + result.coverage.inbox_total + ' 封' : ''}；需要更多历史邮件时请打开学校邮箱。</p>`;
      reader.querySelector('[data-digest-anchor]').onchange = event => {if(event.target.value){anchor=event.target.value;void showDigest(period);}};
      reader.querySelector('[data-mail-back]').onclick=showList;
      reader.querySelector('[data-generate-digest]').onclick = context.ui.safeAction(reader.querySelector('[data-generate-digest]'),() => showDigest(period,true));
      reader.querySelectorAll('[data-digest-message]').forEach(button => {button.onclick = context.ui.safeAction(button,async () => {view='messages';bucket='all';selected=button.dataset.digestMessage;draw();await read();});});
    }
    function digestItem(item, summary) {
      return `<button type="button" class="mail-digest-item" data-digest-message="${e(item.id)}"><span class="mail-tag">${e(state.buckets[item.bucket])} · ${e(item.category)}</span><strong>${e(item.title)}</strong><span>${e(summary)}</span></button>`;
    }
    body.querySelectorAll('[data-digest]').forEach(button => {button.onclick = context.ui.safeAction(button,async () => {view=button.dataset.digest;body.querySelector('.mail-columns').classList.add('mail-reading');draw();await showDigest(view);});});
    search.oninput = () => {query = search.value;showList();search.focus({preventScroll:true});};
    const batch = body.querySelector('[data-batch]');
    batch.onclick = context.ui.safeAction(batch, async () => {
      if (busy) return;
      const ids = filtered().filter(item => item.classification.by === 'rule').slice(0,5).map(item => item.id);
      if (!ids.length) {context.ui.toast('当前邮件已复核；可打开邮件单独重新复核。');return;}
      busy = true;
      try {for (let i = 0;i < ids.length;i++) {body.querySelector('[data-progress]').textContent = `正在复核 ${i + 1} / ${ids.length}`;await context.api('/review',{method:'POST',body:{message_id:ids[i]},timeoutMs:600000});if(context.signal.aborted)return;await refresh();}await read();}
      finally {busy = false;scheduleReview();}
    });
    body.querySelector('[data-preferences]').onclick = () => {
      const p = state.preferences, form = document.createElement('form');form.className = 'campus-form mail-preferences';
      const options = (values,value) => Object.entries(values).map(([id,title]) => `<option value="${id}" ${id === value ? 'selected' : ''}>${e(title)}</option>`).join('');
      const completion = {unknown:'按年级自动关注',required:'仍需完成',done:'已经完成',na:'不适用'};
      form.innerHTML = `<div class="mail-profile-grid"><label>学段<select name="degree">${options({bachelor:'本科',master:'硕士',phd:'博士'},p.degree)}</select></label><label>当前年级<input name="year" type="number" min="1" max="8" value="${p.year || ''}" placeholder="如 2"></label><label>专业<input name="major" maxlength="120" value="${e(p.major)}"></label><label>在修课程名称或代码<input name="courses" value="${e(p.courses.join('，'))}" placeholder="用逗号分隔"></label><label>形策要求<select name="shape">${options(completion,p.shape)}</select></label><label>心理健康要求<select name="mental">${options(completion,p.mental)}</select></label>${Object.entries(state.interests).map(([id,title]) => `<label>${e(title)}<select name="interest_${id}">${options({follow:'优先推荐',digest:'保留摘要',hide:'筛选收起'},p.interests[id] || 'digest')}</select></label>`).join('')}</div><label>补充你的筛选要求<textarea name="requirements" rows="5" maxlength="5000" placeholder="例如：关注集成电路相关讲座；已经完成的考勤只保留摘要。">${e(p.requirements)}</textarea></label><p class="field-hint">AI 复核时会读取完整要求和所选邮件正文。偏好只保存在当前账号的本地数据中。</p><button class="button button-primary">保存偏好</button>`;
      const effective=state.effective_preferences || p, hint=document.createElement('p');hint.className='field-hint';
      hint.textContent=`本科一、二年级优先关注形策，本科一年级优先关注心理活动；完成状态以你的选择为准。${effective.year && !p.year ? `已从学习档案读取当前年级：${effective.year}。` : ''}课程中心已连接的在修课程自动参与分类，可在此补充课程。保存后立即更新规则，并在后台逐批复核本地邮件。`;
      form.prepend(hint);
      const dialog = context.ui.dialog('邮件筛选偏好',form);
      form.onsubmit = async event => {event.preventDefault();const f = form.elements;try {await context.api('/preferences',{method:'PUT',body:{degree:f.degree.value,year:f.year.value ? Number(f.year.value) : null,major:f.major.value,courses:f.courses.value.split(/[,，\n]/).map(v => v.trim()).filter(Boolean),shape:f.shape.value,mental:f.mental.value,requirements:f.requirements.value,interests:Object.fromEntries(Object.keys(state.interests).map(id => [id,f['interest_' + id].value]))}});dialog.close();await refresh();await read();}catch(error){if (!context.signal.aborted)context.ui.toast(error.message);}};
      context.signal.addEventListener('abort',() => dialog.close(),{once:true});
    };
    if (selected) body.querySelector('.mail-columns').classList.add('mail-reading');
    draw(); scheduleReview(); await read();
  });
  return () => {clearTimeout(reviewTimer);dispose?.();removeStyle();};
}
