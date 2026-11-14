# iOS 客户端

两个平级的 Xcode 工程，互不包含：

```
ios/
  shell/   网络外壳：WKWebView 连接电脑上 `run.cmd --share` 的工作台
  local/   本地版：app 内嵌 CPython + FastAPI，设备上独立运行
  ipa/     正式版产物目录（campusMate.ipa，合并 main 后构建）
```

| | `shell/` | `local/` |
| --- | --- | --- |
| 后端在哪 | 电脑（同一 Wi-Fi） | app 自己的沙盒 |
| 构建 | `cd shell && ./build_ipa.sh` | `cd local && ./build_local.sh` |
| 产物 | `shell/campusMate.ipa` | `local/campusMate-dev.ipa`（dev）/ `ipa/campusMate.ipa`（正式） |
| 版本 | 跟随 `backend/core/config.py` 的 `VERSION` | `0.x.y`（dev）/ `1.x.y`（正式） |
| CI | `.github/workflows/ios.yml` 自动构建 | 本机构建（依赖 `.codex/wheelhouse` 的 iOS wheel） |
| 说明 | [shell/README.md](shell/README.md) | [../docs/IOS_LOCAL.md](../docs/IOS_LOCAL.md) |

两者共用仓库根的 `web/` 前端；`local/` 另外打包 `backend/`、`modules/` 和纯 Python 依赖。

## 先读这个

[DEVELOPMENT.md](DEVELOPMENT.md) 是这行的开发规范，架构取舍见
[docs/architecture/0002-ios-local.md](../docs/architecture/0002-ios-local.md)：版本号怎么走、什么时候能出正式版、Bundle ID 为什么不能改、缓存怎么处理。改动前先看。

要点：

- 开发期**只构建 dev 版**，正式版 IPA 只在合并 `main` 之后构建；
- 版本号改动只改 `ios/local/project.yml` 的 `MARKETING_VERSION`，**Bundle ID 永远不变**；
- 覆盖安装会保留缓存，启动时按二进制时间戳清理 WKWebView 缓存。

## 本地版现在能做什么

| 能力 | 说明 |
| --- | --- |
| 本地服务 | app 内启动 FastAPI + uvicorn，监听 `127.0.0.1` 随机端口 |
| 校园功能 | 课程、时间表、作业、邮箱、通知、AI 助手 |
| AI | 无 Harness：DeepSeek 直连 HTTP，其他 OpenAI 兼容端点走「自定义模型 API」；插件工具降级为无工具回答 |
| 日历 | `.ics` 导出由页面 fetch 后交给 EventKit 直接写入系统日历（去重、可重复导入） |
| 后台 | `BGAppRefreshTask` 定期同步邮件/作业/时间表并生成通知；本地通知未读条目 |
| 开发者模式 | **仅 dev 构建**的侧边栏面板：测试通知、手动后台同步、示例日历、重载页面 |

## 原生依赖

本地版的原生依赖（pydantic-core、zstandard、pillow、cryptography、cffi）需要用 `local/tools/` 下的脚本
交叉编译成 iOS wheel，放在 `.codex/wheelhouse/`；构建时自动装进 `site-packages`。
