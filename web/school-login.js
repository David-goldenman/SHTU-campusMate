import {escape} from './shared.js';

const names = {blackboard:'Blackboard',elrc:'虚拟教学社区',ecourse:'E 云课堂',timetable:'教务与课表'};
const statuses = {ready:'已连接',not_connected:'待连接',login_required:'需要登录',verification_required:'需要验证',error:'暂不可用'};

export function recoveryHint(provider) {
  const recovery=provider.recovery?.status;
  if (recovery==='running') return '正在恢复登录，其他读取会共用本次恢复结果。';
  if (recovery==='paused') return '自动恢复已暂停。请更新凭据或主动重新连接，避免重复尝试已失效的登录。';
  if (recovery==='manual_required') return '请打开官方登录窗口完成验证，其他已连接服务仍可使用。';
  if (provider.id === 'coremail' && provider.imap?.configured) return 'IMAP 专用密码已加密保存，读取邮件时直接连接，无需每次在浏览器验证。';
  return provider.automatic_recovery ? '同步前检查登录，过期后自动尝试恢复一次。' : provider.id === 'ids' ? '登录一次即可自动连接校内服务；绑定本机设备或保存密码后，可在统一登录过期时自动恢复。' : provider.id === 'coremail' ? '邮箱单独连接；会话失效时，请重新打开官方登录窗口。' : '当前使用平台独立账号。仅连接会话时，过期需重新登录；保存密码后可自动尝试恢复。';
}

export function schoolServices(provider) {
  const services = Object.keys(names).map(id => ({id,status:'not_connected',...(provider.services || []).find(item => item.id === id)}));
  const connection = provider.connection || {}, running = connection.status === 'connecting';
  const ready = services.filter(item => item.status === 'ready').length;
  const summary = running ? `正在连接校内服务 · ${connection.completed || 0} / ${services.length}`
    : connection.status === 'waiting_for_login' ? '正在等待学校窗口登录，完成后自动连接全部校内服务。'
    : connection.status === 'complete' ? `已连接 ${ready} / ${services.length} 个校内服务` : '一次学校登录，分别建立各服务的连接。';
  return `<div class="school-connections"><p class="field-hint" role="status">${escape(summary)}</p><ul class="school-services">${services.map(item => {
    const active = running && connection.active_target === item.id;
    const needsVerification = ['login_required','verification_required'].includes(item.status);
    return `<li><div><strong>${escape(names[item.id])}</strong><span>${active ? '正在连接…' : escape(statuses[item.status] || '待检查')}</span></div>${item.message ? `<p class="field-hint">${escape(item.message)}</p>` : ''}${needsVerification ? `<button class="text-button" data-school-verify="${escape(item.id)}" type="button">完成该服务验证</button>` : ''}</li>`;
  }).join('')}</ul><p class="field-hint">学校要求验证码或二次验证时，按对应服务提示完成一次验证；其他已连接服务可继续使用。</p></div>`;
}
