import {sourcePanel, link, time} from '/assets/campus.js';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('mail-view');
  let selected = new URLSearchParams(location.hash.split('?')[1] || '').get('message'), bucket = selected ? 'all' : 'focus', query = '', busy = false;
  let view = 'messages', readVersion = 0, anchor = new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
  const dispose = await sourcePanel(container, context, async body => {
    let state = await context.api('/intelligence');
    body.innerHTML = '<div class="campus-toolbar mail-toolbar"><input data-search type="search" aria-label="搜索邮件" placeholder="搜索当前文件夹的主题、发件人或摘要"><button class="button button-secondary" data-preferences type="button">分类偏好</button><button class="text-button" data-batch type="button">AI 复核</button><a class="button button-secondary" href="https://mail.shanghaitech.edu.cn/coremail/" target="_blank" rel="noopener noreferrer">打开学校邮箱 ↗</a><span data-progress role="status"></span></div><div class="mail-columns"><nav class="mail-folders" aria-label="邮件文件夹"><h3>邮箱</h3><div data-inbox-folders></div><h3>智能文件夹</h3><div data-filters></div><h3>总结</h3><button class="mail-folder" type="button" data-digest="day">日总结</button><button class="mail-folder" type="button" data-digest="week">周总结</button><p class="mail-folder-hint">本地分类<br>原邮件保留在学校邮箱</p></nav><section class="mail-inbox" aria-label="邮件列表"><header class="mail-list-heading"><h3 data-folder-title>收件箱</h3><span data-folder-count></span></header><div data-messages></div></section><section class="mail-reader" data-reader aria-label="邮件阅读区"></section></div>';
    const search = body.querySelector('[data-search]'); search.value = query;
    const filtered = () => state.messages.filter(item => (bucket === 'all' || bucket === 'unread' && item.unread === true || item.classification.bucket === bucket) && [item.title,item.sender,item.classification.summary].join(' ').toLowerCase().includes(query.toLowerCase()));
    const refresh = async () => { state = await context.api('/intelligence'); if (!context.signal.aborted) draw(); };
    function draw() {
      const folderButtons = entries => Object.entries(entries).map(([id,title]) => `<button class="mail-folder" type="button" data-bucket="${id}" aria-pressed="${view === 'messages' && bucket === id}"><span>${e(title)}</span><span class="mail-folder-count">${state.messages.filter(item => id === 'all' || id === 'unread' && item.unread === true || item.classification.bucket === id).length}</span></button>`).join('');
      body.querySelector('[data-inbox-folders]').innerHTML = folderButtons({all:'收件箱',unread:'未读邮件'});
      body.querySelector('[data-filters]').innerHTML = folderButtons(state.buckets);
      body.querySelectorAll('[data-bucket]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {view='messages';bucket = button.dataset.bucket;selected=undefined;body.querySelector('.mail-columns').classList.remove('mail-reading');draw();await read();}));
      body.querySelectorAll('[data-digest]').forEach(button => button.setAttribute('aria-pressed',String(view === button.dataset.digest)));
      const items = filtered();
      body.querySelector('[data-folder-title]').textContent = ({all:'收件箱',unread:'未读邮件',...state.buckets})[bucket];
      body.querySelector('[data-folder-count]').textContent = `${items.length} 封`;
      body.querySelector('[data-messages]').innerHTML = items.map(item => `<button type="button" class="mail-row ${selected === item.id ? 'selected' : ''}" data-message="${e(item.id)}" aria-pressed="${selected === item.id}"><span class="mail-row-meta"><span>${e(item.sender)}</span><time>${e(time(item.received_at))}</time></span><strong>${item.unread ? '<span class="mail-unread" aria-label="未读">● </span>' : ''}${e(item.title)}</strong><span class="mail-row-summary">${e(item.classification.summary || '打开查看邮件正文')}</span><span class="mail-tag">${e(item.classification.category)}${item.classification.by === 'manual' ? ' · 手动' : item.classification.by === 'agent' ? ' · AI' : ' · 初筛'}</span></button>`).join('') || '<p class="field-hint mail-empty">此文件夹暂无邮件。</p>';
      body.querySelectorAll('[data-message]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {view='messages';selected = button.dataset.message;body.querySelector('.mail-columns').classList.add('mail-reading');draw(); await read();}));
    }
    async function read() {
      const version = ++readVersion;
      if (view !== 'messages') {await showDigest(view);return;}
      const item = state.messages.find(item => item.id === selected);
      const reader = body.querySelector('[data-reader]');
      if (!item) {reader.innerHTML = `<div class="mail-empty"><h3>选择一封邮件开始阅读</h3><p>收件箱 ${state.messages.length} 封，其中 ${state.messages.filter(item=>item.classification.bucket==='focus').length} 封重点关注。</p><p class="field-hint">左侧可切换分类文件夹，或查看日总结与周总结。</p></div>`;return;}
      const identity = item.id;
      reader.innerHTML = '<p class="mail-empty" role="status">正在读取邮件…</p>';
      let detail;
      try {detail = await context.api('/message?message_id=' + encodeURIComponent(identity));}
      catch(error) {
        if (version !== readVersion || context.signal.aborted) return;
        reader.innerHTML = `<div class="mail-empty" role="alert"><h3>邮件暂时无法读取</h3><p>${e(error.message)}</p><button type="button" class="button button-secondary" data-retry-mail>重试</button></div>`;
        reader.querySelector('[data-retry-mail]').onclick = context.ui.safeAction(reader.querySelector('[data-retry-mail]'),read);return;
      }
      if (selected !== identity || version !== readVersion || context.signal.aborted) return;
      const c = item.classification;
      reader.innerHTML = `<button class="text-button mail-back" data-mail-back type="button">← 返回邮件列表</button><header class="mail-reader-header"><span class="mail-reader-tag">${e(state.buckets[c.bucket])} · ${e(c.category)}${c.needs_check ? ' · 需核对' : ''}</span><h3>${e(item.title)}</h3><dl class="mail-envelope"><dt>发件人</dt><dd>${e(item.sender)}</dd><dt>收件时间</dt><dd>${e(time(item.received_at))}</dd></dl><div class="campus-toolbar"><button type="button" class="text-button" data-review ${busy ? 'disabled' : ''}>AI 复核</button><button type="button" class="text-button" data-label>调整分类</button>${link(item.url,'打开学校邮箱 ↗',e)}</div></header>${c.summary ? `<section class="mail-summary"><h4>内容摘要</h4><p>${e(c.summary)}</p></section>` : ''}<details class="mail-decision"><summary>分类依据</summary><p>${e(c.reason)}</p>${(c.evidence || []).map(source => '<blockquote>' + e(source.quote) + '</blockquote>').join('')}</details><article class="mail-body">${detail.body_html}</article><p class="field-hint mail-footer">附件、原图及完整原件请在学校邮箱查看。</p>`;
      reader.querySelector('[data-mail-back]').onclick = () => body.querySelector('.mail-columns').classList.remove('mail-reading');
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
      reader.innerHTML = '<p class="mail-empty" role="status">' + (generate ? '正在生成邮件总结…' : '正在读取邮件总结…') + '</p>';
      let result;
      try {result = await context.api('/digests' + (generate ? '' : `?period=${period}&anchor=${anchor}`),generate ? {method:'POST',body:{period,anchor},timeoutMs:180000} : {});}
      catch(error) {
        if (version === readVersion && !context.signal.aborted) {reader.innerHTML = `<div class="mail-empty" role="alert"><p>${e(error.message)}</p><button type="button" class="button button-secondary" data-retry-digest>重新读取</button></div>`;reader.querySelector('[data-retry-digest]').onclick = context.ui.safeAction(reader.querySelector('[data-retry-digest]'),() => showDigest(period));}return;
      }
      if (version !== readVersion || context.signal.aborted) return;
      const report = result.report, byId = new Map(result.entries.map(item=>[item.id,item]));
      reader.innerHTML = `<header class="mail-reader-header"><h3>${period === 'day' ? '日总结' : '周总结'}</h3><div class="mail-digest-controls"><label>选择日期<input type="date" data-digest-anchor value="${anchor}"></label><button type="button" class="button button-primary" data-generate-digest ${result.entries.length ? '' : 'disabled'}>${report ? '重新生成 AI 总结' : '生成 AI 总结'}</button></div><p class="field-hint">${e(result.start)}${result.end !== result.start ? ' 至 ' + e(result.end) : ''} · 已同步 ${result.coverage.included_count} 封${report ? ' · 生成于 ' + e(time(report.generated_at)) : ''}</p></header><div class="mail-digest-counts">${Object.entries(state.buckets).map(([id,name])=>`<span>${e(name)} <strong>${result.counts[id]}</strong></span>`).join('')}</div>${report ? `<section class="mail-digest-overview"><h4>本期总结</h4><p>${e(report.overview)}</p></section><section><h4>重点事项</h4>${report.highlights.map(item=>digestItem(byId.get(item.message_id),item.summary)).join('') || '<p class="field-hint">本期没有额外的重点事项。</p>'}</section>` : '<p class="field-hint">可以先浏览下方分类结果；生成 AI 总结时会将本期标题、分类和已有摘要发送至设置中选择的模型服务。</p>'}<details class="mail-digest-sources" ${report ? '' : 'open'}><summary>本期邮件 · ${result.entries.length} 封</summary>${result.entries.map(item=>digestItem(item,item.summary || '尚无正文摘要，打开邮件查看。')).join('') || '<p class="mail-empty">这段时间没有已同步邮件。</p>'}</details><p class="field-hint mail-footer">范围为本机已同步的最近 ${result.coverage.cached_count} 封收件箱邮件${result.coverage.inbox_total != null ? '，学校收件箱共 ' + result.coverage.inbox_total + ' 封' : ''}；需要更多历史邮件时请打开学校邮箱。</p>`;
      reader.querySelector('[data-digest-anchor]').onchange = event => {if(event.target.value){anchor=event.target.value;void showDigest(period);}};
      reader.querySelector('[data-generate-digest]').onclick = context.ui.safeAction(reader.querySelector('[data-generate-digest]'),() => showDigest(period,true));
      reader.querySelectorAll('[data-digest-message]').forEach(button => {button.onclick = context.ui.safeAction(button,async () => {view='messages';bucket='all';selected=button.dataset.digestMessage;draw();await read();});});
    }
    function digestItem(item, summary) {
      return `<button type="button" class="mail-digest-item" data-digest-message="${e(item.id)}"><span class="mail-tag">${e(state.buckets[item.bucket])} · ${e(item.category)}</span><strong>${e(item.title)}</strong><span>${e(summary)}</span></button>`;
    }
    body.querySelectorAll('[data-digest]').forEach(button => {button.onclick = context.ui.safeAction(button,async () => {view=button.dataset.digest;body.querySelector('.mail-columns').classList.add('mail-reading');draw();await showDigest(view);});});
    search.oninput = () => {query = search.value; draw();};
    const batch = body.querySelector('[data-batch]');
    batch.onclick = context.ui.safeAction(batch, async () => {
      if (busy) return;
      const ids = filtered().filter(item => item.classification.by === 'rule').slice(0,5).map(item => item.id);
      if (!ids.length) {context.ui.toast('当前邮件已复核；可打开邮件单独重新复核。');return;}
      busy = true;
      try {for (let i = 0;i < ids.length;i++) {body.querySelector('[data-progress]').textContent = `正在复核 ${i + 1} / ${ids.length}`;await context.api('/review',{method:'POST',body:{message_id:ids[i]},timeoutMs:600000});if(context.signal.aborted)return;await refresh();}await read();}
      finally {busy = false;body.querySelector('[data-progress]').textContent = '';}
    });
    body.querySelector('[data-preferences]').onclick = () => {
      const p = state.preferences, form = document.createElement('form');form.className = 'campus-form mail-preferences';
      const options = (values,value) => Object.entries(values).map(([id,title]) => `<option value="${id}" ${id === value ? 'selected' : ''}>${e(title)}</option>`).join('');
      const completion = {unknown:'尚未填写',required:'仍需完成',done:'已经完成',na:'不适用'};
      form.innerHTML = `<div class="mail-profile-grid"><label>学段<select name="degree">${options({bachelor:'本科',master:'硕士',phd:'博士'},p.degree)}</select></label><label>当前年级<input name="year" type="number" min="1" max="8" value="${p.year || ''}" placeholder="如 2"></label><label>专业<input name="major" maxlength="120" value="${e(p.major)}"></label><label>在修课程名称或代码<input name="courses" value="${e(p.courses.join('，'))}" placeholder="用逗号分隔"></label><label>形策要求<select name="shape">${options(completion,p.shape)}</select></label><label>心理健康要求<select name="mental">${options(completion,p.mental)}</select></label>${Object.entries(state.interests).map(([id,title]) => `<label>${e(title)}<select name="interest_${id}">${options({follow:'优先推荐',digest:'保留摘要',hide:'筛选收起'},p.interests[id] || 'digest')}</select></label>`).join('')}</div><label>补充你的筛选要求<textarea name="requirements" rows="5" maxlength="5000" placeholder="例如：关注集成电路相关讲座；已经完成的考勤只保留摘要。">${e(p.requirements)}</textarea></label><p class="field-hint">AI 复核时会读取完整要求和所选邮件正文。偏好只保存在当前账号的本地数据中。</p><button class="button button-primary">保存偏好</button>`;
      const dialog = context.ui.dialog('邮件筛选偏好',form);
      form.onsubmit = async event => {event.preventDefault();const f = form.elements;try {await context.api('/preferences',{method:'PUT',body:{degree:f.degree.value,year:f.year.value ? Number(f.year.value) : null,major:f.major.value,courses:f.courses.value.split(/[,，\n]/).map(v => v.trim()).filter(Boolean),shape:f.shape.value,mental:f.mental.value,requirements:f.requirements.value,interests:Object.fromEntries(Object.keys(state.interests).map(id => [id,f['interest_' + id].value]))}});dialog.close();await refresh();await read();}catch(error){if (!context.signal.aborted)context.ui.toast(error.message);}};
      context.signal.addEventListener('abort',() => dialog.close(),{once:true});
    };
    if (selected) body.querySelector('.mail-columns').classList.add('mail-reading');
    draw(); await read();
  });
  return () => {dispose?.();removeStyle();};
}
