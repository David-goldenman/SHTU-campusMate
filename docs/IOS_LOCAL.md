# 在 iOS 上本地运行 campusMate

目标：iPhone/iPad 不依赖电脑上的 Python 服务，本地完成课程、作业、邮件、日程与 AI 问答；**不含微信/QQ 群消息**。

架构决策与取舍见 [architecture/0002-ios-local.md](architecture/0002-ios-local.md)；构建、版本与缓存规则见
[../ios/DEVELOPMENT.md](../ios/DEVELOPMENT.md)。

## 结论

采用 **内嵌 CPython + 复用现有 FastAPI 与 `web/` 前端**：app 在自身沙盒里用 `uvicorn` 监听 `127.0.0.1`，`WKWebView` 加载 `http://127.0.0.1:<port>`。

理由：后端约 2.35 万行 Python、19 个模块，前端约 6000 行 JS；前端全部通过同源 `/api/v1` 访问，服务一旦在手机本机跑起来，`web/` 与模块前端不需要改写。原生重写（SwiftUI + URLSession）意味着把 19 个模块的业务逻辑重做一遍，不适合当前阶段。

`ios/shell/campusMate/Info.plist` 已有 `NSAllowsLocalNetworking`，本机 HTTP 不需要额外 ATS 例外。

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

## AI：已定为纯 Python

比较过三条路，最终选了第 1 条：

| 方案 | 结论 |
| --- | --- |
| 纯 Python 直连模型（**采用**） | `AIService` 用 `httpx` 调 DeepSeek 与任意 OpenAI 兼容端点；插件工具降级 |
| nodejs-mobile 内嵌 Harness | `@deepseek-ai/dsh` 要求 Node ≥ 24.9；nodejs-mobile 最新只到 18.20.4，社区 PR #158 移植到 24.5 仍未合并，且需自行编译 V8（本次实测 6 核机器 3 小时仍未编完） |
| 远程 Harness | 违背"本地运行"，保留为将来的可选增强 |

实现要点：

- `provider.complete`（DeepSeek 官方）与 `provider.complete_openai`（自定义网关）都做了容错 JSON 解析：
  去 ```` ```json ```` 围栏、截取首尾花括号、双层编码解一次；
- 失败重试 429/5xx/超时（3 次，1s/3s 退避），这是长批量分类能跑完的关键；
- 无插件工具时：`AIService.supports_tools = False`，邮箱分类直接用模型输出的 decision、主页学习助手
  直接填充 `task.answer`、AI 助手过滤模型编造的 citation_id 后重试一次。

## 分阶段计划

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 内嵌 CPython 启动 `uvicorn`，`WKWebView` 打开首页 | ✅ 真机跑通 |
| P1 | 交叉编译 5 个原生依赖，`import` 全通过 | ✅ 见下文 |
| P2 | WKWebView 登录 + Cookie 桥；Keychain 替 Vault | ✅ Cookie 桥 / ⏳ Keychain 未做（沙盒直通） |
| P3 | AI 改纯 Python；不打包 `group-messages` | ✅ 问答可用（插件工具降级） |
| P4 | 后台刷新、通知、真机验证 | ✅ 后台刷新 + 本地通知；持续观察系统调度频次 |

CI 已能在 `macos-latest` 上构建（`.github/workflows/ios.yml`），P0 起可加一个模拟器构建 job 防回归。

## P1 进展：三个原生 wheel + PDFKit 替代

已产出（`.codex/wheelhouse/`，全部 `platform=iOS`、`minos 16.0`、cp313）：

| wheel | 说明 |
| --- | --- |
| `pydantic_core-2.50.1-cp313-cp313-ios_16_0_arm64_iphoneos.whl` | Rust/pyo3；FastAPI 链路上唯一的原生模块 |
| `zstandard-0.25.0-...whl` | 纯 C 扩展，内嵌 zstd 源码，无外部依赖 |
| `pillow-12.3.0-...whl` | 只带 zlib（JPEG/TIFF/WebP/freetype 关闭）；`_imaging`、`_imagingmath`、`_imagingmorph`、`_imagingtk` |
| `cryptography-50.0.2-cp39-abi3-...whl` | Rust/pyo3 abi3，静态链接自建的 OpenSSL 4.0.3 |
| `cffi-2.1.1-...whl` | `_cffi_backend`，静态链接自建的 libffi 3.8.0（cryptography 的 Rust 模块在导入时就要它） |

复现脚本：

```bash
ios/local/tools/build_pydantic_core.sh   # cargo + 手工组装 wheel
ios/local/tools/build_c_wheels.sh all    # zstandard + pillow（setuptools）
ios/local/tools/build_cryptography.sh    # OpenSSL(ios64-cross) + cryptography
ios/local/tools/build_cffi.sh            # libffi + cffi（cryptography 运行时依赖）
ios/local/tools/assemble_wheel.py        # 通用 wheel 组装（RECORD/WHEEL）
```

踩过的坑（都写进脚本注释了）：

1. **pyo3 交叉编译**需要目标 Python 的 prefix：`lib/libpython3.13.dylib`、`lib/python3.13/_sysconfigdata__ios_arm64-iphoneos.py`、`include/python3.13/`，
   并设置 `PYO3_CROSS=1 PYO3_CROSS_PYTHON_VERSION=3.13 PYO3_CROSS_LIB_DIR=<prefix>`；
   `maturin --target` 会报平台不匹配，`cibuildwheel --platform ios` 要求系统装 python.org Framework 版 CPython，都不适用于本机。
2. **Pillow 12 的 `_imaging` 依赖 `libpil_imaging_mode.a`**，必须 `setup.py build_clib build_ext`，只跑 `build_ext` 会链接失败。
3. **cryptography 需要先自建 OpenSSL**：`openssl-sys` 不会自动为 iOS 编vendored 版本，先用 OpenSSL 自带的
   `ios64-cross` 目标（`CROSS_TOP`/`CROSS_SDK`）编出静态库，再设 `OPENSSL_DIR` + `OPENSSL_STATIC=1`；
   cffi 生成代码要 `Python.h`，所以还要给 `CFLAGS_aarch64-apple-ios` 指向目标 prefix 的 include。
4. **链接期会混进 `-lclang_rt.osx`**（macOS 编译器运行时），iOS 链接器直接报错。用
   `.codex/tools/ios-linker.sh` 过滤掉这个参数（`CARGO_TARGET_AARCH64_APPLE_IOS_LINKER`）。
5. **distutils 会注入 macOS SDK 的 lib 目录**，`-lz` 会链到 macOS 的 libz，iOS 链接器直接报
   “building for 'iOS', but linking in dylib” —— 必须把 `-L$SDKROOT/usr/lib` 放到 LDSHARED 最前面。

## P1 完成：真后端在 app 里启动

`ios/local/Sources/boot.py` 现在启动的是真正的 FastAPI 应用，不再是桩：

- `backend.core.paths.DATA` 指向沙盒 `Documents/data`（`CAMPUS_DATA_DIR`，由 Swift 在启动前 setenv）；
- `backend.core.vault` 的 DPAPI 调用被替换成直通（沙盒本身有 iOS 数据保护；Keychain 实现待做）；
- uvicorn 绑定随机回环端口并写入端口文件，`WKWebView` 随后加载；
- 纯 Python 依赖由 `ios/local/tools/stage_ios_site.sh` 从锁定的 uv 环境裁剪而来（去掉 261 MB 的
  Node runtime 和各平台二进制，换成 iOS wheel）；
- `modules/group-messages` 不打包（依赖 Windows DLL，产品上本来也不提供）。

已在本机 macOS 上用同一份代码验证：`/api/v1/health`、`/api/v1/bootstrap`、`/` 均 200，19 个模块全部加载。

## PDF 渲染：用 PDFKit 取代 pypdfium2

iOS 自带 PDFKit，没必要为 `pypdfium2`（C++ / PDFium，体积大）再造一遍。做法：

- `ios/local/Sources/PDFKitBridge.m`：三个 C 函数 `cm_pdf_page_count` / `cm_pdf_page_size` / `cm_pdf_render_page`，
  内部用 `PDFDocument` + `UIGraphicsImageRenderer` 渲染成 PNG；用 `__attribute__((used, visibility("default")))`
  配合 `-Wl,-export_dynamic` 把符号留在主可执行文件里；
- `ios/local/Sources/py_extra/pypdfium2.py`：通过 `ctypes.CDLL(None)` 调这些符号，提供后端用到的
  `PdfDocument` / `page.get_size()` / `page.render(scale).to_pil()` 子集；
- 构建时该文件与 wheelhouse 一起装进 `site-packages`，后端 `import pypdfium2` 会命中这个 shim。

## 真机跑通（2026-11-12，iPadOS 26.0）

`campusMateLocal.ipa` 已在 iPad 上安装运行：启动约 10 秒后在设备本地起服务，界面、导航、主题、
校园地图、时间表均正常渲染，底部状态显示 `服务就绪 :<port>`，页面探测 `errors: []`。

跑通的完整链路：

```
Swift 启动 → 设置 CAMPUS_DATA_DIR 到 Documents/data
          → fd 级重定向 stderr/stdout 到 python.log
          → cm_start_python（PyConfig: home/executable/argv）
          → boot.py：补丁 Vault、创建 uvicorn 应用
          → 端口写文件 → Swift 健康检查 /api/v1/health
          → WKWebView 加载 http://127.0.0.1:<port>/
```

一路踩到的坑（都已修复并有回归日志）：

| 现象 | 根因 |
| --- | --- |
| 启动即 `-15`，无任何日志 | `PyRun_File` 不填 `__file__`，脚本第一行就 NameError |
| 无 traceback | `sys.stderr` 在极早期失败时可能不可用，改为 C 层 `traceback.format_exception` + fd 重定向 |
| `PermissionError: .private` | `paths.py` 在 import 时就 mkdir；改为尊重 `CAMPUS_DATA_DIR` |
| `No module named '_cffi_backend'` | cryptography 的 Rust 模块导入即需要 cffi；补编 cffi + libffi |
| 白屏 | 后端未就绪但 WebView 已加载；加健康检查与页面探测 |

## 签名与扩展模块加载

iOS 不允许 `dlopen` 未被代码签名覆盖的松散 `.so`。BeeWare 的 CPython 为此内置了
`.fwork` 约定：把扩展模块放进 `Frameworks/<name>.framework/<name>`，并在原位置留一个
`<name>.so.fwork` 指向它，同时框架内留 `<name>.origin` 指回占位文件。

`ios/local/tools/convert_dylibs.sh` 在构建期把所有 `python/**/*.so` 转成框架（本机实测 75 个），
`Sources/PythonBridge.c` 把 `sys.executable` 设成 app 根目录的二进制——importlib 用
`dirname(sys.executable)` 解析 `.fwork` 里的相对路径。

`boot.py` 会在 `Documents/data/boot.log` 记录启动过程；Python 初始化失败时（桥接返回 15）
先看这个文件。

## 已核实的外部事实（2026-11-10）

- PyPI 上 `pydantic-core`、`cryptography`、`pillow`、`zstandard`、`pypdfium2` **均无 iOS 轮子**（0 个 `ios_*` wheel），必须自行交叉编译。
- `cibuildwheel` 文档已提供 iOS 构建与版本兼容说明。
- Python-Apple-support 最新 `3.15-b3`（2026-10-26），稳定线 `3.14-b14`；Briefcase `v0.4.7`。
- `nodejs-mobile` 最新 `v18.20.4`（2024-10-07）。

## 日历导入（2026-11）

`.ics` 不再走下载：页面拦截 `a[href$=".ics"]` 的点击 → `fetch` 文本 → `window.webkit.messageHandlers.calendar`
交给原生 → `ICSImporter` 解析 VEVENT → EventKit 写入默认日历。

- 权限：`requestFullAccessToEvents`（iOS 17+），Info.plist 声明 `NSCalendarsFullAccessUsageDescription`；
- 去重：导出的 UID 写进事件备注（`campusMate:<uid>`），重复导入跳过已有；
- 踩过的坑：ICS 用 CRLF，解析时先按 `\r\n` 切分再按 `\n` 切分会让每个值带上尾部 `\r` 并覆盖
  DTSTART，导致"6 个 VEVENT 解析出 0 个"。

## 后台与通知（2026-11）

- `BGAppRefreshTask`（`ios/local/Sources/BackgroundRefresh.swift`），在 `AppDelegate` 注册，进后台与
  回前台各重排一次；一次约 30 秒，做"同步邮件/作业/时间表 → 生成通知 → 读取快照 → 投递本地通知"；
- 通知去重按通知 id 存在 UserDefaults，保留最近 400 条；
- 后台刷新是系统机会式调度（通常每天几次），App 被划掉后不再唤醒；即时推送需要 APNs；
- 回前台时页面若在 Python 绑定端口前加载失败，会自动重试（最多 12 次、每秒一次）。

## 开发者模式（仅 dev）

`web/app.js` 在 `bootstrap.dev` 为真时往侧边栏追加"开发者模式"入口，面板里可以：发测试通知、手动跑一次
后台同步、导入示例日历、重载页面。

`dev` 来自 `CAMPUS_DEV_BUILD`，只有 Debug 构建在 `LocalRuntime.start()` 里设置；Release 构建会 `unsetenv`，
原生侧 `dev` 消息处理器也只在 `#if DEBUG` 注册。规则见 [../ios/DEVELOPMENT.md](../ios/DEVELOPMENT.md)。

## 版本与产物

| 产物 | 路径 | 说明 |
| --- | --- | --- |
| dev | `ios/local/campusMate-dev.ipa` | 日常开发，`0.x.y`，带 DEV 徽章 |
| 正式 | `ios/ipa/campusMate.ipa` | 合并 `main` 后用 `CAMPUS_RELEASE=1 ./build_local.sh release` 构建，`1.x.y` |

Bundle ID 固定：`edu.shanghaitech.campusmate.local`（正式）/ `...local.dev`（dev），覆盖安装依赖这一点。

## 现状

- 真机（iPadOS 26.x）运行正常：本地服务、课程、时间表、作业、邮箱、通知、AI 问答；
- 已实现纯 Python AI、EventKit 日历导入、后台刷新与本地通知、dev 开发者模式；
- 未完成：Keychain 版 Vault（当前为沙盒直通）、Harness 插件工具、APNs 即时推送。
