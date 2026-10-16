import {sourcePanel, link, time} from '/assets/campus.js';

export function mount(container, context) {
  const e = context.ui.escape;
  return sourcePanel(container, context, async (body, snapshot) => {
    const labels = (await context.api('/labels')).labels;
    let rules = (await context.api('/rules')).rules;
    body.innerHTML = '<div class="campus-toolbar"><input data-search aria-label="搜索邮件" placeholder="搜索主题或发件人"><button type="button" class="button button-secondary" data-classify>执行规则</button><button type="button" class="button button-secondary" data-ai>AI 分类当前列表</button><button type="button" class="text-button" data-agent>Agent 接口</button></div><p class="field-hint">AI 分类最多选择当前列表 25 封邮件，并将主题、发件人与已缓存正文发送至设置中的 DeepSeek 服务。</p><details><summary>分类规则</summary><div data-rules></div><form data-rule class="campus-toolbar"><select name="field" aria-label="匹配字段"><option value="title">主题</option><option value="sender">发件人</option><option value="body_text">已缓存正文</option></select><input name="contains" required maxlength="1000" placeholder="关键词，用英文逗号分隔" aria-label="关键词"><input name="label" required maxlength="32" placeholder="分类名称" aria-label="分类名称"><button class="button button-secondary">添加规则</button></form></details><div class="campus-list" data-messages></div><section class="campus-detail" data-detail aria-live="polite"></section>';
    const search = body.querySelector('[data-search]');
    const visible = () => snapshot.data.messages.filter(item => (item.title + ' ' + item.sender).toLowerCase().includes(search.value.toLowerCase()));
    const draw = () => {
      body.querySelector('[data-messages]').innerHTML = visible().map(item => `<article class="campus-item"><h4>${e(item.title)} ${item.unread ? '· 未读' : ''}</h4><p class="field-hint">${e(item.sender)} · ${e(time(item.received_at))} · ${e(labels[item.id]?.label || '待分类')}</p><button class="text-button" type="button" data-read="${e(item.id)}">阅读正文</button> <button class="text-button" type="button" data-label="${e(item.id)}">手动分类</button> ${link(item.url, '原邮箱', e)}</article>`).join('') || '<p class="field-hint">没有符合条件的邮件，请连接账号并同步。</p>';
      body.querySelectorAll('[data-read]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {
        const detail = await context.api('/message?message_id=' + encodeURIComponent(button.dataset.read));
        body.querySelector('[data-detail]').innerHTML = '<article class="campus-item"><h3>邮件正文</h3><div>' + detail.body_html + '</div><p class="field-hint">附件请在原邮箱中查看。</p></article>';
      }));
      body.querySelectorAll('[data-label]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {
        const label = window.prompt('邮件分类名称（最多 32 字）', labels[button.dataset.label]?.label || '');
        if (!label?.trim()) return;
        await context.api('/labels', {method:'POST', body:{message_id:button.dataset.label,label:label.trim(),by:'manual'}});
        labels[button.dataset.label] = {label:label.trim(),by:'manual'};
        draw();
      }));
    };
    const drawRules = () => {
      body.querySelector('[data-rules]').innerHTML = rules.map((rule,index) => `<p>${e({title:'主题',sender:'发件人',body_text:'正文'}[rule.field])} · ${e(rule.contains)} → ${e(rule.label)} <button type="button" class="text-button" data-remove="${index}">删除</button></p>`).join('');
      body.querySelectorAll('[data-remove]').forEach(button => button.onclick = context.ui.safeAction(button, async () => {
        rules = rules.filter((_,index) => index !== Number(button.dataset.remove));
        await context.api('/rules', {method:'PUT',body:{rules}}); drawRules();
      }));
    };
    search.oninput = draw;
    body.querySelector('[data-rule]').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const rule = {id:crypto.randomUUID(),field:form.elements.field.value,contains:form.elements.contains.value,label:form.elements.label.value,enabled:true};
      try { await context.api('/rules',{method:'PUT',body:{rules:[...rules,rule]}}); rules.push(rule); form.reset(); drawRules(); }
      catch (error) { if (!context.signal.aborted) context.ui.toast(error.message); }
    };
    const classify = body.querySelector('[data-classify]');
    classify.onclick = context.ui.safeAction(classify,async () => { await context.api('/classify',{method:'POST'}); Object.assign(labels,(await context.api('/labels')).labels); draw(); });
    const ai = body.querySelector('[data-ai]');
    ai.onclick = context.ui.safeAction(ai,async () => {
      const message_ids = visible().slice(0,25).map(item => item.id);
      if (!message_ids.length) return;
      await context.api('/ai-classify',{method:'POST',body:{message_ids}}); Object.assign(labels,(await context.api('/labels')).labels); draw();
    });
    const agent = body.querySelector('[data-agent]');
    agent.onclick = context.ui.safeAction(agent,async () => {
      const {token} = await context.api('/agent/token',{method:'POST'});
      const content = document.createElement('pre');
      content.style.whiteSpace = 'pre-wrap';
      content.textContent = 'Bearer ' + token + '\n\nGET ' + location.origin + '/api/v1/modules/mail/agent/pending\nPOST ' + location.origin + '/api/v1/modules/mail/labels\n生成新令牌后旧令牌失效。';
      context.ui.dialog('邮件 Agent 接口',content);
    });
    drawRules(); draw();
  });
}
