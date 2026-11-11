# 在 iOS 上本地运行 campusMate

目标：iPhone/iPad 不依赖电脑上的 Python 服务，本地完成课程、作业、邮件、日程与 AI 问答；**不含微信/QQ 群消息**。

## 结论

采用 **内嵌 CPython + 复用现有 FastAPI 与 `web/` 前端**：app 在自身沙盒里用 `uvicorn` 监听 `127.0.0.1`，`WKWebView` 加载 `http://127.0.0.1:<port>`。

理由：后端约 2.35 万行 Python、19 个模块，前端约 6000 行 JS；前端全部通过同源 `/api/v1` 访问，服务一旦在手机本机跑起来，`web/` 与模块前端不需要改写。原生重写（SwiftUI + URLSession）意味着把 19 个模块的业务逻辑重做一遍，不适合当前阶段。

`ipa/campusMate/Info.plist` 已有 `NSAllowsLocalNetworking`，本机 HTTP 不需要额外 ATS 例外。

## 必须先消除的桌面依赖

iOS 沙盒**禁止 fork/exec**，现有 26 处 `subprocess` 调用全部不可用：

| 组件 | 现状 | iOS 替代 | 工作量 |
| --- | --- | --- | --- |
| Python 运行时 | `uv` + 系统 Python | [Python-Apple-support](https://github.com/beeware/Python-Apple-support) 静态 CPython（3.14-b14 / 3.15-b3，满足 `>=3.12`），用 [Briefcase](https://github.com/beeware/briefcase) 生成工程 | 中 |
| 原生依赖 | PyPI 轮子 | 交叉编译（`cibuildwheel` 已支持 iOS）：`pydantic-core`、`cryptography`、`pillow`、`zstandard`、`pypdfium2` | **高（主要风险）** |
| 凭据保管 | `vault.py`：Windows DPAPI + PowerShell `scripts/dpapi.ps1` | Keychain（`Security.framework`），经 Swift 桥或 `ctypes` 调用 | 低 |
| 学校登录 | `auth/browser.py`：Node + Edge + CDP（`scripts/browser.mjs`） | **内嵌 Safari**（见下节） | 中 |
| AI | `ai/harness.py`：Node 子进程 + `pnpm` 安装 harness 插件 | 三选一，见下节 | 中～高 |
| 微信/QQ 群消息 | `modules/group-messages`：Windows DLL、DLL 注入、进程读取 | **删除该模块** | 无 |
| 文件位置 | 项目目录 `.private/` | App 沙盒 `Application Support/`、`Library/` | 低 |
| 后台同步 | 常驻线程 + 定时任务 | 前台执行 + `BGTaskScheduler`（受限） | 中 |
| 局域网分享/配对码 | `--share`、`share.json`、配对 cookie | 本地运行后不需要，保留代码但不启用 | 无 |
| `uv` / `pnpm` / Node | 构建与桌面运行工具 | **不进运行时**；Xcode 也没有 `uv`，它只是打包工具，iOS 上不存在"Java/uv 式"运行时 | 无 |

## 登录认证：内嵌 Safari 的两种做法

现有实现把浏览器 Cookie 导出成 JSON，再注入 `httpx`（`auth/protocols.py` 的 `client.cookies.jar.set_cookie`）。因此"内嵌 Safari"要分清：

| 方案 | 能否拿到 Cookie | 适用 |
| --- | --- | --- |
| `SFSafariViewController` | **不能**（独立进程，Cookie 在 Safari 自己的存储里） | 只要"登录完成"就够的场景 |
| `WKWebView` | **能**（同进程，`WKHTTPCookieStore` 可读全部 Cookie） | 需要把学校会话 Cookie 交给 Python 侧请求 |
| `ASWebAuthenticationSession` | 只能拿到回调 URL 里的 code/token | 学校支持 OAuth/自定义 scheme 时 |

结论：**用 `WKWebView` 作为登录容器**（外观就是内嵌 Safari），登录完成后 `getAllCookies()` → Swift 桥 → Python `httpx` CookieJar。这样 `PROVIDERS`（coremail/ids/gradescope/piazza）的既有逻辑基本不改，只把 `VerificationBrowser` 换成桥接调用。

## AI 的三条路

1. **纯 Python 直连模型（推荐）**：`AIService` 用 `httpx` 调 DeepSeek/OpenAI 兼容接口，保留 `chat`/`generate`/流式；放弃 Harness 插件运行时（`academic-assistant` 等模块的插件工具会失效）。
2. **nodejs-mobile 内嵌 Node 跑 Harness**：可保留插件，但上游最新是 Node 18（2024-10 停更），体积与审核风险高。
3. **AI 走远程**：把 Harness 留在电脑/服务器，手机端只做 UI——违背"本地运行"，仅作兜底。

## 分阶段计划

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P0 | Briefcase/BeeWare 工程，内嵌 CPython 启动 `uvicorn`，`WKWebView` 打开首页 | 模拟器能进首页、`/api/v1/health` 通 |
| P1 | 交叉编译 5 个原生依赖，`import` 全通过 | `python -c "import fastapi, pydantic, cryptography, PIL, zstandard"` 在模拟器通过 |
| P2 | Keychain 替 Vault；WKWebView 登录 + Cookie 桥 | 连接邮箱/Blackboard 成功 |
| P3 | AI 改纯 Python；删除 `group-messages`；清空 26 处 `subprocess` | 无 `fork/exec`；问答可用 |
| P4 | 后台刷新、真机、打包 | 真机连续使用 1 天 |

CI 已能在 `macos-latest` 上构建（`.github/workflows/ios.yml`），P0 起可加一个模拟器构建 job 防回归。

## 已核实的外部事实（2026-11-10）

- PyPI 上 `pydantic-core`、`cryptography`、`pillow`、`zstandard`、`pypdfium2` **均无 iOS 轮子**（0 个 `ios_*` wheel），必须自行交叉编译。
- `cibuildwheel` 文档已提供 iOS 构建与版本兼容说明。
- Python-Apple-support 最新 `3.15-b3`（2026-10-26），稳定线 `3.14-b14`；Briefcase `v0.4.7`。
- `nodejs-mobile` 最新 `v18.20.4`（2024-10-07）。

## 待定

- AI 走"纯 Python"还是"内嵌 Node"？
- 群消息模块是删除，还是保留代码但 iOS 不编译？
