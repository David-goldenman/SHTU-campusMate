import {sourcePanel, link, time} from '/assets/campus.js';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('mail-view');
  let selected, bucket = 'all', query = '', busy = false;
  const dispose = await sourcePanel(container, context, async body => {
    let state = await context.api('/intelligence');
    body.innerHTML = '<div class="campus-toolbar mail-toolbar"><input data-search type="search" aria-label="搜索邮件" placeholder="搜索主题、发件人或摘要"><button class="button button-secondary" data-preferences type="button">筛选偏好</button><button class="button button-secondary" data-batch type="button">复核最近邮件</button><span data-progress role="status"></span></div><div class="mail-filters" data-filters aria-label="邮件筛选"></div><div class="mail-columns"><div class="mail-inbox" data-messages aria-label="邮件列表"></div><section class="mail-reader" data-reader aria-label="邮件正文"></section></div>';
    const search = body.querySelector('[data-search]'); search.value = query;
    const filtered = () => state.messages.filter(item => (bucket === 'all' || item.classification.bucket === bucket) && [item.title,item.sender,item.classification.summary].join(' ').toLowerCase().includes(query.toLowerCase()));
    const refresh = async () => { state = await context.api('/intelligence'); if (!context.signal.aborted) draw(); };
    function draw() {
      body.querySelector('[data-filters]').innerHTML = Object.entries({all:'全部',...state.buckets}).map(([id,title]) => `<button type="button" data-bucket="${id}" aria-pressed="${bucket === id}">${e(title)} <span>${state.messages.filter(item => id === 'all' || item.classification.bucket === id).length}</span></button>`).join('');
      body.querySelectorAll('[data-bucket]').forEach(button => button.onclick = () => {bucket = button.dataset.bucket; draw();});
      const items = filtered();
      body.querySelector('[data-messages]').innerHTML = items.map(item => `<button type="button" class="mail-row ${selected === item.id ? 'selected' : ''}" data-message="${e(item.id)}" aria-pressed="${selected === item.id}"><span class="mail-row-meta">${e(item.sender)} · ${e(time(item.received_at))}</span><strong>${item.unread ? '<span aria-label="未读">● </span>' : ''}${e(item.title)}</strong><span class="mail-row-summary">${e(item.classification.summary || item.classification.reason)}</span><span class="mail-tag">${e(item.classification.category)}${item.classification.by === 'manual' ? ' · 手动' : item.classification.by === 'agent' ? ' · AI' : ''}</span></button>`).join('') || '<p class="field-hint mail-empty">当前筛选没有邮件。筛选仅影响工作台显示。</p>';
      body.querySelectorAll('[data-message]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {selected = button.dataset.message; draw(); await read();}));
    }
    async function read() {
      const item = state.messages.find(item => item.id === selected);
      const reader = body.querySelector('[data-reader]');
      if (!item) {reader.innerHTML = '<div class="mail-empty"><h3>阅读校园邮件</h3><p>选择一封邮件，在这里查看正文和分类依据。</p><p class="field-hint">偏好用于初筛，AI 会按原文复核；已筛选的邮件仍保留在原邮箱。</p></div>';return;}
      const identity = item.id;
      reader.innerHTML = '<p class="mail-empty" role="status">正在读取邮件…</p>';
      const detail = await context.api('/message?message_id=' + encodeURIComponent(identity));
      if (selected !== identity || context.signal.aborted) return;
      const c = item.classification;
      reader.innerHTML = `<header class="mail-reader-header"><h3>${e(item.title)}</h3><p>${e(item.sender)}</p><p class="field-hint">${e(time(item.received_at))} · ${link(item.url,'在原邮箱查看',e)}</p><div class="campus-toolbar"><button type="button" class="button button-secondary" data-review ${busy ? 'disabled' : ''}>AI 复核这封邮件</button><button type="button" class="text-button" data-label>调整分类</button></div></header><details class="mail-decision" ${c.summary ? 'open' : ''}><summary>${e(state.buckets[c.bucket])} · ${e(c.category)}${c.needs_check ? ' · 需核对' : ''}</summary>${c.summary ? `<p>${e(c.summary)}</p>` : ''}<p class="field-hint">${e(c.reason)}</p>${(c.evidence || []).map(source => '<blockquote>' + e(source.quote) + '</blockquote>').join('')}</details><article class="mail-body">${detail.body_html}</article><p class="field-hint mail-footer">附件和图片原件可在原邮箱查看。外部图片以说明文字显示。</p>`;
      const review = reader.querySelector('[data-review]');
      review.onclick = context.ui.safeAction(review, async () => {await context.api('/review',{method:'POST',body:{message_id:identity,force:true}});await refresh();await read();});
      reader.querySelector('[data-label]').onclick = () => {
        const form = document.createElement('form');form.className = 'campus-form';
        form.innerHTML = `<label>显示位置<select name="bucket">${Object.entries(state.buckets).map(([id,title]) => `<option value="${id}" ${c.bucket === id ? 'selected' : ''}>${e(title)}</option>`).join('')}</select></label><label>分类名称<input name="label" required maxlength="32" value="${e(c.category)}"></label><p class="field-hint">手动分类优先于自动复核。</p><button class="button button-primary">保存分类</button>`;
        const dialog = context.ui.dialog('调整邮件分类',form);
        form.onsubmit = async event => {event.preventDefault();try {await context.api('/labels',{method:'POST',body:{message_id:identity,label:form.elements.label.value,bucket:form.elements.bucket.value,by:'manual'}});dialog.close();await refresh();await read();}catch(error){if (!context.signal.aborted)context.ui.toast(error.message);}};
        context.signal.addEventListener('abort',() => dialog.close(),{once:true});
      };
    }
    search.oninput = () => {query = search.value; draw();};
    const batch = body.querySelector('[data-batch]');
    batch.onclick = context.ui.safeAction(batch, async () => {
      if (busy) return;
      const ids = filtered().filter(item => item.classification.by === 'rule').slice(0,5).map(item => item.id);
      if (!ids.length) {context.ui.toast('当前邮件已复核；可打开邮件单独重新复核。');return;}
      busy = true;
      try {for (let i = 0;i < ids.length;i++) {body.querySelector('[data-progress]').textContent = `正在复核 ${i + 1} / ${ids.length}`;await context.api('/review',{method:'POST',body:{message_id:ids[i]}});if(context.signal.aborted)return;await refresh();}await read();}
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
    draw(); await read();
  });
  return () => {dispose?.();removeStyle();};
}
