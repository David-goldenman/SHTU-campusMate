# CampusMate Windows 桌面版

面向 Windows x64 的本地校园学习工作台。安装包携带 Electron、Python、Node、官方 DeepSeek Harness 和项目依赖，普通使用无需另外安装开发环境。

## 安装和启动

运行安装程序，在目录选择页指定安装位置。请选择当前 Windows 用户有写入权限的目录；安装后从开始菜单或安装目录的 CampusMate.exe 打开。首次使用在设置中连接自己的学校账号并配置 AI 服务。课程平台与模型调用需要网络，校外访问内网服务按学校要求连接 VPN。微信和 QQ 来源需要用户本人客户端或对应本机接口服务。

账号验证使用安装包中的 Electron 独立登录窗口。工作台页面保持隔离，不向网页开放 Node.js。关闭主窗口会正常停止后端和所管理的后台任务。

## 数据位置

应用创建的设置、凭据、课程缓存、模块资料、日志、临时工作区和浏览器资料均保存在安装目录的 .private 中。通过工作台下载或导出的文件保存到 .private/downloads。安装器注册信息和开始菜单入口由 Windows 管理。

升级到同一目录时仅替换程序资源，用户数据原地保留。卸载保留 .private，之后可重新安装读取普通资料；需要彻底清理时由用户自行删除该目录。凭据由当前 Windows 用户的 DPAPI 加密，复制安装目录不等同于跨电脑或跨用户迁移登录，新环境需重新连接账号。

## 构建

在 Windows 构建机准备 Node.js 22 及以上版本、npm、Git 和 uv，在仓库根目录执行：

~~~powershell
.\packaging\electron\build.ps1 -Uv uv
~~~

固定版本见 package.json、package-lock.json 和 uv.lock。构建环境、下载缓存与产物写入项目 .codex/desktop；发布产物位于其中 dist 目录。加上 -Unpacked 可生成用于验收的程序目录。GitHub Release 上传安装程序、SHA256 校验文件和本说明。构建不会自动发布 Release。

安装包内 resources/release.json 记录版本及来源提交。发布前运行 check.ps1，并用安装后的程序验收自定义中文目录、首次启动、登录窗口、独立 Harness 插件、本地数据写入、退出、覆盖升级与卸载保留资料。

在全新安装目录运行下面的合成验收；第二条命令的后端目录应使用同一安装包内的 resources/backend。

~~~powershell
node packaging/electron/check-install.mjs "E:/Apps/CampusMate/CampusMate.exe"
node packaging/electron/check-auth.mjs packaged "E:/Apps/CampusMate/CampusMate.exe" "E:/Apps/CampusMate/resources/backend"
~~~

## 验证范围

本地回归使用合成账号、模拟网络与模型。真实学校登录、客户端兼容与手机日历导入按项目验收记录继续确认。Windows 安装包未使用代码签名证书，系统可能显示发行者未知。

第三方组件、地图数据和主题美术的来源及许可见同目录 THIRD_PARTY_NOTICES.md 与各依赖随附的许可证。

