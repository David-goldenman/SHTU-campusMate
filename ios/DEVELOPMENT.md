# iOS 开发规范

适用于 `ios/` 下的两个工程：`shell/`（网络外壳）与 `local/`（设备内本地版）。改动前先读本文件。

## 版本号

| 版本线 | 使用场景 | 规则 |
| --- | --- | --- |
| `0.x.y` | **dev 版**（`ios/local`，Debug 配置） | 永远锁在 `0.x.x`；每完成一个功能 `y+1`（如 0.2.0 → 0.2.1）；`x+1` 由开发者决定 |
| `1.x.y` | **正式版**（Release 配置） | 只有合并到 `main` 之后才构建；从 `1.0.0` 开始；修 bug 只动第三位（`1.0.1`） |

- 版本号只改 `ios/local/project.yml` 的 `MARKETING_VERSION`（`shell/` 的版本与 `backend/core/config.py` 的 `VERSION` 保持一致，见 `checks/check_ipa.py`）。
- **任何情况下都不改 Bundle ID**：`edu.shanghaitech.campusmate.local`（正式）与 `edu.shanghaitech.campusmate.local.dev`（dev）。开发期都是覆盖安装，包名一变就会变成另一个 App，缓存、登录状态和用户数据全部隔离。

## 构建

- **开发期只构建 dev 版**：`cd ios/local && ./build_local.sh`（默认即 dev）。
- **不得在开发期构建正式版 IPA**：`./build_local.sh release` 需要显式设置 `CAMPUS_RELEASE=1` 才会执行，产物固定写到 `ios/ipa/campusMate.ipa`（该目录只留说明文件，IPA 不进版本库）。
- dev 版与正式版靠图标（右下角 `DEV` 徽章）、名称（`campusMate dev`）和 Bundle ID 区分，其余代码完全一致。
- 每次构建都会更换二进制时间戳，App 启动时据此清理 WKWebView 缓存；服务端对页面与资源发送 `Cache-Control: no-cache`。新增缓存层时请沿用这套约定。

## dev 专属功能

dev 构建多一个侧边栏入口 **开发者模式**（`web/app.js`），里面可以发测试通知、手动跑一次后台同步、导入示例日历、重载页面。

- 开关来自后端 `GET /api/v1/bootstrap` 的 `dev` 字段，它读取 `CAMPUS_DEV_BUILD` 环境变量；
- 只有 Debug 构建在 `LocalRuntime.start()` 里设置该变量（`#if DEBUG`），Release 构建会 `unsetenv`；
- 原生侧的消息处理器 `dev` 也只在 `#if DEBUG` 注册；
- **正式版必须没有这个入口**：新增 dev 功能时，服务端与原生侧都要保持"Release 下不可达"，不能只靠界面隐藏。

## 后台与通知

- 后台同步由 `BGAppRefreshTask` 驱动（`Sources/BackgroundRefresh.swift`），在 `AppDelegate` 里注册，进后台与回前台都会重排；
- 一次后台任务约 30 秒，只做"同步 + 读通知快照 + 投递本地通知"，失败的下次再来；
- iOS 不允许常驻后台，通知时效由系统调度决定；需要即时推送时只能引入服务端 APNs；
- 新增后台动作时保持幂等，并在 `BackgroundRefresh.pass()` 里按"可选调用"处理模块未启用的 404/409。

## 发布

1. 功能在 dev 版验证通过、版本号已递增；
2. 合并到 `main`；
3. 在 `main` 上设置 `CAMPUS_RELEASE=1 ./build_local.sh release` 生成 `1.x.y`；
4. 后续修复只递增第三位。

## 目录

```
ios/
  README.md                 两个工程的对照与当前能力
  DEVELOPMENT.md            本文件
  shell/                    网络外壳（WKWebView + 电脑上的后端）
    build_ipa.sh
  ipa/                      正式版产物目录（README 说明用途，IPA 被 gitignore）
  local/                    本地版（内嵌 CPython + FastAPI）
    build_local.sh          默认 dev；release 需要 CAMPUS_RELEASE=1，输出到 ../ipa
    Sources/LocalRuntime.swift      启动 Python、端口发现、缓存清理
    Sources/LocalWebView.swift      页面加载、登录桥、.ics 拦截、恢复重试
    Sources/BackgroundRefresh.swift 后台同步与本地通知
    Sources/ICSImporter.swift       EventKit 日历导入
    tools/                          原生依赖的 iOS 交叉编译脚本
```

两个工程平级，互不包含；共用仓库根的 `web/`，本地版另外打包 `backend/`、`modules/` 与 iOS wheel。
