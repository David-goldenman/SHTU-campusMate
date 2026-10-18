const path = require('node:path');
const project = path.resolve(__dirname, '../..');
const build = path.join(project, '.codex', 'desktop');
module.exports = {
  electronVersion: require('./package.json').devDependencies.electron,
  appId: 'com.campusmate.desktop', productName: 'CampusMate',
  directories: {output: path.join(build, 'dist'), buildResources: build},
  files: ['main.cjs', 'portable.cjs', 'package.json'],
  extraResources: [
    {from: path.join(build, 'stage', 'backend'), to: 'backend'},
    {from: path.join(build, 'stage', 'runtime'), to: 'runtime'},
    {from: path.join(build, 'stage', 'release.json'), to: 'release.json'},
    {from: path.join(project, 'packaging', 'electron', 'THIRD_PARTY_NOTICES.md'), to: 'THIRD_PARTY_NOTICES.md'},
    {from: path.join(project, 'packaging', 'electron', 'README.md'), to: 'README.md'}
  ],
  electronDist: path.join(build, 'tools', 'node_modules', 'electron', 'dist'),
  asar: true, compression: 'normal', npmRebuild: false,
  win: {target: [{target: 'nsis', arch: ['x64']}], icon: path.join(build, 'icon.ico')},
  nsis: {oneClick: false, perMachine: false, allowElevation: false,
    allowToChangeInstallationDirectory: true, runAfterFinish: true,
    createDesktopShortcut: false, createStartMenuShortcut: true,
    include: path.join(__dirname, 'installer.nsh'), installerLanguages: ['zh_CN', 'en_US'],
    language: '2052', differentialPackage: false, deleteAppDataOnUninstall: false}
};

module.exports.artifactName = 'CampusMate-${version}-Setup-${arch}.${ext}';

