const CHARSETS = [
  'ABCDEFGHJKLMNPQRSTUVWXYZ',
  'abcdefghjkmnpqrstuvwxyz',
  '23456789',
  '!@#$%^&*',
];
const ALL_CHARS = CHARSETS.join('');

// Versioned inputs keep seed/site/length derivation deterministic; no seed is saved.
export async function generatePassword(site, seed, length = 16) {
  if (typeof site !== 'string' || !site.trim() || typeof seed !== 'string' || !seed.trim()) {
    throw new Error('请输入平台名和非空的种子密码。');
  }
  if (!Number.isInteger(length) || length < 12 || length > 64) {
    throw new Error('密码长度必须是 12 到 64 之间的整数。');
  }
  const input = ['campus-password-v1',seed.trim(),site.trim().toLowerCase(),length];
  const encoder = new TextEncoder();
  let bytes = new Uint8Array(), offset = 0, block = 0;
  async function choose(size) {
    const limit = 256 - 256 % size;
    while (true) {
      if (offset === bytes.length) {
        bytes = new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(JSON.stringify([...input,block++]))));
        offset = 0;
      }
      const value = bytes[offset++];
      if (value < limit) return value % size;
    }
  }
  const chars = [];
  for (const set of CHARSETS) chars.push(set[await choose(set.length)]);
  while (chars.length < length) chars.push(ALL_CHARS[await choose(ALL_CHARS.length)]);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = await choose(i + 1);
    [chars[i],chars[j]] = [chars[j],chars[i]];
  }
  return chars.join('');
}
