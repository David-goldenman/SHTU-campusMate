import {escape} from './shared.js';

const sourceStatuses = {syncing:'正在同步',ready:'已更新',partial:'部分更新',error:'同步失败',
  login_required:'需要登录',verification_required:'等待验证',cancelled:'已取消',not_connected:'待连接'};
const workerStatuses = {running:'运行中',stopped:'已退出',idle:'已结束',cancelled:'已取消',error:'失败'};
const localTime = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '暂无';

export function renderRuntime(runtime) {
  if (!runtime) return '';
  const last=runtime.last_request,error=runtime.last_error,sources=Object.entries(runtime.sources || {});
  const failed=Boolean(error) || sources.some(([,value])=>['error','partial','login_required','verification_required'].includes(value.status));
  return `<details class="module-runtime"><summary class="${failed ? 'danger-text' : ''}">运行详情${failed ? ' · 有需检查的状态' : ''}</summary><div>
    <p>进行中请求 ${Number(runtime.active_requests || 0)} · 等待调用 ${Number(runtime.pending_calls || 0)}</p>
    <p>最近接口成功：${escape(localTime(runtime.last_success_at))}${last ? ' · 最近请求 '+Number(last.status)+' / '+Number(last.duration_ms)+' ms' : ''}</p>
    ${sources.map(([name,value])=>`<div class="source-runtime"><p>${escape(name)}：${escape(sourceStatuses[value.status] || '待检查')}</p>
      <p>最近同步成功：${escape(localTime(value.last_success_at))} · 缓存更新时间：${escape(localTime(value.cached_at))}</p>
      ${value.action ? '<p>'+escape(value.action)+'</p>' : ''}
      ${value.operation_id ? '<p>操作编号：'+escape(value.operation_id)+(value.request_id ? ' · 错误编号：'+escape(value.request_id) : '')+'</p>' : ''}</div>`).join('')}
    ${(runtime.workers || []).map(worker=>`<p>${worker.kind === 'thread' ? '后台线程' : '后台任务'} · ${escape(worker.name)}：${escape(workerStatuses[worker.status] || '待检查')}</p>`).join('')}
    ${error ? `<p class="danger-text">最近接口失败：${escape(localTime(error.at))} · HTTP ${Number(error.status)}${error.request_id ? ' · 错误编号 '+escape(error.request_id) : ''}${error.operation_id ? ' · 操作编号 '+escape(error.operation_id) : ''}</p>` : ''}
  </div></details>`;
}

export function diagnosticSummary(modules) {
  const pick=(value,keys)=>Object.fromEntries(keys.filter(key=>value?.[key] !== undefined).map(key=>[key,value[key]]));
  return JSON.stringify({generated_at:new Date().toISOString(),modules:modules.map(module=>({
    ...pick(module,['id','version','status']),
    last_request:pick(module.runtime?.last_request,['status','operation_id','component','phase','at','duration_ms']),
    http:pick(module.runtime?.last_error,['status','code','request_id','operation_id','component','phase','at']),
    sources:Object.fromEntries(Object.entries(module.runtime?.sources || {}).map(([name,value])=>[name,
      pick(value,['status','code','phase','request_id','operation_id','last_success_at','cached_at'])])),
  }))},null,2);
}
