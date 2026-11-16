# 四人协作、打包与迁移

当前包含 Windows 本地网页开发入口和 Electron 桌面安装候选版。日常开发仍用既有工作副本的 `run.cmd`／`run-local.ps1`，账号和数据位置不变。桌面候选版面向 Windows x64 普通用户，随包携带 Python、Node、官方 Harness 与本项目插件依赖；学校网页登录继续使用 Windows 上的 Edge。

iPhone 客户端继续由 `ios/local/` 与 `ios/shell/` 提供，构建和运行方式见 [平台说明](PLATFORM_SUPPORT.md) 与 [iPhone 客户端](../ios/shell/README.md)。

## 构建和安装候选版

构建机需要现有 Python 3.12.10、uv、Node 24.18.0 和 pnpm 11.22.0。运行 `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`，产物在 `.codex/windows-release/campusMate-0.2.0-Setup.exe`。桌面依赖固定在 `desktop/package-lock.json`；Python 使用 `uv.lock`；其余运行时版本见 `packaging/runtime-lock.json`。构建缓存和准备目录均在 `.codex/`。安装后的正常启动不调用 uv/npm/pnpm，也不下载依赖。

`packaging/build_windows.py` 只采集 backend、web、模块的 server/web/harness 和明确列出的运行脚本；排除 `.private`、开发环境、检查、备份文件及隐藏目录。依赖版本和源文件清单写入 `resources/campus/release-manifest.json`，第三方许可证位置见同目录 `THIRD_PARTY.txt`。Harness 每次任务从预装模板复制独立可写配置，仅激活被选中的插件；插件版本不匹配时要求修复安装，不回退到在线安装。

安装器默认写入 `%LOCALAPPDATA%\Programs\campusMate`。每次安装准备独立版本目录，使用临时空账号数据实际启动候选版并验证界面，然后原子切换 `current.json`。失败不改变旧指针；开始菜单的 “Restore previous version” 可回到上一版，操作前需关闭桌面应用。卸载只移除受安装记录管理的程序目录，保留 `%LOCALAPPDATA%\campusMate\data`。选择已有无关文件的目录会被拒绝。

安装、回滚及卸载均拒绝程序路径、默认资料路径和 `CAMPUS_DATA_DIR` 路径任一层的链接／联接目录，并检查程序与资料互不包含。升级同时更新已安装的维护脚本，确保已有安装的回滚和卸载入口获得新的路径保护。

桌面启动在创建用户资料和浏览器配置目录之前也检查程序、资料的全部路径祖先，拒绝链接／联接，并按实际路径核对包含关系；安全且尚未创建的普通资料目录可正常使用。

Electron 负责单实例、本机服务就绪和退出。默认争取 16666；已有程序占用时另选空闲端口，不接管已有服务。就绪检查验证本次随机实例编号。页面禁用 Node、启用上下文隔离；保留原有 Host、Origin 与写令牌校验。关闭窗口后通过控制管道正常停止后端；宿主异常退出同样关闭管道，Windows Job Object 负责收回其子进程。

## 显式迁移开发版数据

安装不会自动扫描或导入现有账号。需要在同一 Windows 用户下迁移时，先停止开发版与桌面版，再运行随包 Python 和 `scripts/migrate_data.py --source <旧.private绝对路径> --destination <新数据绝对路径>`。新目录必须为空。迁移先建立独立备份并检查 SQLite，再启用新副本；原目录保留。根目录 `runtime` 下的浏览器临时会话、运行环境、日志及根目录的应用凭据锁文件不迁移，DPAPI 凭据仅适用于原 Windows 用户。

`runtime` 目录排除规则仅作用于资料根目录；模块资料内部由用户创建的同名目录及其文件，会完整进入迁移副本和独立备份。

迁移只排除根目录的 `vault.dpapi.lock` 和真实 SQLite 数据库的 `-wal`／`-shm` 附属文件；数据库通过 SQLite 备份接口合并已提交日志并验证完整性。普通用户 `uv.lock`、`poetry.lock`、名称以 `-wal`／`-shm` 结尾的资料及仅名称类似数据库的文件都会保留。应用主数据库无效时拒绝迁移。

## 验收边界

行为检查覆盖独立数据目录、Unicode／空格路径、重复启动、占用端口、退出释放、升级失败与回滚。`packaging/verify_harness.py` 使用随包解释器、官方 Harness 与本地合成模型验证原生工具，拒绝运行时安装依赖。桌面构建和安装候选需要在每次交付时执行真实安装检查；这些检查不等于干净 Windows VM、真实学校登录或真实模型服务的验收。当前候选没有发布者签名，未配置自动更新或公开发布渠道。

## 四人协作的共同约定

| 事项 | 现在的要求 | 避免的迁移问题 |
| --- | --- | --- |
| 分支与合并 | 每人从最新 `origin/main` 建立功能分支；按现有负责目录修改；PR 写明行为、接口、依赖和验证，合并前同步主分支 | 并行开发互相覆盖、只在个人机器可运行 |
| 公共改动 | 启动入口、路径规则、Vault、AI、公共 UI 与锁文件由相应负责人或集成人员整合；先明确接口，再同步调用方 | 四个人各复制一套登录、环境和平台判断 |
| 路径与配置 | 资源从项目/模块位置解析，使用 `context.data_dir/store/secrets`；个人 WSL 用参数或环境变量选择，运行时从配置或 PATH 定位 | 用户名、盘符、某个发行版、邻近项目路径写进代码 |
| 依赖 | Python 基线由 `.python-version` 指定为 3.12；依赖变更同时提交 `pyproject.toml` 和 `uv.lock`，启动与检查用 `uv sync --locked`；原生插件声明 npm 依赖，发布构建固定实际解析版本 | 另一位成员安装后拿到不同依赖；构建依赖个人缓存 |
| 模块接口 | 保持 `api_version:1` 的公开 HTTP API；不读其他模块数据库，不直接 import 其他模块私有代码 | 模块无法独立安装、测试或由桌面壳加载 |
| 平台接口 | Windows 浏览器、DPAPI、WSL、子进程管理集中在框架/共享服务；业务模块不导入 Electron 或执行系统工具 | 换桌面壳或操作系统时需要重写业务 |
| 生命周期 | `stop` 结束后台任务，关闭连接；前端卸载释放监听器、样式和请求；进程仅监听本机并保留 Host/Origin/CSRF 校验 | 退出仍占端口、升级无法替换文件、本机 API 暴露 |
| 数据格式 | 有持久数据格式变更时，PR 给出旧版本升级及失败恢复方案；使用合成夹具验证 | 升级安装包后旧数据无法打开 |

共享分支上的“能运行”是统一入口与公开接口能运行。不得以“我的机器有这份文件/这把 Key/这个全局包”作为隐含前提。每个模块 README 说明外部服务、所需配置、持久文件与清理方式。

## 开发版迁移到另一台 Windows 电脑

1. 复制 Git 跟踪的代码或克隆指定提交，保留 `uv.lock`、模块清单、前端资源与检查。不要把 `.private/`、`.codex/`、`.venv/`、`node_modules/`、`.env*`、浏览器配置和个人日志装进分享包。
2. 目标机安装 Git、Node.js 22+ 与 Edge；Python 3.12+（含 pip）或 Windows uv 至少准备一个，AI 插件安装另需 pnpm。先运行 `run.cmd --check`，再双击 `run.cmd`；缺少 uv 时启动器会用 Python/pip 把它安装到 `.private/runtime/tools/uv`，随后按锁文件创建 `.private/runtime/windows/venv`，官方 SDK 安装对应 Windows x64 运行时。选择 WSL 时使用 `--distro`，安装对应 Linux 工具。首次联网安装失败时显示错误，不静默替换版本。
3. 在设置中重新连接学校账号、配置个人 AI Key。DPAPI 保险库及 IDS 本机设备私钥绑定原 Windows 用户环境，不能把复制 `vault.dpapi` 当作跨电脑登录迁移。学校端设备登记按需要重新绑定。
4. 如需迁移用户资料，单独定义显式的导出/导入流程，只迁移用户选择的普通配置与数据，校验格式版本和账号归属。课程缓存、邮件和转写属于用户私有资料；默认在新机重新同步。数据库备份应在服务停止后进行。
5. 即使只是同机移动目录，也不承诺 Python 虚拟环境可直接移动：虚拟环境可能引用原解释器的绝对路径。生成的互操作脚本在下一次启动时重建；失效的开发环境由 uv 重新创建，不修改业务代码来适配旧路径。

## 后续正式发布检查

候选目标为 Windows x64、普通用户权限、用户不必预装开发工具。中文与空格路径受支持；安装前检查原生库的 Windows 路径长度限制，过长目录会被拒绝，建议使用默认位置。

1. **原生运行基线。** 以 Windows x64 的 Python 后端、Node、DPAPI、Edge 验证窗口、官方 SDK 和原生插件为基线；Windows 使用 `check.ps1`，WSL 使用 `check.sh`。发布前仍需在干净 Windows 用户环境验收，区分本机原生验证和安装包验收。
2. **资源与数据分离。** 确认用户数据进入 `%LOCALAPPDATA%\campusMate\data` 或显式配置的独立目录；程序与资料目录不得相互包含。模块继续使用注入上下文，开发版 `.private` 行为保持兼容。
3. **固定并携带运行时。** 构建机按锁文件准备所选平台的 Python、Node、Python 依赖、Harness、插件及前端资源。插件安装在发布构建阶段预置或有明确安装流程；正常启动不依赖开发者的全局 PATH、邻近仓库，也不临时下载未锁定依赖。保留第三方许可证与依赖清单。
4. **桌面宿主管理服务。** 按项目既定方向接入 Electron，由主进程负责单实例、选择本机端口、启动后端、等待健康检查、打开窗口和退出清理；学校登录使用共享浏览器接口。普通页面保持 Web/HTTP 边界。
5. **生成安装与升级包。** 当前候选使用固定版本的 Electron Builder 和 NSIS 编译器，版本目录保留供回滚。正式发布前补齐签名、干净系统验收、分发许可及更新渠道；不将本地候选视为已发布产品。

上面的路线用于后续正式发布核对；当前 Windows 候选实现以本文开头的实际构建、安装与验收约定为准。macOS/Linux 需要替换 DPAPI 与浏览器启动适配，并分别构建和验收，不共用一个 Windows 安装文件。

## 四人集成与发布检查

- 提交者：运行影响模块的检查，更新接口/README，提供合成输入与失败场景；不提交真实账号、Cookie、API Key 或私人页面。
- 相应公共服务负责人：确认接口兼容与依赖变化；跨模块修改由集成人员明确纳入。
- 集成人员：以合并后的实际提交运行 Windows `check.ps1` 或 WSL `check.sh`，确认 `run.cmd` 冷启动、重复启动、停止、端口冲突，以及启停/刷新模块。
- 发布候选：在没有开发环境缓存的干净 Windows 用户环境中，检查中文/空格路径、首次登录、过期恢复、AI Key 配置、原生插件、升级保留数据及卸载行为。CI 可使用合成服务；真实学校登录由受授权的验收者完成。

开发版已验证的入口不等于干净机器的安装包验收。PR 和发布记录分别写清两者范围。

## 启动器维护与资料

`run.cmd` 调用兼容 Windows PowerShell 5.1 的 `run.ps1`。默认使用 Windows；显式选择 WSL 时探测发行版并创建互操作脚本。生成文件位于 `.private/runtime/launcher`，Windows 环境位于 `.private/runtime/windows`。PATH 中没有 uv 时，原生启动器会先用 Python/pip 安装到 `.private/runtime/tools/uv` 并复用；`CAMPUS_UV` 可指定已有程序。`/api/v1/health` 和公开 `launch_id` 用于确认本目录实例就绪，与凭据、CSRF 和数据归属校验分开。

最小检查：`powershell -NoProfile -ExecutionPolicy Bypass -File checks/check_launcher.ps1`、`run.cmd --check`；全量检查使用 Windows `check.ps1` 或 WSL `check.sh`。手工验收保留启动窗口，重复启动应打开已有实例，按 Ctrl+C 应停止后端。实际启动故障和迁移故障应回到对应平台适配修复。

参考：[Microsoft WSL 命令](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)、[uv 安装与本地安装选项](https://docs.astral.sh/uv/reference/installer/)、[Electron Forge 打包流程](https://www.electronjs.org/docs/latest/tutorial/tutorial-packaging)。
