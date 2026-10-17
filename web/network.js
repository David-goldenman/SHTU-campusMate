import {api, escape} from './shared.js';

const states = {reachable:'已响应',login_required:'已响应 · 需要登录',access_denied:'已响应 · 拒绝访问',service_error:'已响应 · 服务异常',http_error:'已响应 · HTTP 异常',dns_error:'解析失败',dns_timeout:'解析超时',timeout:'连接超时',tls_error:'安全连接失败',proxy_error:'代理连接失败',connection_error:'连接失败',protocol_error:'协议异常',configuration_error:'配置异常',ok:'解析成功'};
const stateText = value => states[value] || '状态未知';

export function networkPanel() {
  return `<section class="panel settings-section network-panel" id="network-panel"><div class="section-heading"><div><h2>校园网络检测</h2><p>检查校园服务是否可达，并提供 DNS、代理与校园 VPN 的排查建议。</p></div><button class="button button-primary" data-network-check type="button">重新检测</button></div><p class="field-hint" data-network-progress role="status" aria-live="polite">进入此页后检测，通常在 10 秒内完成。</p><div data-network-result></div><p class="field-hint">校外访问内网服务，请先连接学校 VPN。检测只发送匿名请求，不读取账号和课程资料。</p><a href="https://it.shanghaitech.edu.cn/2021/0424/c8423a63191/page.htm" target="_blank" rel="noopener noreferrer">打开学校 VPN 接入指南 ↗</a></section>`;
}

export function renderNetwork(result) {
  const services = result.services.map(service => {
    const finding = service.diagnosis;
    const attention = finding.code !== 'reachable';
    const evidence = finding.confidence === 'suspected' ? '可能原因' : finding.confidence === 'unknown' ? '原因待确认' : '检测结果';
    const dns = service.dns.addresses.length ? service.dns.addresses.join('、') : stateText(service.dns.status);
    return `<article class="network-service"><header><h3>${escape(service.name)}</h3><span class="status-badge ${attention ? 'network-attention' : 'auth-ready'}">${service.direct.reachable ? '网络可达' : '暂不可达'}</span></header><p class="network-finding">${escape(finding.title)}</p><p>${escape(finding.message)}</p>${finding.actions.length ? '<ul>' + finding.actions.map(action => `<li>${escape(action)}</li>`).join('') + '</ul>' : ''}<details><summary>${evidence}依据</summary><dl><dt>服务入口</dt><dd>${escape(service.host)}:${service.port}</dd><dt>系统 DNS</dt><dd>${escape(dns)}</dd><dt>工作台直连</dt><dd>${escape(stateText(service.direct.status))}${service.direct.http_status ? ' · HTTP ' + service.direct.http_status : ''} · ${service.direct.elapsed_ms} 毫秒</dd><dt>代理路径对照</dt><dd>${service.proxy ? escape(stateText(service.proxy.status)) + (service.proxy.http_status ? ' · HTTP ' + service.proxy.http_status : '') : '未发现适用的普通代理配置'}</dd></dl></details></article>`;
  }).join('');
  return `<div class="network-summary"><strong>${escape(result.summary)}</strong><p>${escape(result.scope)}</p><p>${result.proxy_configured ? '已检测到普通代理配置；校园同步默认绕过它，检测会单独对照代理路径。' : '未发现适用的普通代理配置；TUN 或透明代理仍可能影响系统网络。'}</p></div><div class="network-services">${services}</div>`;
}

export function bindNetwork(panel, signal) {
  const button = panel.querySelector('[data-network-check]');
  const progress = panel.querySelector('[data-network-progress]');
  const output = panel.querySelector('[data-network-result]');
  let running = false, opened = false;
  async function check(useSaved = false) {
    if (running || signal.aborted) return;
    running = true;
    button.disabled = true;
    panel.setAttribute('aria-busy','true');
    progress.textContent = '正在检查校园服务、DNS 和代理路径…';
    try {
      let result = useSaved ? await api('/auth/network',{signal}) : null;
      // A result is a timestamped snapshot, never an assertion about the current VPN state.
      if (!result?.checked_at || Date.now() - new Date(result.checked_at).getTime() > 60000) {
        result = await api('/auth/network/check',{method:'POST',signal,timeoutMs:15000});
      }
      if (signal.aborted) return;
      output.innerHTML = renderNetwork(result);
      progress.textContent = '检测时间：' + new Date(result.checked_at).toLocaleString('zh-CN') + '。切换网络或连接 VPN 后，请重新检测。';
    } catch (error) {
      if (!signal.aborted) progress.textContent = '检测未完成：' + error.message + (output.children.length ? ' 下方保留上次检测结果。' : ' 请稍后重新检测。');
    } finally {
      running = false;
      if (!signal.aborted) {button.disabled = false;panel.removeAttribute('aria-busy');}
    }
  }
  button.onclick = () => check();
  signal.addEventListener('abort',() => {button.onclick = null;},{once:true});
  return {open() {if (!opened) {opened = true;void check(true);}}};
}
