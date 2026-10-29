# 四人协作、打包与迁移

当前交付物是 Windows 原生运行的本地网页工作台，WSL 是可选开发入口。`run.cmd` 启动 Python 后端、官方 Harness 与本机 Edge；正式安装包由后续桌面集成工作提供。`ipa/` 内的 SwiftUI 客户端只是同一套页面的手机外壳，需要电脑以 `run.cmd --share` 运行，构建与签名见 [iPhone 客户端](../ipa/README.md)。本文件约定四位成员共同遵守的边界。

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

## 正式安装包路线

建议先确定一个可验收目标：Windows x64、普通用户权限、用户不必预装开发工具。

1. **原生运行基线。** 以 Windows x64 的 Python 后端、Node、DPAPI、Edge 验证窗口、官方 SDK 和原生插件为基线；Windows 使用 `check.ps1`，WSL 使用 `check.sh`。发布前仍需在干净 Windows 用户环境验收，区分本机原生验证和安装包验收。
2. **资源与数据分离。** 安装目录放只读程序和模块资源；用户数据放 `%LOCALAPPDATA%/CampusWorkspace` 或桌面宿主提供的用户目录；缓存和日志另设子目录。先由框架扩展统一路径解析，模块继续使用注入上下文。当前 `backend/core/paths.py` 仍使用项目旁的 `.private`，不能直接把现有代码塞进只读 Program Files 后就认定可用。
3. **固定并携带运行时。** 构建机按锁文件准备所选平台的 Python、Node、Python 依赖、Harness、插件及前端资源。插件安装在发布构建阶段预置或有明确安装流程；正常启动不依赖开发者的全局 PATH、邻近仓库，也不临时下载未锁定依赖。保留第三方许可证与依赖清单。
4. **桌面宿主管理服务。** 按项目既定方向接入 Electron，由主进程负责单实例、选择本机端口、启动后端、等待健康检查、打开窗口和退出清理；学校登录使用共享浏览器接口。普通页面保持 Web/HTTP 边界。
5. **生成安装与升级包。** 可用 Electron Forge 生成对应平台的安装产物，之后配置签名、版本号、升级和回滚。安装/升级只更新程序，保留用户数据；卸载是否清数据应由用户明确选择。正式发布前单独确认分发许可和签名配置。

这条路线是安装包设计与待办，当前 PR 没有生成安装包，也没有把应用改成跨平台。macOS/Linux 需要替换 DPAPI 与浏览器启动适配，并分别构建和验收，不共用一个 Windows 安装文件。

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
