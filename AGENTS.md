# 开发约定

工作前阅读 [README.md](README.md)、[团队开发约定](docs/DEVELOPMENT.md) 和 [模块接口](docs/MODULES.md)，明确当前任务的负责目录及接口。业务开发限定在分配的 `modules/<id>/`；主框架、公共 UI、共享登录、共享 AI 由各自负责人维护，跨范围改动需要先由协调者明确授权。

- 开发临时文件、验证截图、合成夹具与开发环境写入本项目 `.codex/`，Python 开发使用 uv 和 `.codex/venv`。应用启动创建 `.private/runtime/` 管理运行环境、登录验证、缓存和 Harness 工作区；持久结果使用模块数据目录，正式运行目录由 Git 忽略。
- 用户秘密交给 `context.secrets` 或共享服务 Vault；普通状态交给模块自己的 `context.store`，持久文件交给 `context.data_dir`。私有数据及临时文件遵循现有 `.gitignore`。
- 使用统一 Nord 变量、组件及注入上下文。前端用原生 ES Modules，服务端用 FastAPI；按实际需要增加依赖，由相应公共目录负责人维护依赖锁定文件。
- AI 工具和工作流以官方 DeepSeek Harness 后端为统一入口：新增能力分配独立模块 ID，在 `modules/<id>/harness/` 编写原生 Cordis 插件，由 `context.ai.run(..., plugins=[模块ID])` 调用；基础文本对话与生成使用共享 `chat`、`generate`。框架负责凭据、运行时及生命周期，模块负责业务工具、资料选择和结果校验，接口以 [AI 文档](docs/AI.md) 为准。
- 每项变更解决当前明确需求。遵守 Ponytail 最简原则，复用已有实现，校验系统边界；非平凡行为留下一个小型检查即可。涉及秘密时使用合成数据进行验证。
- 从最新 `origin/main` 建立自己的功能分支，完成接口设计、实现、文档与最小验证后创建 PR；合并前同步主分支并检查实际差异，验证当前提交，合并后拉取 `main` 并重启 demo。修改范围覆盖自己的调用方、文档和检查；跨模块通过文档化 API 协作，公共接口调整交由其负责人整合。
- 热插拔模块实现完整清理：前端在卸载时取消请求、释放监听器和样式；后端 `stop(context)` 结束后台任务。由宿主提供统一设置、登录、AI、主题和安全保护。
- 当前目标为本地网页验证。Electron 最后由桌面负责人统一接入，业务模块维持网页与 HTTP API 边界。
