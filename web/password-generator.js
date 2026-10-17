const PASSWORD_CHARSETS = {
  upper:   'ABCDEFGHJKLMNPQRSTUVWXYZ',
  lower:   'abcdefghjkmnpqrstuvwxyz',
  digits:  '23456789',
  symbols: '!@#$%^&*',
};
const PASSWORD_ALL_CHARS = Object.values(PASSWORD_CHARSETS).join('');

// 确定性字节流：block[0]=SHA-256(seed::site), block[i+1]=SHA-256(block[i] || block[0])
// 任意长度都能取到字节，解决 SHA-256 仅 32 字节导致 length>32 越界的问题
async function deriveBytes(seed, site, minLength) {
  const encoder = new TextEncoder();
  const raw = encoder.encode(seed.trim() + '::' + site.trim().toLowerCase());
  const first = new Uint8Array(await crypto.subtle.digest('SHA-256', raw));
  const blocks = [first];
  const needed = Math.ceil(Math.max(minLength, 8) / 32);
  for (let i = 1; i < needed; i++) {
    const prev = blocks[i - 1];
    const linked = new Uint8Array(prev.length + first.length);
    linked.set(prev, 0);
    linked.set(first, prev.length);
    blocks.push(new Uint8Array(await crypto.subtle.digest('SHA-256', linked)));
  }
  const out = new Uint8Array(needed * 32);
  blocks.forEach((b, i) => out.set(b, i * 32));
  return out;
}

// 为四个类别确定性挑选互不相交的保留位置（Fisher-Yates 洗牌取前 4 个）
function reservedPositions(bytes, length) {
  const idx = Array.from({length}, (_, i) => i);
  let cursor = 32; // 前 32 字节留给主字符填充，从第 32 字节起用于洗牌
  for (let i = length - 1; i > 0; i--) {
    const j = bytes[cursor++ % bytes.length] % (i + 1);
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx.slice(0, 4);
}

// Preserve the existing local seed/site derivation exactly for supported lengths.
export async function generatePassword(site, seed, length = 16) {
  if (typeof site !== 'string' || !site.trim() || typeof seed !== 'string' || !seed.trim()) {
    throw new Error('请输入平台名和非空的种子密码。');
  }
  if (!Number.isInteger(length) || length < 12 || length > 32) {
    throw new Error('密码长度必须是 12 到 32 之间的整数。');
  }
  const bytes = await deriveBytes(seed, site, length);
  const chars = new Array(length);
  for (let i = 0; i < length; i++) {
    chars[i] = PASSWORD_ALL_CHARS[bytes[i] % PASSWORD_ALL_CHARS.length];
  }
  // 四个类别各挑一个互不相交的位置强制写入该类字符，保证四类齐全
  const positions = reservedPositions(bytes, length);
  const sets = Object.values(PASSWORD_CHARSETS);
  for (let k = 0; k < sets.length; k++) {
    const set = sets[k];
    const pick = bytes[(64 + k * 7) % bytes.length] % set.length;
    chars[positions[k]] = set[pick];
  }
  return chars.join('');
}
