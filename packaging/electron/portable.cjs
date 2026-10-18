const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

async function freePort() {
  // This range is above the browser-restricted ports in backend/core/config.py.
  for (let port = 16666; port < 16766; port++) {
    const server = net.createServer();
    try {
      await new Promise((resolve, reject) => {
        server.once('error', reject);
        server.listen(port, '127.0.0.1', resolve);
      });
      await new Promise(resolve => server.close(resolve));
      return port;
    } catch (error) {
      if (!['EADDRINUSE', 'EACCES'].includes(error.code)) throw error;
    }
  }
  throw new Error('16666–16765 范围内没有可用的本机端口。');
}

function dataPaths(installRoot, profile) {
  const data = path.join(installRoot, '.private');
  const userData = profile || path.join(data, 'electron');
  const relative = path.relative(data, userData);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('登录资料路径必须位于安装目录内。');
  const result = {data, userData, sessionData: userData, temp: path.join(data, 'runtime', 'tmp'),
    logs: path.join(data, 'logs'), crashDumps: path.join(data, 'runtime', 'crashes'),
    downloads: path.join(data, 'downloads')};
  for (const directory of new Set(Object.values(result))) fs.mkdirSync(directory, {recursive: true});
  const probe = path.join(data, '.write-check');
  fs.writeFileSync(probe, '');
  fs.unlinkSync(probe);
  return result;
}

function backendEnvironment(installRoot, runtime, inherited = process.env) {
  const data = path.join(installRoot, '.private');
  const root = path.join(data, 'runtime');
  const windows = inherited.SystemRoot || 'C:\\Windows';
  return {...inherited,
    PATH: [path.join(runtime, 'node'), path.join(windows, 'System32'),
      path.join(windows, 'System32', 'WindowsPowerShell', 'v1.0'), windows].join(path.delimiter),
    CAMPUS_DATA_DIR: data,
    PYTHONHOME: path.join(runtime, 'python'), PYTHONPATH: '',
    PYTHONUSERBASE: path.join(root, 'python-user'), NODE_OPTIONS: '',
    PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1', PYTHONUTF8: '1',
    TMP: path.join(root, 'tmp'), TEMP: path.join(root, 'tmp'), TMPDIR: path.join(root, 'tmp'),
    XDG_CACHE_HOME: path.join(root, 'cache'), XDG_CONFIG_HOME: path.join(root, 'config'),
    XDG_DATA_HOME: path.join(root, 'data'), XDG_STATE_HOME: path.join(root, 'state'),
    COREPACK_HOME: path.join(root, 'corepack'), NODE_COMPILE_CACHE: path.join(root, 'node-cache'),
    npm_config_cache: path.join(root, 'npm-cache'), npm_config_store_dir: path.join(root, 'pnpm-store'),
    npm_config_state_dir: path.join(root, 'pnpm-state'), npm_config_update_notifier: 'false',
    npm_config_auto_install_peers: 'false', npm_config_offline: 'true',
    pnpm_config_offline: 'true', pnpm_config_auto_install_peers: 'false',
    pnpm_config_store_dir: path.join(root, 'pnpm-store'), pnpm_config_state_dir: path.join(root, 'pnpm-state'),
    pnpm_config_update_notifier: 'false', pnpm_config_manage_package_manager_versions: 'false',
    PNPM_HOME: path.join(root, 'pnpm')};
}
module.exports = {dataPaths, backendEnvironment, freePort};

