// This polls only the local status endpoint, never the remote mailbox.
export function watchAutoSync(request,signal,onStatus,{interval=5000}={}) {
  let timer, last, stopped=false;
  const stop=()=>{stopped=true;clearTimeout(timer);};
  signal.addEventListener('abort',stop,{once:true});
  async function poll() {
    try {
      const value=await request('/auto-sync',{signal});
      if (stopped || signal.aborted) return;
      const changed=value.revision!==last?.revision;
      last=value;onStatus(value,changed);
    } catch {
      if (stopped || signal.aborted) return;
      if (last?.state!=='unavailable') {
        last={...last,state:'unavailable',message:'暂时无法连接本地服务，恢复后继续更新。',revision:'unavailable'};
        onStatus(last,true);
      }
    } finally {
      if (!stopped && !signal.aborted) timer=setTimeout(poll,interval);
    }
  }
  if (!signal.aborted) void poll();
  return stop;
}

export function autoSyncLabel(state) {
  if (!state) return '正在读取自动同步状态…';
  if (state.state==='unavailable') return state.message;
  if (!state.configured) return '配置 IMAP 后可自动同步';
  if (!state.enabled) return '自动同步已暂停';
  return {starting:'正在准备自动同步',syncing:'正在同步邮件',watching:'后台每分钟检查新邮件',
    retrying:'连接暂时中断，稍后自动重试',login_required:'专用密码未通过，请检查邮箱登录'}[state.state] || state.message || '自动同步已开启';
}
