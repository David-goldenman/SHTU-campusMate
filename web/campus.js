import {bindSyncNetwork} from './sync-network.js';

// Generic presentation helper; callers own the palette and record matching.
export function applyAccent(element, appearance = {}) {
  for (const key of ['accent','tint','ink']) {
    const value = appearance[key];
    if (/^#[\da-f]{6}$/i.test(value || '')) element.style.setProperty('--record-' + key, value);
    else element.style.removeProperty('--record-' + key);
  }
}

export function link(url, label, escape) {
  try {
    const target = new URL(url, location.origin);
    if (!['http:', 'https:'].includes(target.protocol)) return escape(label);
    return `<a href="${escape(target.href)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>`;
  } catch { return escape(label); }
}

export function time(value) {
  const date = new Date(value);
  return value && !Number.isNaN(date.valueOf()) ? date.toLocaleString('zh-CN', {timeZone:'Asia/Shanghai', hour12:false}) : '时间未提供';
}

export function submissionLabel(item) {
  const labels = {not_submitted:'未提交',draft:'草稿，尚未提交',submitted:'已提交',needs_grading:'已提交，待评分',graded:'已评分',exempt:'已豁免',unknown:'提交状态待核实'};
  const state = item.exempt === true ? 'exempt' : item.submission_status;
  const label = Object.hasOwn(labels,state) ? labels[state] : (item.submitted === true ? '已提交' : item.submitted === false ? '未提交' : labels.unknown);
  return label + (item.stale || item.submission_stale || item.source_stale ? '（缓存，待核实）' : '');
}

export function records(items, escape) {
  return items.length ? '<div class="campus-list">' + items.map(item => `<article class="campus-item"><h4>${link(item.url, item.title, escape)}</h4><p class="field-hint">${escape([item.source, item.term, item.sender, item.teacher, item.location, item.path?.join(' / ')].filter(Boolean).join(' · '))}</p>${item.body_text ? '<p>' + escape(item.body_text.slice(0, 900)) + '</p>' : ''}${item.download_url ? link(item.download_url, '下载文件', escape) : ''}</article>`).join('') + '</div>' : '<p class="field-hint">当前范围没有内容。</p>';
}

export async function sourcePanel(container, context, render) {
  let timer;
  container.innerHTML = '<div class="campus-toolbar source-toolbar"><span data-status role="status"></span><div><a class="text-button" href="#settings" data-connect hidden>连接账号</a><button class="button button-secondary" data-sync type="button">同步</button></div></div><div data-issues role="status"></div><div data-content></div>';
  const button = container.querySelector('[data-sync]');
  const networkHost = document.createElement('div');
  networkHost.hidden = true;
  container.querySelector('[data-issues]').after(networkHost);
  const diagnose = bindSyncNetwork(networkHost,context,async () => {await context.api('/sync',{method:'POST'});await refresh();});
  const labels = {ready:'已同步', partial:'部分数据可用', cached:'本地缓存', syncing:'正在同步', error:'同步失败', not_connected:'尚未连接', login_required:'需要登录', verification_required:'需要验证'};
  async function refresh() {
    clearTimeout(timer);
    const snapshot = await context.api('/snapshot');
    if (context.signal.aborted) return;
    button.disabled = snapshot.status === 'syncing';
    container.querySelector('[data-connect]').hidden = !['not_connected','login_required','verification_required'].includes(snapshot.status);
    container.querySelector('[data-status]').textContent = (labels[snapshot.status] || snapshot.status) + (snapshot.updated_at ? ' · 上次成功同步 ' + time(snapshot.updated_at) : ' · 暂无成功同步记录');
    container.querySelector('[data-issues]').textContent = [snapshot.message, ...(snapshot.data.issues || [])].filter(Boolean).join('；');
    diagnose.update(snapshot.network_failure ? [snapshot.network_failure] : snapshot.network_failures || []);
    await render(container.querySelector('[data-content]'), snapshot, context, refresh);
    if (snapshot.status === 'syncing') timer = setTimeout(() => refresh().catch(error => { if (!context.signal.aborted) context.ui.toast(error.message); }), 1200);
  }
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await context.api('/sync', {method:'POST'}); await refresh(); }
    catch (error) { if (!context.signal.aborted) { context.ui.toast(error.message); button.disabled = false; } }
  }, {signal:context.signal});
  context.signal.addEventListener('abort', () => clearTimeout(timer), {once:true});
  await refresh();
  return () => clearTimeout(timer);
}
