const labels = {list:'列出目录',read:'读取文件',write:'写入文件',edit:'编辑文件',mkdir:'创建文件夹'};

export async function showFileSettings(context) {
  const value=await context.api('/files/settings'), e=context.ui.escape;
  if(context.signal.aborted)return;
  const form=document.createElement('form');form.className='campus-form study-files-settings';
  form.innerHTML=`<p>学习助手可以列出目录、读取文本、创建和编辑文件。文件保存在本机，结束对话后仍保留。</p><label>Workspace<input name="workspace" value="${e(value.workspace)}" required maxlength="2000"></label><p class="field-hint">相对路径基于这个目录。更换目录不搬动原有文件。</p><label>访问方式<select name="mode"><option value="workspace" ${value.mode==='workspace'?'selected':''}>Workspace + 审批</option><option value="full" ${value.mode==='full'?'selected':''}>完全访问</option></select></label><p data-mode-note></p><p class="field-hint">文件读取内容会用于当前模型回答。修改作业、日程等工作台状态仍通过相应工具完成。</p><p class="danger-text" role="alert" data-file-error></p><button class="button button-primary" type="submit">保存访问设置</button>`;
  const dialog=context.ui.dialog('本地文件访问',form);
  context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
  const explain=()=>{form.querySelector('[data-mode-note]').textContent=form.elements.mode.value==='full'?'完全访问：助手可按你的指令、在本机账户权限内读写路径，不再逐次审批 workspace 外的操作。':'Workspace 内直接读写；访问外部路径时在聊天里显示具体操作，由你决定是否允许本次操作。';};
  form.elements.mode.onchange=explain;explain();
  form.onsubmit=context.ui.safeAction(form.querySelector('[type=submit]'),async()=>{
    if(!form.reportValidity())return;
    try {
      await context.api('/files/settings',{method:'PUT',body:{mode:form.elements.mode.value,workspace:form.elements.workspace.value,account_revision:value.account_revision,expected_revision:value.revision}});
      dialog.close();context.ui.toast('文件访问设置已保存');
    } catch(error) {if(!context.signal.aborted)form.querySelector('[data-file-error]').textContent=error.message;}
  });
}

export function renderApprovals(host, requests, context) {
  const e=context.ui.escape, ids=new Set(requests.map(item=>item.id));
  host.querySelectorAll('[data-file-approval]').forEach(item=>{if(!ids.has(item.dataset.fileApproval))item.remove();});
  for(const request of requests) {
    if([...host.children].some(item=>item.dataset.fileApproval===request.id))continue;
    const card=document.createElement('section');card.className='study-file-approval';card.dataset.fileApproval=request.id;
    card.innerHTML=`<strong>需要你的文件访问审批</strong><p>${e(labels[request.action])}</p><code>${e(request.path)}</code><p class="field-hint">路径在 workspace 外，仅批准这一次操作；拒绝或超时后不会执行。</p>${request.content!=null?'<details open><summary>待写入内容</summary><pre>'+e(request.content)+'</pre></details>':''}${request.old_text!=null?'<details open><summary>替换原文 → 新内容</summary><pre>'+e(request.old_text)+'</pre><pre>'+e(request.new_text)+'</pre></details>':''}<div class="form-actions"><button type="button" class="button button-primary" data-allow>允许本次操作</button><button type="button" class="button button-secondary" data-deny>拒绝</button></div>`;
    host.append(card);
    card.querySelectorAll('button').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{
      await context.api('/files/approvals/'+encodeURIComponent(request.id),{method:'POST',body:{allow:button.hasAttribute('data-allow'),account_revision:request.account_revision}});
      card.querySelectorAll('button').forEach(control=>{control.disabled=true;});
    }));
  }
}
