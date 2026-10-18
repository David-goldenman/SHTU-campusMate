// Small local WebAudio cues; no external files or network requests.
let ctx, master, unlocked = false, resuming = false;
let enabled = true;
try { enabled = localStorage.getItem('sounds.enabled') !== 'false'; } catch {}
const voices = new Set();

function ensure() {
  if (ctx && ctx.state !== 'closed') return ctx;
  ctx = master = undefined; unlocked = false;
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return null;
    ctx = new Audio();
    master = ctx.createGain(); master.gain.value = 0.30; master.connect(ctx.destination);
    return ctx;
  } catch {
    try { master?.disconnect(); const closing = ctx?.close(); closing?.catch?.(() => {}); } catch {}
    ctx = master = undefined;
    return null;
  }
}
function release(voice) {
  voices.delete(voice);
  voice.osc.onended = null;
  try { voice.osc.disconnect(); } catch {}
  try { voice.gain.disconnect(); } catch {}
}
function stop() {
  for (const voice of [...voices]) {
    try { voice.osc.stop(); } catch {}
    release(voice);
  }
}
function beep(freq, at, duration, type = 'sine', peak = 0.6) {
  let osc, gain;
  try {
    osc = ctx.createOscillator(); gain = ctx.createGain();
    const voice = {osc, gain};
    osc.onended = () => release(voice); voices.add(voice);
    osc.type = type; osc.frequency.value = freq;
    const start = ctx.currentTime + at;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(peak, start + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(gain); gain.connect(master);
    osc.start(start); osc.stop(start + duration + 0.05);
  } catch {
    const voice = [...voices].find(item => item.osc === osc);
    if (voice) { try { osc.stop(); } catch {} release(voice); }
    else { try { osc?.disconnect(); gain?.disconnect(); } catch {} }
  }
}
const MELODIES = {
  mail: [[659.25, 0, 0.18], [523.25, 0.20, 0.22]],
  deadline: [[440, 0, 0.60, 'triangle', 0.5]],
  announce: [[783.99, 0, 0.10], [783.99, 0.14, 0.10], [783.99, 0.28, 0.14]],
  assistant: [[523.25, 0, 0.12], [659.25, 0.10, 0.18]],
};
export function playSound(kind = 'deadline') {
  if (!enabled || !unlocked || ctx?.state !== 'running') return;
  const notes = Object.hasOwn(MELODIES,kind) ? MELODIES[kind] : MELODIES.deadline;
  for (const [frequency, at, duration, type, peak] of notes) beep(frequency,at,duration,type,peak);
}
export function setEnabled(value) {
  enabled = !!value;
  if (!enabled) stop();
  try { localStorage.setItem('sounds.enabled',String(enabled)); } catch {}
}
export function isEnabled() { return enabled; }
// Only the application calls this from a user gesture; background events cannot resume audio.
export async function unlock() {
  if (!enabled || resuming) return false;
  if (unlocked && ctx?.state === 'running') return true;
  const audio = ensure();
  if (!audio) return false;
  resuming = true;
  try {
    if (audio.state === 'suspended') await audio.resume();
    unlocked = enabled && audio.state === 'running';
    return unlocked;
  } catch { unlocked = false; return false; }
  finally { resuming = false; }
}
