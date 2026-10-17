import {time} from '/assets/campus.js';

const kinds = {assignment:'作业进度',reminder:'提醒',plan:'学习计划'};
const statuses = {todo:'待办',in_progress:'进行中',done:'已完成',cancelled:'已取消'};

export function changeCards(changes, escape) {
  const actions = {create:'新增',update:'修改',delete:'删除',set_assignment:'更新作业进度',adjust_class:'课程调整'};
  return changes.filter(value=>value.applied).map(value=>{
    const item=value.after || value.before || {};
    const detail=value.domain==='workspace' ? statuses[item.status] || '' : ({leave:'请假',cancel:'停课',move:'调课',restore:'恢复原安排'})[item.action] || '';
    const describe=record=>record ? [statuses[record.status],record.to_date || record.date || record.on_date,record.period_start?'第 '+record.period_start+'–'+record.period_end+' 节':'',record.starts_at || record.at || record.due_at ? time(record.starts_at || record.at || record.due_at) : '',record.location].filter(Boolean).join(' · ') : '已移除';
    return `<div class="study-change"><strong>已保存：${escape(actions[value.action] || value.action)} · ${escape(item.title || '')}</strong><span>${escape(detail)}${value.affected_count>1 ? ' · '+value.affected_count+' 次' : ''} · 本地记录</span>${value.before?'<span>原：'+escape(describe(value.before))+'</span>':''}<span>现：${escape(describe(value.after))}</span>${value.conflicts?.items.length ? '<span>存在 '+value.conflicts.items.length+' 处时间冲突，请查看时间表。</span>' : ''}${value.conflicts && !value.conflicts.complete ? '<span>部分来源或时间不完整，冲突检查有限。</span>' : ''}</div>`;
  }).join('');
}

export async function showWorkspace(context) {
  const e=context.ui.escape, value=await context.api('/work');
  if(context.signal.aborted)return;
  const body=document.createElement('div');body.className='study-workspace';
  const dialog=context.ui.dialog('学习事务',body);
  context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
  let state=value;
  async function refresh() {state=await context.api('/work');if(!context.signal.aborted)draw();}
  async function change(item,action,patch={}) {
    await context.api('/work/commands',{method:'POST',body:{action,record_id:item.id,expected_revision:item.revision,account_revision:state.account_revision,request_id:crypto.randomUUID(),item:patch}});
    await refresh();
  }
  function draw() {
    body.innerHTML=`<p class="field-hint">本地作业进度不代表原站提交。${e(state.reminder_delivery)}</p><div class="form-actions"><button type="button" class="button button-secondary" data-new="reminder">新增提醒</button><button type="button" class="button button-secondary" data-new="plan">新增计划</button></div><div class="study-work-items">${state.items.length ? state.items.map((item,index)=>`<article><header><strong>${e(item.title)}</strong><span>${kinds[item.kind]} · ${statuses[item.status]}</span></header>${item.due_at?'<p>'+e(time(item.due_at))+'</p>':''}${item.delivered_at?'<p>已发送到通知中心</p>':''}${item.delivery_error?'<p>'+e(item.delivery_error)+'</p>':''}<p class="study-work-notes">${e(item.notes)}</p><button type="button" class="text-button" data-edit="${index}">编辑</button><button type="button" class="text-button danger-text" data-delete="${index}">删除本地记录</button></article>`).join(''):'<p>还没有学习事务。可以在这里添加提醒和计划，或通过主页对话标记作业进度。</p>'}</div><details><summary>最近操作记录</summary>${changeCards(state.changes.slice().reverse(),e) || '<p>暂无修改。</p>'}</details>`;
    body.querySelectorAll('[data-new]').forEach(button=>button.onclick=()=>edit({kind:button.dataset.new,status:'todo',title:'',notes:''}));
    body.querySelectorAll('[data-edit]').forEach(button=>button.onclick=()=>edit(state.items[Number(button.dataset.edit)]));
    body.querySelectorAll('[data-delete]').forEach(button=>button.onclick=context.ui.safeAction(button,async()=>{
      const item=state.items[Number(button.dataset.delete)];
      if(await context.ui.confirmDialog('删除本地记录','删除“'+item.title+'”？','删除'))await change(item,'delete');
    }));
  }
  function edit(item) {
    const form=document.createElement('form');form.className='campus-form';
    const requestId=crypto.randomUUID(), owner=state.account_revision;
    const local=item.due_at ? new Date(new Date(item.due_at).getTime()+8*3600000).toISOString().slice(0,16) : '';
    form.innerHTML=`<label>名称<input name="title" required maxlength="120" value="${e(item.title)}" ${item.kind==='assignment'?'readonly':''}></label><label>状态<select name="status">${Object.entries(statuses).map(([key,label])=>`<option value="${key}" ${key===item.status?'selected':''}>${label}</option>`).join('')}</select></label>${item.kind!=='assignment'?`<label>${item.kind==='reminder'?'提醒时间':'目标时间（可选）'} · 北京时间<input type="datetime-local" name="due_at" value="${local}" ${item.kind==='reminder'?'required':''}></label>`:''}<label>内容／备注<textarea name="notes" rows="7" maxlength="12000">${e(item.notes)}</textarea></label><p data-error class="danger-text" role="alert"></p><button type="submit" class="button button-primary">保存</button>`;
    const editor=context.ui.dialog(kinds[item.kind],form);
    context.signal.addEventListener('abort',()=>editor.close(),{once:true});
    form.onsubmit=context.ui.safeAction(form.querySelector('[type=submit]'),async()=>{
      if(!form.reportValidity())return;
      const fields=Object.fromEntries(new FormData(form));
      if('due_at' in fields)fields.due_at=fields.due_at?fields.due_at+':00+08:00':null;
      try {
        if(item.kind==='assignment') {
          await context.api('/work/commands',{method:'POST',body:{action:'set_assignment',record_id:item.assignment_id,expected_revision:item.revision,account_revision:owner,request_id:requestId,item:{status:fields.status,notes:fields.notes}}});
          await refresh();
        } else if(item.id) {
          await context.api('/work/commands',{method:'POST',body:{action:'update',record_id:item.id,expected_revision:item.revision,account_revision:owner,request_id:requestId,item:fields}});
          await refresh();
        }
        else {
          await context.api('/work/commands',{method:'POST',body:{action:'create',account_revision:owner,request_id:requestId,item:{...fields,kind:item.kind}}});
          await refresh();
        }
        editor.close();
      } catch(error) {if(!context.signal.aborted)form.querySelector('[data-error]').textContent=error.message;}
    });
  }
  draw();
}
