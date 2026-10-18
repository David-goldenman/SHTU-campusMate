; Inno Setup script — Campus Framework installer
; 编译要求：Inno Setup 6.x（https://jrsoftware.org/isinfo.php）
; 用法：
;   1) 先跑 packaging/build_mirror.py 产出 dist/CampusFramework/
;   2) ISCC.exe packaging/installer.iss
; 产出：Output/CampusFrameworkSetup-<version>.exe（单文件 setup，带卸载/start menu/桌面 icon）

#define AppName "Campus Framework"
#define AppNameZh "校园工作台"
#define AppVendor "ShanghaitechHackathon"
#define AppExeName "CampusFramework.exe"
#define AppId "{{8E9D8354-2A72-4B8D-8715-CAMPUSFRAME1}}"
#define AppVersion "0.1.0"   ; TODO: 从 pyproject 提取

#define SrcDir "..\\dist\\CampusFramework"
#define OutDir "..\\Output"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppVendor}
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppVendor}
VersionInfoDescription={#AppNameZh} Installer

; 用户态安装，无需 UAC；不污染 Program Files
DefaultDirName={localappdata}\Programs\{#AppVendor}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 单文件 + 现代外观
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
; SetupIconFile 必须用 .ico。当前项目 web/icon.svg 是 svg，跳过 setup icon，
; 让 Inno Setup 用默认；UninstallDisplayIcon 用 exe 自带资源。
UninstallDisplayIcon={app}\{#AppExeName}

OutputDir={#OutDir}
OutputBaseFilename=CampusFrameworkSetup-{#AppVersion}

; 禁用修改 PATH / 注册开机启动 等系统级 side effects
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64

; AppPaths：让 Windows 通过 shell 直接调
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExeName}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppId}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"; Flags: uninsdeletekey

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"

[Files]
; 全部产物（_internal/ + modules/ + bin/ + exe）
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单
Name: "{group}\{#AppNameZh}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppNameZh}"; Filename: "{uninstallexe}"
; 桌面（可选）
; Name: "{autodesktop}\{#AppNameZh}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
; 勾选项：桌面图标 + Edge WebView 检查
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加任务："

[Run]
; 安装完成后询问是否立即启动
Filename: "{app}\{#AppExeName}"; Description: "立即启动 {#AppNameZh}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; 卸载时清残留（保留用户数据：APPDATA 数据单独目录）
Type: files; Name: "{app}\{#AppExeName}"

[Code]
// 在启动 setup 前检测 Edge WebView
function InitializeSetup(): Boolean;
var
  msEdgePath: string;
begin
  Result := True;
  msEdgePath := 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe';
  if not FileExists(msEdgePath) then begin
    msEdgePath := 'C:\Program Files\Microsoft\Edge\Application\msedge.exe';
  end;
  if not FileExists(msEdgePath) then begin
    if MsgBox(
      '未检测到 Microsoft Edge 浏览器。' + #13#10 +
      'Campus Framework 需要 Edge 才能拉起校园网站 SSO 登录窗口，' +
      '但您仍可以继续安装，稍后再安装 Edge。' + #13#10#13#10 +
      '确定继续安装吗？',
      mbConfirmation, MB_YESNO) = IDNO
    then begin
      Result := False;
    end;
  end;
end;
