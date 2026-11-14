# 0002 · iOS 本地运行（`ios/local`）

状态：已实施（2026-11）。取代早先"只用网络外壳连电脑"的唯一方案。

## 背景

`ios/shell` 是一个 WKWebView 外壳，后端仍在电脑上；离开电脑就不可用。目标是在设备上独立运行整套
campusMate：课程、作业、邮件、时间表、通知与 AI 问答，且不依赖任何桌面进程。

## 决策

1. **内嵌 CPython 复用现有后端与前端**，而不是用 SwiftUI 重写 19 个模块。
   - 运行时：BeeWare `Python-Apple-support` 的 `Python.xcframework`；
   - 服务：`boot.py` 里启动既有 FastAPI + uvicorn，监听 `127.0.0.1` 随机端口；
   - 界面：`WKWebView` 加载本机地址，前端与 `/api/v1` 契约完全不变。
2. **原生依赖交叉编译**：pydantic-core、zstandard、pillow、cryptography、cffi 由 `ios/local/tools/`
   下的脚本产出 iOS wheel，构建期装进 `site-packages`；PDF 渲染用 PDFKit 桥替代 pypdfium2。
3. **不运行 Harness 插件**：`@deepseek-ai/dsh` 要求 Node ≥ 24.9，而 nodejs-mobile 最新只到
   Node 18.20.4（社区 PR #158 移植到 24.5，未合并且需自行编译 V8）。因此 AI 走纯 Python HTTP，
   插件工具降级为无工具回答。
4. **登录用 `WKWebView` 容器**：`SFSafariViewController` 拿不到 Cookie；`WKWebView` 可以
   `getAllCookies()` 后导入 Python 的 CookieJar。
5. **`.ics` 直接写日历**：iOS 对下载的 `.ics` 只提供分享面板，改为页面 `fetch` 后交给原生
   EventKit 解析写入，按导出 UID 去重。
6. **后台用 `BGAppRefreshTask`**：后台唤醒时同步邮件/作业/时间表并投递本地通知；受系统调度限制，
   不做"常驻服务"的承诺。
7. **数据与凭据留在沙盒**：`CAMPUS_DATA_DIR=Documents/data`；Vault 由 DPAPI 改为沙盒直通
   （Keychain 实现仍待做）。

## 后果

- 单包体积约 38 MB（Python + 纯 Python 依赖 + iOS wheel），不含 Node；
- AI 插件工具不可用，`academic-assistant`、`mail` 等模块在 iOS 上走无工具兜底；
- 后台同步是机会式的（系统决定频次），即时推送需要另加 APNs；
- dev 与正式版用不同 Bundle ID 并存，版本线与产物目录见 [ios/DEVELOPMENT.md](../../ios/DEVELOPMENT.md)。

## 相关

- 实施细节：[docs/IOS_LOCAL.md](../IOS_LOCAL.md)
- 工程结构：[ios/README.md](../../ios/README.md)
