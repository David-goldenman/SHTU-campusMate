const {app, BrowserWindow, dialog, shell} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {randomUUID} = require('node:crypto');
const {dataPaths, backendEnvironment} = require('./portable.cjs');

const authMode = process.argv.includes('--campus-auth');
const hidden = process.argv.includes('--campus-smoke');
const installRoot = app.isPackaged ? path.dirname(process.execPath) : path.resolve(__dirname, '../..');
const resourceRoot = app.isPackaged ? process.resourcesPath : path.join(installRoot, '.codex', 'desktop', 'stage');
const source = path.join(resourceRoot, 'backend');
const runtime = path.join(resourceRoot, 'runtime');
const profile = authMode ? process.argv.find(arg => arg.startsWith('--user-data-dir='))?.slice(16) : undefined;
let paths;
try {
  paths = dataPaths(installRoot, profile);
  app.setPath('appData', paths.data);
  app.setPath('userData', paths.userData);
  app.setPath('sessionData', paths.sessionData);
  app.setPath('temp', paths.temp);
  app.setPath('crashDumps', paths.crashDumps);
  app.setPath('downloads', paths.downloads);
  app.setAppLogsPath(paths.logs);
  process.env.TEMP = paths.temp;
  process.env.TMP = paths.temp;
  app.commandLine.appendSwitch('user-data-dir', paths.userData);
  app.commandLine.appendSwitch('log-file', path.join(paths.logs, 'chromium.log'));
  app.commandLine.appendSwitch('disk-cache-dir', path.join(paths.userData, 'cache'));
} catch (error) {
  dialog.showErrorBox('CampusMate 无法写入数据', '请选择当前 Windows 用户有写入权限的安装目录。\n' + error.message);
  app.exit(1);
}

app.setName('CampusMate');
app.setAppUserModelId('com.campusmate.desktop');
app.on('window-all-closed', () => app.quit());
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function configureDownloads(window) {
  window.webContents.session.on('will-download', (_event, item) => {
    const basename = path.basename(item.getFilename()).replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_');
    let destination = path.join(paths.downloads, basename);
    if (fs.existsSync(destination)) {
      const parsed = path.parse(basename);
      destination = path.join(paths.downloads, parsed.name + '-' + Date.now() + parsed.ext);
    }
    item.setSavePath(destination);
  });
}

function external(url) {
  const target = new URL(url);
  if (['http:', 'https:'].includes(target.protocol)) shell.openExternal(target.href);
}

if (authMode) {
  app.whenReady().then(() => {
    const window = new BrowserWindow({width: 1300, height: 900, show: !hidden,
      title: 'CampusMate 账号连接', autoHideMenuBar: true,
      webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true}});
    configureDownloads(window);
    window.webContents.setWindowOpenHandler(({url}) => {
      if (['http:', 'https:'].includes(new URL(url).protocol)) return {action: 'allow'};
      return {action: 'deny'};
    });
    window.loadURL('about:blank');
  });
} else if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  let window;
  let backend;
  let stopping = false;
  let stopped = false;
  let origin;
  app.on('second-instance', () => {
    if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
  });

  async function freePort() {
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.once('error', reject);
      server.listen(0, '127.0.0.1', () => {
        const port = server.address().port;
        server.close(() => resolve(port));
      });
    });
  }

  async function stopBackend() {
    if (!backend?.pid || backend.exitCode !== null) return;
    const processId = backend.pid;
    const exited = new Promise(resolve => backend.once('exit', resolve));
    backend.stdin.end('stop\n');
    await Promise.race([exited, sleep(15000)]);
    if (backend.exitCode === null) {
      const killer = spawn(path.join(process.env.SystemRoot, 'System32', 'taskkill.exe'),
        ['/PID', String(processId), '/T', '/F'], {windowsHide: true, stdio: 'ignore'});
      await new Promise(resolve => killer.once('exit', resolve));
    }
  }

  app.on('before-quit', event => {
    if (stopped) return;
    event.preventDefault();
    if (stopping) return;
    stopping = true;
    stopBackend().finally(() => {stopped = true; app.quit();});
  });

  app.whenReady().then(async () => {
    const port = await freePort();
    const launchId = randomUUID();
    origin = 'http://127.0.0.1:' + port;
    const env = backendEnvironment(installRoot, runtime);
    env.CAMPUS_AUTH_ELECTRON = process.execPath;
    const log = fs.openSync(path.join(paths.logs, 'backend.log'), 'a');
    backend = spawn(path.join(runtime, 'python', 'python.exe'),
      ['-s', '-B', '-u', path.join(source, 'packaging', 'electron', 'server.py'),
        '--port', String(port), '--launch-id', launchId],
      {cwd: source, env, windowsHide: true, stdio: ['pipe', log, log]});
    fs.closeSync(log);
    let launchError;
    backend.once('error', error => {launchError = error;});
    backend.once('exit', () => {
      if (!stopping && window) {
        dialog.showErrorBox('CampusMate 后台已停止', '请重新打开程序，或查看安装目录 .private/logs 中的日志。');
        app.quit();
      }
    });
    let ready = false;
    for (let attempt = 0; attempt < 240; attempt++) {
      if (launchError) throw launchError;
      if (backend.exitCode !== null) throw new Error('后台启动失败，请查看 .private/logs/backend.log。');
      try {
        const response = await fetch(origin + '/api/v1/health', {signal: AbortSignal.timeout(1000)});
        const health = await response.json();
        if (health.application === 'campus-framework' && health.launch_id === launchId) {ready = true; break;}
      } catch {}
      await sleep(250);
    }
    if (!ready) throw new Error('后台启动超时，请查看 .private/logs/backend.log。');
    window = new BrowserWindow({width: 1360, height: 900, minWidth: 360, minHeight: 500,
      show: !hidden, title: 'CampusMate', backgroundColor: '#2e3440', autoHideMenuBar: true,
      webPreferences: {nodeIntegration: false, contextIsolation: true, sandbox: true}});
    configureDownloads(window);
    window.webContents.setWindowOpenHandler(({url}) => {external(url); return {action: 'deny'};});
    window.webContents.on('will-navigate', (event, url) => {
      if (new URL(url).origin !== origin) {event.preventDefault(); external(url);}
    });
    await window.loadURL(origin);
    fs.writeFileSync(path.join(paths.data, 'desktop.json'), JSON.stringify({
      version: app.getVersion(), port, pid: process.pid, backendPid: backend.pid, launchId,
      installRoot, dataDirectory: paths.data, userData: app.getPath('userData'),
      sessionData: app.getPath('sessionData'), logs: app.getPath('logs'), temp: app.getPath('temp')}, null, 2));
    if (hidden) {
      await sleep(1500);
      const picture = await window.webContents.capturePage();
      fs.writeFileSync(path.join(paths.logs, 'desktop.png'), picture.toPNG());
    }
  }).catch(error => {
    fs.appendFileSync(path.join(paths.logs, 'desktop-error.log'), error.stack + '\n');
    dialog.showErrorBox('CampusMate 启动失败', error.message);
    app.quit();
  });
}

