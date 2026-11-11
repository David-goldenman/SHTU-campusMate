# iPhone / iPad 客户端（campusMate.ipa）

## 它是什么

`ipa/` 里是一个原生 SwiftUI + WKWebView 外壳，打开电脑上运行的同一套工作台：同一个 HTTP 接口、同一份课表与作业数据。后端仍然跑在电脑上——它依赖 Windows 凭据保护、Node.js 学校登录窗口和本地文件，这些无法塞进 iOS，所以手机里不启动 Python 服务。

依赖电脑端登录状态的功能（微信群、QQ 群消息）暂不在手机端实现，仍在电脑上使用；手机端也不缓存任何学校账号密码。

## 手机与电脑怎么连

1. 电脑上运行 `run.cmd --share`。分享只支持原生 Windows 后端：`--distro`/WSL 不会把端口暴露到局域网，因此这两个开关不能同时用。
2. 启动窗口会打印 `campusMate 手机端: http://192.168.x.x:16666  配对码: ab12cd34`，同样的内容临时写入 `.private/runtime/launcher/share.json`，服务退出时删除。电脑装了虚拟机、VPN 或多块网卡时会显示多个地址（用 ` / ` 分隔），逐个尝试：虚拟网卡的地址从手机连不通，真实 Wi-Fi 地址通常以 `192.168.` 或 `10.` 开头。
3. 让 iPhone/iPad 与电脑连接同一个 Wi-Fi，打开 app，填写窗口里的地址与 8 位配对码。
4. 配对码保存在电脑的 `.private/settings.sqlite3`，只有“清空全部数据”才会重新生成；手机端把地址和配对码存在 `UserDefaults`，随时可以用顶栏齿轮按钮修改。

安全边界：

- 不加 `--share` 时后端只监听 `127.0.0.1`，Host 白名单与 CSRF 校验和以前一致。
- 加了 `--share` 才监听 `0.0.0.0`；非回环 Host 必须是私有地址（`10/8`、`172.16/12`、`192.168/16`、`fc00::/7`、链路本地或 `.local`）并携带配对码，写请求仍然需要 `X-Framework-Token`。
- 配对码通过 `?pair=` 换成 `HttpOnly` + `SameSite=strict` 的 cookie 后立即重定向，地址栏不留痕。
- 没有 HTTPS，只在可信 Wi-Fi 下开启 `--share`；公共网络请保持默认的本机模式。

## 构建

需要 macOS + Xcode 15 及以上 + [XcodeGen](https://github.com/yonaskolb/XcodeGen)（`brew install xcodegen`）。

```bash
cd ipa
./build_ipa.sh                              # 未签名产物
CAMPUS_IOS_TEAM=XXXXXXXXXX ./build_ipa.sh   # 用自动描述文件签名
```

产物是 `ipa/campusMate.ipa`，归档和导出中间文件都在 `ipa/build/`（已被 `.gitignore` 忽略，不随仓库提交）。

`project.yml` 由 XcodeGen 生成 `ipa/campusMate.xcodeproj`（与 `INFOPLIST_FILE` 的相对路径一致，已被 `.gitignore` 忽略）；也可以自己 `xcodegen generate` 后用 Xcode 打开、选真机 Archive。Bundle id 默认 `edu.shanghaitech.campusmate`，换成自己的团队前缀只需要改 `project.yml` 的 `PRODUCT_BUNDLE_IDENTIFIER`。

版本号 `MARKETING_VERSION` 必须与 `backend/core/config.py` 的 `VERSION` 保持一致，`checks/check_ipa.py` 会校验这一点。

## 安装

- 已签名：Xcode 的 Window → Devices and Simulators 拖入，或用 Apple Configurator、AltStore 等侧载工具。
- 未签名：只能作为构建产物留存；安装前需要用自己的证书重签。
- 免费 Apple ID 的签名 7 天过期，重新侧载一次即可，app 内的地址与配对码不会丢。

## 目录

```
ipa/
  project.yml             XcodeGen 工程定义（bundle id、版本、签名风格）
  build_ipa.sh            归档 + 打包：未签名与签名两条路径
  ExportOptions.plist     签名导出的参数
  campusMate/
    CampusMateApp.swift   入口
    ContentView.swift     顶栏、离线提示、设置入口
    SetupView.swift       地址与配对码表单
    CampusWebView.swift   WKWebView 外壳：同源限制、下载分享、JS 弹窗
    ServerSettings.swift  地址解析、配对码校验、UserDefaults 持久化
    Info.plist            ATS 本地网络例外、启动画面、方向
    Assets.xcassets       1024 图标与启动色
  tools/make_app_icon.py  从 web/brand 生成无 alpha 的 1024 图标
```

外壳负责把网页能力补齐：

- 只允许留在配对电脑的 origin 内，外部链接交给 Safari；
- `target=_blank` 在同一视图打开；
- `.ics` 导出走 `WKDownload`，完成后弹系统分享面板，可直接存到“文件”或导入日历；
- `alert` / `confirm` / `window.prompt`（密码生成器用到）都有原生弹窗；
- 页面加载失败显示离线提示与重试按钮。

## 本地原型（P0，`ipa/local/`）

`ipa/local/` 是「在手机上自己跑」的第一版：内嵌 CPython（BeeWare 的
[Python-Apple-support](https://github.com/beeware/Python-Apple-support)），启动后用标准库
`http.server` 在 `127.0.0.1` 提供打包进 app 的 `web/`，`WKWebView` 直接加载本机地址，不需要电脑。

```bash
# 一次性：把 Python.xcframework 放到 ipa/local/
curl -L https://github.com/beeware/Python-Apple-support/releases/download/3.13-b18/Python-3.13-iOS-support.b18.tar.gz |
    tar xz -C ipa/local
cd ipa/local && ./build_local.sh          # 产物 ipa/local/campusMateLocal.ipa
```

现状与限制：

- 已实现：本地起服务、加载真实前端、主题目录、`/api/v1/bootstrap`、`/settings`、`/themes`、`/health`；
- 未实现：业务模块（作业、课程、邮箱、AI 等）仍返回 503——它们依赖的 `pydantic-core`、`cryptography`
  等原生扩展需要先交叉编译到 iOS，见 [IOS_LOCAL.md](../docs/IOS_LOCAL.md)；
- 未签名产物无法安装到真机；用 Xcode 签名时，`python/lib/python3.13/lib-dynload/*.so` 也需要一并签名
  （BeeWare 的 `build/utils.sh` 提供了 `.so → framework` 的转换脚本）；
- 原型与正式外壳（`ipa/campusMate/`）互不影响，`ios.yml` 的 CI 仍只构建正式外壳。

## 已知边界

- 只能在同一个局域网内使用；跨网络需要自己加 HTTPS 反向代理，届时 `--share` 的私有地址校验会拒绝公网域名。
- 手机端不提供微信、QQ 群消息的读取或发送，这些仍依赖电脑上的登录桥接。
- 未在仓库里内置签名证书与描述文件；这两样必须由开发者本机或 CI 密钥提供。

## 检查

```bash
uv run --no-sync python checks/check_ipa.py
```

`.github/workflows/ios.yml` 会在 macOS 上真实跑一遍 `build_ipa.sh`，保证工程文件、图标和 Swift 源码始终可编译，并把未签名产物作为 `campusMate-ipa` artifact 上传，没有 Xcode 的机器可以直接下载。
