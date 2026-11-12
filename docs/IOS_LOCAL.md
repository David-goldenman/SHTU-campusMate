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

## P1 进展：三个原生 wheel + PDFKit 替代

已产出（`.codex/wheelhouse/`，全部 `platform=iOS`、`minos 16.0`、cp313）：

| wheel | 说明 |
| --- | --- |
| `pydantic_core-2.50.1-cp313-cp313-ios_16_0_arm64_iphoneos.whl` | Rust/pyo3；FastAPI 链路上唯一的原生模块 |
| `zstandard-0.25.0-...whl` | 纯 C 扩展，内嵌 zstd 源码，无外部依赖 |
| `pillow-12.3.0-...whl` | 只带 zlib（JPEG/TIFF/WebP/freetype 关闭）；`_imaging`、`_imagingmath`、`_imagingmorph`、`_imagingtk` |
| `cryptography-50.0.2-cp39-abi3-...whl` | Rust/pyo3 abi3，静态链接自建的 OpenSSL 4.0.3 |

复现脚本：

```bash
ipa/local/tools/build_pydantic_core.sh   # cargo + 手工组装 wheel
ipa/local/tools/build_c_wheels.sh all    # zstandard + pillow（setuptools）
ipa/local/tools/build_cryptography.sh    # OpenSSL(ios64-cross) + cryptography
ipa/local/tools/assemble_wheel.py        # 通用 wheel 组装（RECORD/WHEEL）
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

## PDF 渲染：用 PDFKit 取代 pypdfium2

iOS 自带 PDFKit，没必要为 `pypdfium2`（C++ / PDFium，体积大）再造一遍。做法：

- `ipa/local/Sources/PDFKitBridge.m`：三个 C 函数 `cm_pdf_page_count` / `cm_pdf_page_size` / `cm_pdf_render_page`，
  内部用 `PDFDocument` + `UIGraphicsImageRenderer` 渲染成 PNG；用 `__attribute__((used, visibility("default")))`
  配合 `-Wl,-export_dynamic` 把符号留在主可执行文件里；
- `ipa/local/Sources/py_extra/pypdfium2.py`：通过 `ctypes.CDLL(None)` 调这些符号，提供后端用到的
  `PdfDocument` / `page.get_size()` / `page.render(scale).to_pil()` 子集；
- 构建时该文件与 wheelhouse 一起装进 `site-packages`，后端 `import pypdfium2` 会命中这个 shim。

## 已核实的外部事实（2026-11-10）

- PyPI 上 `pydantic-core`、`cryptography`、`pillow`、`zstandard`、`pypdfium2` **均无 iOS 轮子**（0 个 `ios_*` wheel），必须自行交叉编译。
- `cibuildwheel` 文档已提供 iOS 构建与版本兼容说明。
- Python-Apple-support 最新 `3.15-b3`（2026-10-26），稳定线 `3.14-b14`；Briefcase `v0.4.7`。
- `nodejs-mobile` 最新 `v18.20.4`（2024-10-07）。

## 待定

- AI 走"纯 Python"还是"内嵌 Node"？
- 群消息模块是删除，还是保留代码但 iOS 不编译？
