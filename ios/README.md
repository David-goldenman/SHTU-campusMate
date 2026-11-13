# iOS 客户端

两个平级的 Xcode 工程，互不包含：

```
ios/
  shell/   网络外壳：WKWebView 连接电脑上 `run.cmd --share` 的工作台
  local/   本地版：app 内嵌 CPython + FastAPI，设备上独立运行
```

| | `shell/` | `local/` |
| --- | --- | --- |
| 后端在哪 | 电脑（同一 Wi-Fi） | app 自己的沙盒 |
| 构建 | `cd shell && ./build_ipa.sh` | `cd local && ./build_local.sh [release\|dev]` |
| 产物 | `shell/campusMate.ipa` | `local/campusMate.ipa` / `local/campusMate-dev.ipa` |
| CI | `.github/workflows/ios.yml` 自动构建 | 本机构建（依赖 `.codex/wheelhouse` 的 iOS wheel） |
| 说明 | [shell/README.md](shell/README.md) | [../docs/IOS_LOCAL.md](../docs/IOS_LOCAL.md) |

两者共用仓库根的 `web/` 前端；`local/` 另外打包 `backend/`、`modules/` 和纯 Python 依赖。

本地版的原生依赖（pydantic-core、zstandard、pillow、cryptography、cffi）需要用 `local/tools/` 下的脚本
交叉编译成 iOS wheel，放在 `.codex/wheelhouse/`；构建时自动装进 `site-packages`。
