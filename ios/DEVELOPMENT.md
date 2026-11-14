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
- **不得在开发期构建正式版 IPA**：`./build_local.sh release` 需要显式设置 `CAMPUS_RELEASE=1` 才会执行，构建产物 `campusMate.ipa` 不应留在工作区。
- dev 版与正式版靠图标（右下角 `DEV` 徽章）、名称（`campusMate dev`）和 Bundle ID 区分，其余代码完全一致。
- 每次构建都会更换二进制时间戳，App 启动时据此清理 WKWebView 缓存；服务端对页面与资源发送 `Cache-Control: no-cache`。新增缓存层时请沿用这套约定。

## 发布

1. 功能在 dev 版验证通过、版本号已递增；
2. 合并到 `main`；
3. 在 `main` 上设置 `CAMPUS_RELEASE=1 ./build_local.sh release` 生成 `1.x.y`；
4. 后续修复只递增第三位。

## 目录

```
ios/
  shell/   网络外壳（WKWebView + 电脑上的后端）
  local/   本地版（内嵌 CPython + FastAPI）
```

两个工程平级，互不包含；共用仓库根的 `web/`，本地版另外打包 `backend/`、`modules/` 与 iOS wheel。
