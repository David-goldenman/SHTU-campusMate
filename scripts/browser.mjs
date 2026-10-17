import { readFile, mkdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { proxyArguments } from './browser-network.mjs';

const input = JSON.parse(await new Promise(resolve => {
  let value = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', part => value += part);
  process.stdin.on('end', () => resolve(value));
}));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
let retainSocket = false;
let serial = 0;
const pending = new Map();
function call(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++serial;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('Browser command timed out')); }, 15000);
    pending.set(id, { resolve, reject, timer });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? {sessionId} : {}) }));
  });
}
async function connect(url) {
  socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data), task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id); clearTimeout(task.timer);
    if (message.error) task.reject(new Error('Browser command failed'));
    else task.resolve(message.result);
  });
}
async function endpoint() {
  const port = (await readFile(join(input.profile, 'DevToolsActivePort'), 'utf8')).split(/\r?\n/)[0];
  if (!/^\d+$/.test(port)) throw new Error('Invalid browser port');
  return await (await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1500) })).json();
}
try {
  if (input.action === 'open') {
    await mkdir(input.profile, { recursive: true });
    const temp = join(input.profile, 'temp');
    await mkdir(temp, { recursive: true });
    let existing;
    try { existing = await endpoint(); } catch {}
    if (!existing) {
      const args = [`--user-data-dir=${input.profile}`, '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check', `--disk-cache-dir=${join(input.profile, 'cache')}`, '--disable-background-mode', '--window-size=1300,900'];
      args.push(...proxyArguments(input.url));
      if (input.headless) args.push('--headless=new', '--disable-gpu');
      args.push('about:blank');
      const child = spawn(input.edge || process.env.CAMPUS_EDGE || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', args, {
        detached: true, windowsHide: Boolean(input.headless), stdio: 'ignore', env: { ...process.env, TEMP: temp, TMP: temp },
      });
      child.on('error', () => {});
      child.unref();
      for (let n = 0; n < 60; n++) {
        await delay(250);
        try { existing = await endpoint(); break; } catch {}
      }
      if (!existing) throw new Error('Login browser did not start');
    }
    await connect(existing.webSocketDebuggerUrl);
    if (input.device_setup) {
      if (input.url !== 'https://ids.shanghaitech.edu.cn/personalInfo/personCenter/index.html#/accountsecurity') throw new Error('Unexpected device setup destination');
      const {targetId} = await call('Target.createTarget', {url:'about:blank'});
      const {sessionId} = await call('Target.attachToTarget', {targetId,flatten:true});
      const source = await readFile(new URL('./ids-device-guide.js', import.meta.url), 'utf8');
      await call('Page.enable', {}, sessionId);
      await call('Page.addScriptToEvaluateOnNewDocument', {source}, sessionId);
      await call('Page.navigate', {url:input.url}, sessionId);
      retainSocket = Boolean(input.keep_alive);
    } else {
      await call('Target.createTarget', { url: input.url });
    }
    console.log(JSON.stringify({ opened: true }));
    // Windows browsers launched through WSL need their launcher to remain alive.
    if (input.keep_alive) {
      const watcher = setInterval(async () => {
        try { await endpoint(); }
        catch { clearInterval(watcher); if (retainSocket && socket) socket.close(); }
      }, 1000);
    }
  } else {
    const version = await endpoint();
    await connect(version.webSocketDebuggerUrl);
    if (input.action === 'close') {
      await call('Browser.close');
      for (let n = 0; n < 50; n++) {
        await delay(100);
        try { await endpoint(); } catch { break; }
      }
      console.log(JSON.stringify({ closed: true }));
    } else if (input.action === 'state') {
      const { cookies } = await call('Storage.getCookies');
      const targets = await call('Target.getTargets');
      const mailPage = targets.targetInfos.find(page => page.type === 'page' && page.url.startsWith('https://mail.shanghaitech.edu.cn/'));
      const sid = mailPage ? new URL(mailPage.url).searchParams.get('sid') : null;
      console.log(JSON.stringify({ cookies, user_agent: version['User-Agent'], sid }));
    } else throw new Error('Unsupported browser action');
  }
} catch {
  console.error(JSON.stringify({ error: 'Verification browser operation failed' }));
  process.exitCode = 1;
} finally {
  if (socket && !retainSocket) socket.close();
}
