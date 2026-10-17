# 本地 UI 与团队更新的维护说明

本机在 `codex/local-ui-polish` 保留 UI 和启动器定制，持续整合团队 `origin/main`。个人启动器及其配置只保存在本地。UI 主题、交互和检查已通过 `codex/share-nord-ui` 上传，[PR #11](https://github.com/David-goldenman/Shanghaitech-2026-Hackthon/pull/11) 已合入团队主线；本地沿用同一主题，并继续接收团队的界面和功能更新。定时任务每 15 分钟获取远端引用并报告变化，不自动合并、切换分支或推送。

## 从哪里启动

- 双击根目录 `run.cmd`，调用 `run-local.ps1` → `scripts/launch.py`，复用已有 `.codex/venv/Scripts/python.exe`，就绪后打开浏览器。默认 http://127.0.0.1:16666/ ，端口以设置为准。
- 双击 `stop.cmd` 只停止本目录启动的后台。关闭浏览器后后台仍继续运行。
- `run-local.ps1 --check` 检查环境；`--no-browser` 只启动后台；`--python 路径` 可指定已安装的 Python。`python-path.txt` 和 `CAMPUS_PYTHON` 仍可指定环境。
- 团队 `run.ps1` 保留主线原版。它使用团队的 uv 环境流程，可能安装运行时；本机日常请使用 `run.cmd` 或 `run-local.ps1`。

本地启动器仅为自身及子进程设置脚本执行方式，使本仓库的 Windows 凭据辅助脚本可运行；不修改系统或用户的永久策略。

启动器不会自动下载 Python 或库。本次主线新增的 Windows 时区依赖已按用户授权装入已有项目环境。临时文件、日志和检查截图保存在 `.codex/`；持久账号、会话与模块数据继续使用 `.private/`。

## 外观改哪里

纯视觉改动集中在 `web/themes/nord-refined.css`：

| 修改 | 位置 |
| --- | --- |
| 背景、文字、边框、侧栏宽度 | 文件开头的语义变量 |
| 导航、按钮、卡片、设置外观 | 对应组件选择器 |
| 总览统计、连接引导、日程卡片 | `.campus-overview` 作用域 |
| 手机和窄屏布局 | 文件末尾的媒体查询 |

`web/index.html` 只保留本地主题的属性和样式链接、跳至主内容入口及菜单图标。所有主题覆写限定于 `data-ui-theme="nord-refined"`。开发时移除这个 HTML 属性即可对照团队基础外观；样式链接中的跳转与快捷入口基础样式仍保留。不要把团队样式全文复制进本地主题；新增覆写只写有差异的属性。

团队 `web/styles.css`、`web/icons.js`、`web/settings.js`、`web/shared.js`、总览原始样式与 `checks/check_web.mjs` 已恢复为本次主线版本。以后这些文件可以直接接受团队更新，再检查本地覆写是否仍匹配。

## 功能与结构改哪里

主题文件只能改变外观。界面行为已成为团队主线的一部分，以下文件按各自职责维护；本地独有改动主要是已有环境启动器：

- `web/app.js`：导航、常驻后台入口、聚合主页面布局、页面分区快捷按钮与主要阅读区切换，全部沿用团队主线的模块元数据与生命周期。
- `modules/dashboard/web/index.js`：紧凑统计、按需展开的近期作业与日程；全部来源尚未连接时显示 `—` 与连接引导，保留独立错误。来源统计继续使用已有 `ready_sources` 字段。
- `scripts/launch.py`：本机已有环境启动、进程归属检查、停止与依赖校验。只支持项目实际使用的版本、固定 Git 地址以及当前 Windows 平台条件；未知依赖条件会明确报错。
- `run.cmd`：本机双击入口对 `run-local.ps1` 的引用。这是仍需保留的公共启动入口差异。
- `checks/check_ui_theme.mjs`、`checks/check_launcher.py`、`checks/check_launcher_requirements.py`：本地主题与启动器回归检查，和团队检查分开维护。

Piazza 保持信息同步和新附件提醒，不自动下载附件。本地没有新增 QQ 接入。

本次同步到 `150a386`，包含 16 个模块：保留新版首页工作区、切页后台生成、日程与学习事务、账号隔离、网络诊断、模块错误隔离和本地数据恢复。后台入口、流式请求与操作回执采用团队主线契约；启动入口继续复用已有项目 Python。

## 下次更新怎么做

1. 在本地 UI 分支保存修改，确认工作区干净；不要把 `.private/` 或 `.codex/` 加入提交。
2. 获取远端更新，查看变化：

```powershell
git fetch origin
git log --oneline HEAD..origin/main
git diff --stat HEAD...origin/main
```

3. 合并功能，逐项处理有冲突的文件：

```powershell
git merge --no-commit origin/main
```

即使没有同文件冲突，也要检查接口字段、路由、模块分类与 CSS 类名。先保留新版功能，再适配主题和少量本地行为；不能直接把整个冲突文件选为本地版。仓库已启用本地 `rerere` 记忆历史冲突解决，但禁用自动暂存，复用结果仍需检查。

4. 验证后完成合并提交，重启本机后台并刷新页面。不要在尚未解决冲突时启动程序。工作区不干净或合并中断时，先检查 `git status`，不要使用强制重置覆盖修改。

最早的 UI 版本保存在 `codex/ui-before-sync-20261017`；本次同步前的版本另保存在 `codex/backup-before-3535313`。设置和记录的冷备份保存在 `.private/backups/before-3535313-*/`，不上传 Git。需要试验团队原版时可使用独立工作目录，避免在运行中的目录来回切换分支。

## 本机验证入口

使用已有环境，无需新装 Python。先启动本机服务，再运行界面检查：

```powershell
& .\run-local.ps1 --check
& .\.codex\venv\Scripts\python.exe -X utf8 -B checks/check_launcher_requirements.py
& .\.codex\venv\Scripts\python.exe -X utf8 -B checks/check_launcher.py
& D:\Hermes\node\node.exe checks/check_web.mjs http://127.0.0.1:16666
& D:\Hermes\node\node.exe checks/check_ui_theme.mjs http://127.0.0.1:16666
& D:\Hermes\node\node.exe modules/academic-assistant/checks/check_web.mjs http://127.0.0.1:16666
& D:\Hermes\node\node.exe checks/check_campus_workspace.mjs http://127.0.0.1:16666
```

本地 UI 检查包含真实未连接页面、合成有数据/无数据快照、独立错误保留、分页切换、模块样式清理、主题开关对照以及 1440/768/375px 和横屏布局。团队检查继续覆盖登录草稿、重试、时间表和模块启停。测试窗口使用合成账号，不提交真实登录信息或调用付费 AI。

跨模块或公共框架变动还需运行团队框架、边界与相关业务检查；完整团队验收入口为 `check.ps1` / `check.sh`。本机直接调用已有环境内相同的检查脚本，可避免这些入口自动创建运行时。

## 开场白（2026-10-17）

普通页面在顶部日期旁显示一条中文开场白；新版桌面首页隐藏顶部栏，因此在学习助手标题下方显示同一句。窄屏沿用顶部位置，两处按页面状态与宽度互斥，不重复显示。HTML 中有默认短句，加载模块或接口前即可看到。新标签页从本地 20 条文案中选择一句，同一标签页的刷新和页面切换保持不变；浏览器限制会话存储时仍能显示。没有轮播、打字动画、额外网络请求或模型调用，不改变真实的加载、同步和错误提示。

文案学习用户提供的 `E:\AAAstudy\黑客松\openclaw-quirks.md` 中的反转与自嘲节奏，改写为学习、文件、天文和截止日期语境，不使用 OpenClaw 品牌身份。

- 文案池与选取：`web/opening-lines.js`。
- 普通页位置与默认句：`web/index.html` 的 `data-opening-line`。
- 桌面首页位置：`modules/academic-assistant/web/index.js` 的 `study-opening-line`；从公共开场白模块读取同一份本地文案，不重新挑选。
- 独立样式与窄屏换行：`web/opening-lines.css`。

开场白已通过 PR #42 合入团队 main（150a386），队友更新后即可使用。个人启动器继续只保存在本地。两套艺术主题已在本地实现，入口为设置 → 外观，说明见 ART_THEMES.md。

最新主线使用 `httpx[socks]>=0.28`。本地启动器已识别该声明并检查 httpx 版本及 socksio 1.x；只接受项目实际使用的 extra，不忽略未知依赖。用户本次授权补装的 `socksio==1.0.0` 已安装到现有项目环境，启动器本身仍不安装软件。

本次同步还包含按来源隔离的作业状态统计、作业状态分类、时间表中的作业日期、Blackboard 提交证据、草稿／待评分／豁免／待核实状态，以及同步失败旁的网络诊断。启动器合成检查的随机端口现复用应用端口校验，避免偶然选中浏览器限制的 2049 等端口；实际默认端口仍为 16666。

### 本次验证

已同步主线 7afff8d 并保留个人启动器和开场白。完整回归通过：41 项 Python 检查、3 项 JavaScript 检查、Windows 启动器及 47 个 JavaScript 文件语法检查。日志保存在 .codex/local-update-7afff8d-checks.log。

实际浏览器验证了 1280px 桌面与 375px 窄屏：首页对话、校园概览、设置页均只有一条可见开场白；刷新与切页保持同一句，无页面横向溢出，输入框正常可见，未发送聊天或调用付费模型。截图保存在 .codex/screenshots/opening-line-final-desktop-20261017.jpg 与 opening-line-final-mobile-20261017.jpg。

