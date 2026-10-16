# 校园工作台

本地校园信息工作台，以独立模块接入学校邮箱、教务课表、Blackboard、Gradescope、Piazza 和虚拟教学社区，提供课程中心、作业管理、校园总览、重要通知与 AI 助手。框架统一维护 Nord 界面、导航、设置、加密凭据、学校登录和 DeepSeek 服务。

## 启动

当前开发环境为 Windows + WSL Ubuntu-26.04：Python 服务在 WSL 运行，登录验证使用 Windows Edge，凭据使用当前 Windows 用户的 DPAPI 加密。需要 Python 3.12+、uv、Windows Node.js 22+ 和 Edge。Node.js 仅用于登录验证窗口，网页界面使用原生 ES Modules。

在 Windows 双击 `run.cmd`，或运行：

```powershell
.\run.ps1
# 同时运行其他本地项目时可指定独立预览端口
.\run.ps1 --port 17666
```

在 WSL 中运行 `bash ./run.sh`，打开 [本地工作台](http://127.0.0.1:16666)。默认端口为 16666，设置中修改端口后重启生效。所有路径从项目目录计算，可以整体移动项目目录。启动脚本把虚拟环境、uv 缓存、Python 缓存和临时文件统一放入 `.codex/`。

首次使用在设置中连接账号，IDS 共用于教务、Blackboard 与教学社区，邮箱、Gradescope 和 Piazza 分别连接。随后在总览点击同步数据。课程中心按课程代码与学期自动关联，也支持手动分组；作业管理区分开放能力、提交状态和截止时间。邮箱支持正文阅读、规则、手动、AI 与专用 Agent 分类。AI 助手和通知使用所选缓存文字，并附带可验证来源；自动通知在通知页启用。

## 功能模块与分支

| 模块 | 内容 | 功能分支 |
| --- | --- | --- |
| [timetable](modules/timetable/README.md) | 教务课程、周次、教师与教室 | `feat/timetable` |
| [mail](modules/mail/README.md) | Coremail 正文、分类与 Agent 接口 | `feat/mail` |
| [gradescope](modules/gradescope/README.md) | 课程、作业能力与题目下载 | `feat/gradescope` |
| [blackboard](modules/blackboard/README.md) | 资料目录、成绩、作业与公告 | `feat/blackboard` |
| [piazza](modules/piazza/README.md) | 近期讨论与嵌套回复 | `feat/piazza` |
| [elrc](modules/elrc/README.md) | 章节资料、录播、转写与学校摘要 | `feat/elrc` |
| [courses](modules/courses/README.md) | 跨平台课程关联与统一只读目录 | `feat/courses` |
| [assignments](modules/assignments/README.md) | 本学期待办与按课程查看作业 | `feat/assignments` |
| [dashboard](modules/dashboard/README.md) | 本学期统计、近期截止与来源状态 | `feat/dashboard` |
| [assistant](modules/assistant/README.md) | 资料选择、连续对话、总结与报告 | `feat/assistant` |
| [notifications](modules/notifications/README.md) | 重要事项、自动提炼与已读跟踪 | `feat/notifications` |

`feat/module-data` 提供公共模块 HTTP 调用、来源同步、文件读取与 AI 引用校验。`integration/demo` 用于本地整体运行和验证，`main` 保存基础框架。各模块保持自己的前后端、说明与检查，数据通过公开 API 协作。

## 目录与职责

| 目录 | 内容与维护者 |
| --- | --- |
| `web/` | 框架页面、导航、全局设置、共享组件和 Nord 设计变量；框架维护者负责 |
| `backend/core/`、`backend/main.py` | 生命周期、模块加载、数据隔离、本地接口保护；框架维护者负责 |
| `backend/services/auth/`、`scripts/` | 登录提供方、二次验证和会话管理；认证服务维护者负责 |
| `backend/services/ai/` | DeepSeek 配置和通用生成接口；AI 服务维护者负责 |
| `modules/<id>/` | 一项独立业务模块，内部按 `web/`、`server/`、`checks/` 分工 |
| `.private/` | 加密凭据、普通设置、各模块用户数据；整目录加入 Git 忽略规则 |
| `.codex/` | 当前项目的开发环境、缓存和验证临时数据；整目录加入 Git 忽略规则 |
| `checks/`、`docs/` | 框架和共享服务的最小检查、接口及团队规范 |

项目以空配置启动。账号、密码、Cookie、登录参数、AI Key 和模块秘密统一写入 `.private/vault.dpapi`；接口只返回配置及会话状态。普通设置保存在 `.private/settings.sqlite3`，模块文件存放在 `.private/modules/<id>/`。设置中可分别清除凭据、模块数据，或重置全部本地数据。账号版本变化会隔离来源缓存及派生的对话和通知；归档、环境、缓存与个人资料遵循 `.gitignore`。

DPAPI 密文绑定当前 Windows 用户；更换电脑或 Windows 账号后需重新配置凭据。登录验证窗口临时资料位于 `.codex/auth/`，导入会话后关闭并删除临时资料。Windows 会话密钥由操作系统管理，项目内保存密文。

## 统一开发方式

先开发网页和 HTTP API，使用 `modules/<id>/module.json` 注册业务模块；在设置中刷新即可发现，启停和更新以模块为单位进行。模块前端通过 `mount(container, context)` 挂载，后端通过 `create_router(context)` 暴露自己的接口。界面清理、后台任务停止和数据清除都遵循明确的生命周期，详见 [模块开发接口](docs/MODULES.md)。

登录通过 `context.auth` 复用，AI 通过 `context.ai` 调用，模块使用自己的 `context.store`、`context.secrets` 和 `context.data_dir` 管理数据。前端通过注入的 `context.api`、`context.services` 和 `context.ui` 使用接口及组件。API 基础路径为 `/api/v1`，运行后可查看 [交互式接口文档](http://127.0.0.1:16666/api/docs) 和 [OpenAPI](http://127.0.0.1:16666/api/openapi.json)。共享 AI 直接调用 DeepSeek 官方 API，由模块提供要处理的文本和对话。

Nord 变量统一在 `web/styles.css` 定义：Polar Night 用于侧栏与正文，Snow Storm 用于内容背景，Frost 用于操作和焦点，Aurora 用于状态提示。默认字体为微软雅黑 UI、微软雅黑和系统字体，正文 16px、行高 1.75，主要标题 32px；业务模块复用 `.button`、`.panel`、`label`、`.empty-state` 等公共组件，以模块根节点限定自己的样式。完整配色、字号和组件用法见 [设计规范](docs/DESIGN.md)。

最后统一集成 Electron：桌面层负责窗口、标签页、系统浏览器与应用内打开方式及桌面能力，网页和模块继续使用相同的本地 API。当前开发入口为网页，模块通过 HTTP 和注入上下文与框架协作。

## 团队交接

每位成员负责明确的 1–3 个模块，在自己的功能分支开发；按可以完整评审的阶段提交 PR，日常小修改直接提交到自己的分支。主框架、共享认证、共享 AI、公共 UI 和业务模块分别设定负责人；跨职责变更先确认接口，再由对应负责人修改。业务模块保持独立，跨模块通过公开接口协作。具体目录边界、分支规则和 Ponytail 最简代码约定见 [团队开发约定](docs/DEVELOPMENT.md) 和 [AGENTS.md](AGENTS.md)。

## 验证与文档

在 WSL 运行 `bash ./check.sh`。检查覆盖空配置、模块动态加载/更新/停用、模块存储隔离、本地接口保护、DPAPI 往返、登录流程、来源异常与 DeepSeek 模拟响应，并自动发现各模块检查。`checks/check_integration.py` 使用六个平台的合成响应验证全部模块共同运行，包括课程关联、Agent 权限、正文与录播详情、文件下载、AI、后台清理与账号切换；测试夹具只在 `.codex/` 中生成。

- [统一 HTTP API](docs/API.md)
- [模块生命周期与扩展接口](docs/MODULES.md)
- [认证、会话与二次验证](docs/AUTH.md)
- [AI 接入与上下文约定](docs/AI.md)
- [Nord 界面与组件](docs/DESIGN.md)
- [团队开发与修改边界](docs/DEVELOPMENT.md)

交互式 API 页面从 jsDelivr 加载 Swagger UI；离线时可直接使用 OpenAPI JSON 和项目内接口文档。学校登录协议、二次验证和会话有效期由相应网站决定；以真实登录探测结果确认会话状态。
