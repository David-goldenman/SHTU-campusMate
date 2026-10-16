# Campus Framework

本地校园工作台，统一提供 Nord 界面、导航、设置、加密凭据、学校登录、DeepSeek 基础 AI 服务与官方 Harness 插件运行时。已整合首页学习助手、总览、邮箱、时间表、课程聚合、作业、教务系统、通知、AI 助手，以及 Blackboard、Gradescope、ELRC、Piazza、教育问答和截止时间插件模块。首页可以对话查询学习资料、规划作业、引用课件页码并结合成绩与培养方案讨论选课；时间表汇总每周课程、带时间的 quiz／作业与教务考试。侧栏按模块启停显示相应分类，顺序与文案由模块清单声明，框架统一呈现，设置始终可用。

## 下一阶段开发方向

近期目标是完成一条可演示的真实使用链路：连接学校账号 → 识别本学期 → 汇总课程与作业 → 查看通知 → 用课程原文回答问题。按以下顺序推进：

1. **真实来源验收与登录恢复。** 六个来源已完成真实账号的登录与基础同步验证，最近完成课表、Blackboard、Gradescope、Coremail 的重复同步和重启检查。已提供 IDS 本机免密码设备入口、过期恢复和按已验证账号隔离缓存；验证范围及限制见 [真实来源验收](docs/LIVE_ACCEPTANCE.md)，用户连接步骤见 [认证文档](docs/AUTH.md)。继续覆盖学校协议变化、验证码与各来源文件正文，未知提交状态不列为未提交。
2. **验证带引用的学习建议。** 首页 [学习助手插件](modules/academic-assistant/README.md) 已接入按需查询、PDF／PPTX 页级文字、录播检索、历史成绩、培养方案及课程目录／大纲查询。继续用真实问题核对作业建议与课程要求；界面说明发送至 DeepSeek 的资料范围，后端校验实际引用和账号版本后保存。扫描件与未公布的学期开课安排需要用户补充。
3. **收敛演示界面与启动流程。** 课程中心负责课程总入口，来源面板突出连接状态和同步范围；统一失败重试、过期提示、空状态与首次引导。本机 Windows 启动器复用已有 Python 并自动打开网页，WSL 开发入口也保留；接下来准备合成演示数据和 5 分钟演示脚本，按 [交付与移植规范](docs/DELIVERY.md) 验收后再接 Electron。

每项工作从最新主分支建立功能分支，仍按模块分工；共享身份、聚合契约和启动流程的变更作为集成任务处理。

## 启动

Windows 双击本目录的 `run.cmd`。启动器使用已有 Python，等待本机后台可访问后自动打开浏览器，默认地址为 http://127.0.0.1:16666/。启动失败会保留报错窗口，详细日志在 `.codex/logs/`，不会只闪一下就退出。

Windows 启动器不会安装 Ubuntu、Python 或依赖。它优先使用现有 `.codex/venv/Scripts/python.exe`，其次查找常见的 Anaconda/Miniconda 路径。需要 Python 3.12+；缺包或版本不符时列出缺项，由用户在选定环境补齐。已有项目环境能用时，不重复下载环境。Windows 环境缺少 IANA 时区数据时，会复用现有 Conda 的时区数据；找不到才提示自行补装 tzdata。

首次使用时，在设置中连接账号并配置共享 AI；已有账号资料继续保存在本机。打开网页本身不执行登录或模型调用。

- 双击 `stop.cmd`：请求当前目录后台正常结束，执行模块清理；关闭浏览器不会停止后台。
- 重复双击 `run.cmd`：后台已就绪时复用当前实例并打开网页。
- 改用其他已有环境：在 `python-path.txt` 中填写一行 python.exe 完整路径，或用 `--python`；该配置文件由 Git 忽略。
- 设置端口后，未指定端口的下次启动会读取本地保存的值；端口已被其他程序占用时提示错误，不打开或停止那个程序。

~~~powershell
.\run.ps1 --check
.\run.ps1 --no-browser
.\run.ps1 --port 17666
.\run.ps1 --python 'D:\anaconda\python.exe' --check
.\run.ps1 --stop
~~~

更新代码后，新增依赖需在启动器实际使用的环境中手动补齐；`git pull` 不安装 Python 包。启动检查支持普通版本约束和锁定到具体提交的 HTTPS Git 依赖，并核对已安装包的来源记录。缺项会一起列出，启动器不会自动下载。

`--check` 只检查选定环境，不启动服务。旧式 `-Port`、`-NoBrowser`、`-CheckRuntime`、`-PythonPath` 参数也可使用。日志和实例信息写入 `.codex/`；停止时验证进程创建时间和所属目录，避免误停其他副本。

Windows Node.js 22+ 和 Edge 用于登录验证；原生 AI 插件的包管理另需 pnpm。启动网页不执行插件包安装。凭据使用当前 Windows 用户的 DPAPI 加密。共享 AI 及账号需要在设置中自行配置。

WSL 入口保留为 `bash ./run.sh`；它按上游流程在 `.private/runtime/venv` 准备运行环境。应用缓存、登录验证与 Harness 工作区由 `.private/runtime/` 管理；本机 Windows 启动器复用已有 `.codex/venv`，启动控制与开发日志留在 `.codex/`。Windows 双击入口直接使用本机环境，不依赖 WSL。

## AI 功能开发入口

AI 工具和工作流统一使用官方 DeepSeek Harness 后端运行时。每项新增能力在独立 `modules/<id>/harness/` 中实现原生 Cordis 插件，由模块管理负责启停与刷新；框架维护凭据、运行时适配和生命周期。基础文本对话和生成使用共享 `chat`、`generate`，插件任务使用 `context.ai.run(..., plugins=[模块ID])`。示例为 [截止时间整理](modules/deadlines/README.md)，可在 AI 助手的“插件任务”中选择。

需要按问题调用校园 API 的能力参考 [首页学习助手](modules/academic-assistant/README.md)：业务后端创建任务与工具授权，通过内部 `plugin_env` 注入本机调用信息，原生插件负责模型工具接口。带页面的插件从所属页面发起，纯工具插件从“插件任务”选择。学校会话和 API Key 留在共享服务，工具只把回答所需资料交给模型。

开始开发前阅读 [团队开发流程](docs/DEVELOPMENT.md#开发流程)、[AI 插件接口](docs/AI.md#原生-harness-插件) 和 [模块契约](docs/MODULES.md)。`main` 保存已整合且可运行的版本；功能在独立分支开发，完成验证与文档后通过 PR 合并。

## 目录与职责

| 目录 | 内容与维护者 |
| --- | --- |
| `web/` | 框架页面、导航、全局设置、共享组件和 Nord 设计变量；框架维护者负责 |
| `backend/core/`、`backend/main.py` | 生命周期、模块加载、数据隔离、本地接口保护；框架维护者负责 |
| `backend/services/auth/`、`scripts/` | 登录提供方、二次验证和会话管理；认证服务维护者负责 |
| `backend/services/ai/` | DeepSeek 配置、基础对话和官方 Harness 适配；AI 服务维护者负责 |
| `modules/<id>/` | 一项独立业务或 AI 插件模块，按需提供 `web/`、`server/`、`harness/` 与 `checks/` |
| `.private/` | 加密凭据、普通设置、各模块用户数据；整目录加入 Git 忽略规则 |
| `.private/runtime/` | 程序创建的运行环境、登录验证目录、Harness 工作区与缓存；随私有目录忽略 |
| `.codex/` | 当前项目的开发环境、缓存和验证临时数据；整目录加入 Git 忽略规则 |
| `checks/`、`docs/` | 框架和共享服务的最小检查、接口及团队规范 |

项目以空配置启动。账号、密码、Cookie、登录参数、AI Key 和模块秘密统一写入 `.private/vault.dpapi`；接口只返回配置及会话状态。普通设置保存在 `.private/settings.sqlite3`，模块文件存放在 `.private/modules/<id>/`。设置中可分别清除凭据、模块数据，或重置全部本地数据。私有资料和开发环境遵循项目 `.gitignore`。

DPAPI 密文绑定当前 Windows 用户；更换电脑或 Windows 账号后需重新配置凭据。登录验证窗口临时资料位于 `.private/runtime/auth/`，导入会话后关闭并删除临时资料。Windows 会话密钥由操作系统管理，项目内保存密文。

## 统一开发方式

先开发网页和 HTTP API，使用 `modules/<id>/module.json` 注册业务模块；在设置中刷新即可发现，启停和更新以模块为单位进行。模块前端通过 `mount(container, context)` 挂载，后端通过 `create_router(context)` 暴露自己的接口。界面清理、后台任务停止和数据清除都遵循明确的生命周期，详见 [模块开发接口](docs/MODULES.md)。

登录通过 `context.auth` 复用，AI 通过 `context.ai` 调用，模块使用自己的 `context.store`、`context.secrets` 和 `context.data_dir` 管理数据。前端通过注入的 `context.api`、`context.services` 和 `context.ui` 使用接口及组件。API 基础路径为 `/api/v1`，运行后可查看 [交互式接口文档](http://127.0.0.1:16666/api/docs) 和 [OpenAPI](http://127.0.0.1:16666/api/openapi.json)。基础对话和生成使用 DeepSeek 官方 API；需要 AI 调用工具完成工作的新增功能在 `modules/<id>/harness/` 实现原生 Cordis 插件，通过官方 Harness 运行时的 `context.ai.run` 执行，并跟随模块热插拔。AI 助手的“插件任务”提供所选资料和截止时间整理工具的使用入口，详见 [插件接口](docs/AI.md#原生-harness-插件)。

Nord 变量统一在 `web/styles.css` 定义：Polar Night 用于侧栏与正文，Snow Storm 用于内容背景，Frost 用于操作和焦点，Aurora 用于状态提示。默认字体为微软雅黑 UI、微软雅黑和系统字体，正文 16px、行高 1.75，主要标题 32px；业务模块复用 `.button`、`.panel`、`label`、`.empty-state` 等公共组件，以模块根节点限定自己的样式。完整配色、字号和组件用法见 [设计规范](docs/DESIGN.md)。

最后统一集成 Electron：桌面层负责窗口、标签页、系统浏览器与应用内打开方式及桌面能力，网页和模块继续使用相同的本地 API。当前开发入口为网页，模块通过 HTTP 和注入上下文与框架协作。

## 团队交接

每位成员负责明确的 1–3 个模块，在自己的功能分支开发；按可以完整评审的阶段提交 PR，日常小修改直接提交到自己的分支。主框架、共享认证、共享 AI、公共 UI 和业务模块分别设定负责人；跨职责变更先确认接口，再由对应负责人修改。业务模块保持独立，跨模块通过公开接口协作。具体目录边界、分支规则和 Ponytail 最简代码约定见 [团队开发约定](docs/DEVELOPMENT.md) 和 [AGENTS.md](AGENTS.md)。

## 验证与文档

在 WSL 运行 `bash ./check.sh`。检查覆盖空配置、模块动态加载/更新/停用、模块存储隔离、本地接口保护、DPAPI 往返、登录流程、DeepSeek 模拟响应和官方 Harness 原生插件，并自动发现模块检查。学习资料集成检查覆盖 ELRC/Piazza 缓存、教育回答、统一助手与插件任务；夹具只在 `.codex/` 中生成，AI 响应使用本地模拟数据。

- [统一 HTTP API](docs/API.md)
- [模块生命周期与扩展接口](docs/MODULES.md)
- [认证、会话与二次验证](docs/AUTH.md)
- [AI 接入与上下文约定](docs/AI.md)
- [Nord 界面与组件](docs/DESIGN.md)
- [团队开发与修改边界](docs/DEVELOPMENT.md)
- [四人协作、打包与迁移](docs/DELIVERY.md)

交互式 API 页面从 jsDelivr 加载 Swagger UI；离线时可直接使用 OpenAPI JSON 和项目内接口文档。学校登录协议、二次验证和会话有效期由相应网站决定；以真实登录探测结果确认会话状态。

模块边界、独立启停与完整主分支约定见 [AGENTS.md](AGENTS.md) 和 [架构决策](docs/architecture/0001-module-boundaries.md)。完整检查自动覆盖当前安装模块，移除业务模块后仍可启动框架设置页。
