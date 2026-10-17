import {escape} from './shared.js';

export function syncNetworkReports(reports) {
  return reports.map(report => `<article class="network-inline notice"><h4>${escape(report.name)}：${escape(report.diagnosis.title)}</h4><p>${escape(report.diagnosis.message)}</p><ul>${report.diagnosis.actions.map(action => '<li>' + escape(action) + '</li>').join('')}</ul><p class="field-hint">${report.diagnosis.confidence === 'suspected' ? '可能原因 · ' : ''}检测于 ${escape(new Date(report.checked_at).toLocaleString('zh-CN'))} · 上次成功数据仍保留</p>${['campus_route','direct_route','dns_proxy','dns'].includes(report.diagnosis.code) ? '<a href="https://it.shanghaitech.edu.cn/2021/0424/c8423a63191/page.htm" target="_blank" rel="noopener noreferrer">查看校园 VPN 接入说明 ↗</a>' : ''}</article>`).join('');
}

export function bindSyncNetwork(host, context, retry) {
  let current = [], key = '', generation = 0;
  const buttons = () => '<div class="network-inline-actions">' + (retry ? '<button class="button button-secondary" data-network-sync type="button">重试同步</button>' : '') + '<button class="text-button" data-network-explain type="button">重新检测网络</button></div>';
  async function diagnose() {
    const run = ++generation;
    host.hidden = false;
    host.innerHTML = '<p class="notice" role="status">同步发生网络错误，正在自动检查原因… 已保留上次成功数据。</p>';
    try {
      const value = await context.services.auth.explainNetwork(current);
      if (context.signal.aborted || run !== generation) return;
      host.innerHTML = syncNetworkReports(value.reports) + buttons();
    } catch (error) {
      if (context.signal.aborted || run !== generation) return;
      host.innerHTML = '<p class="notice" role="status">同步网络请求失败，已保留缓存。自动检测暂未完成：' + escape(error.message) + '</p>' + buttons();
    }
  }
  host.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !host.contains(button)) return;
    if (button.hasAttribute('data-network-explain')) void diagnose();
    if (button.hasAttribute('data-network-sync') && retry) void context.ui.safeAction(button,retry)();
  },{signal:context.signal});
  context.signal.addEventListener('abort',() => {generation++;},{once:true});
  return {update(failures = []) {
    const next = failures.map(item => item.id).sort().join('|');
    if (key === next) return;
    key = next;current = failures;generation++;
    if (!current.length) {host.hidden = true;host.replaceChildren();return;}
    void diagnose();
  }};
}
