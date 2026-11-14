# 运行平台支持说明

针对「在 Linux 上启动报错」的反馈，这里说明项目实际支持的运行平台、会看到的具体错误，以及替代做法。

## 结论

campusMate 的**主程序不是跨平台 Python 应用**：它依赖 Windows 的凭据保护、浏览器自动化和本机进程能力。只有下面这些组合可以正常运行。

| 环境 | 主程序（网页工作台） | iOS 端（`ios/shell/`） |
| --- | --- | --- |
| **Windows 10/11** | ✅ 支持，`run.cmd` | ✅ 需要 macOS 构建 IPA |
| **WSL2（Windows 内）** | ✅ 支持，`run.sh` / `run.cmd --distro`，依赖 Windows 互操作 | ✅ 同上 |
| **纯 Linux / 容器 / 云主机** | ❌ 不支持 | ❌ 不支持（没有 Xcode） |
| **macOS** | ❌ 不支持主程序（缺 DPAPI / Edge 自动化） | ✅ 支持，`ios/shell/build_ipa.sh` |

这不是安装步骤的问题，也不是少装某个依赖就能解决的——见下一节的具体原因。

## 在 Linux 上会看到什么

| 报错 | 出现位置 | 原因 |
| --- | --- | --- |
| `Missing Windows tool: powershell.exe` | `./run.sh --check` | 启动检查明确要求 Windows 的 `powershell.exe` 与 `node.exe`（`run.sh` 第 8 行） |
| `需要 Windows powershell，请使用 Windows 或启用了 Windows 互操作的 WSL。` | 启动初始化 `Vault()` | 凭据加密调用 `scripts/dpapi.ps1`（Windows DPAPI），纯 Linux 没有对应的系统凭据保护（`backend/core/vault.py`） |
| `FileNotFoundError: wslpath` | 同上 | 非 Windows 分支用 `wslpath` 把路径翻译给 Windows 工具，纯 Linux 没有该命令 |
| `验证窗口未能启动，请检查 Windows Node 与 Edge。` | 连接校园服务时 | 学校统一登录用 Node + Edge 的 CDP 自动化（`scripts/browser.mjs`），Linux 上没有 Edge |
| `xcodebuild: command not found` / `Xcode command line tools are required` | `cd ios/shell && ./build_ipa.sh` | iOS 工程只能用 macOS 的 Xcode 构建；Linux 上没有任何 iOS SDK |

## 为什么必须这样

- **凭据**：`Vault` 用 Windows DPAPI 加密 `.private/vault.dpapi`，加解密通过 `scripts/dpapi.ps1` 完成；Linux 没有等价的原生能力，需要改用 Keychain / Secret Service 之类，属于未实现的功能。
- **登录**：`backend/services/auth/browser.py` 启动 Node + Edge，通过 CDP 打开学校登录页并导出 Cookie；Linux 无 Edge，也没有可用的等价流程。
- **群消息**：微信/QQ 读取依赖 Windows 本机进程与 DLL，只在 Windows 上可用（移动端本来也不提供）。
- **路径与进程**：启动脚本、`wslpath`、`powershell.exe` 调用都以 Windows 为目标平台。

## 正确的运行方式

Windows 本机：

```bat
run.cmd
```

Windows + WSL2（Docker 容器不算，容器里没有 Windows 互操作）：

```bash
run.cmd --distro          # 由启动器选择 WSL
# 或在 WSL 内：
./run.sh --check && ./run.sh
```

想在同一 Wi-Fi 下用手机浏览器打开：`run.cmd --share`（仅限原生 Windows 后端）。

## 如果你确实想在 Linux 上运行

需要替换掉上面四类平台依赖，工作量集中在：

1. `Vault` → 平台凭据库（libsecret / Keychain）；
2. 登录自动化 → 无头浏览器或纯 HTTP 登录（学校协议目前是 `auth/protocols.py` 的 HTTP 实现 + 浏览器补验证）；
3. 群消息模块 → 不启用（`modules/group-messages` 可停用）；
4. 启动脚本 → 去掉 `powershell.exe` / `wslpath` 依赖。

在 iOS 上做同类替换的逐项清单见 [在 iOS 上本地运行 campusMate](IOS_LOCAL.md)，思路与 Linux 一致：把 Windows 独占的能力换成目标平台的原生实现。

## 相关

- 启动与环境：[运行与开发指南](PROJECT_GUIDE.md)
- iOS 客户端：[ios/shell/README.md](../ios/shell/README.md)
- 平台依赖替换清单：[IOS_LOCAL.md](IOS_LOCAL.md)
