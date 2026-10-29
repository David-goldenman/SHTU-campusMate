# 自动检查与 main 合并约定

## 自动检查

`.github/workflows/ci.yml` 对发往 main 的 PR 创建、更新、重新打开和转为可审核状态，以及 main 的每次推送执行检查；也支持 Actions 页面手动运行。不按文件路径跳过检查，新推送取消同一 PR 的旧执行。

稳定检查名称为 **CI required**。Windows Server 2025 托管 runner 使用 Python 3.12、Node.js 22.23.3、pnpm 11.22.0 和 uv 0.13.0，按 `uv.lock` 安装依赖。Actions 固定到发布提交，工作流只有读取仓库内容的权限，不保存 checkout 凭据，不需要学校账号、AI Key 或仓库自定义 secret。

本地 Windows 的 `./check.ps1`、WSL 的 `bash check.sh` 与 CI 共同调用 `checks/run_checks.py`：自动发现 `checks/check_*.py`、`modules/*/checks/check_*.py`，覆盖框架、模块独立启停、依赖缺失、空框架、账号隔离、真实 Windows DPAPI、官方 Harness 原生插件、手机分享配对、iOS 外壳文件与各来源合成协议检查；另执行前端清理、设备引导、Windows 启动器检查及 JavaScript 语法检查。任一检查失败即失败，不允许以跳过或忽略错误得到通过结果。

`checks/check_ipa.py` 只读校验 `ipa/` 的工程定义、版本同步、图标尺寸与 alpha、Info.plist 的本地网络例外、配对默认值和打包脚本换行，不需要 macOS。`.github/workflows/ios.yml` 另行在 `macos-14` 上执行 `ipa/build_ipa.sh`，真实编译 SwiftUI 外壳并产出未签名 `.ipa`，仅由 `ipa/**` 改动触发，不属于 **CI required**。

CI 的学校 HTTP 与模型响应使用合成夹具；安装依赖及 Harness 插件仍需要联网。依赖缓存只保存 uv 包缓存，不上传 `.private`、浏览器配置、测试临时目录或用户资料。交互式 Edge 登录、真实学校协议与最终网页视觉验收仍由授权成员按功能单独验证。

原生 Windows 使用 `./check.ps1`；WSL 使用 `bash check.sh`，需要现有 Windows 互操作、Node.js 及 pnpm。两种入口均按锁定文件安装开发依赖。

## 四人合并约定与当前限制

每位成员从 main 建立功能分支、提交 PR。查看当前提交的 **CI required**，由另一位有写权限的成员审核，再合并；推送新修改后重新检查与审核。作者不能批准自己的 PR。管理员也遵守此流程。

2026-10-16 GitHub 管理 API 对本私有仓库的分支保护与 rulesets 均返回 403：当前套餐不支持这项能力。用户选择保持私有并先接入 CI。因此 **自动检查可运行，但“检查通过且有人审核才能合并”目前不是服务器强制门槛**；写权限成员仍可能直接推送或绕过团队约定。工作流本身不能替代分支保护。

`.github/main-protection.json` 保存待启用的完整规则：要求最新 main 上的 `CI required`（GitHub Actions 来源）、至少 1 人审核、最后一次推送由他人批准、更新提交撤销旧批准、解决全部讨论、管理员同样受约束，禁止强推与删 main。

账号具备支持私有仓库保护的权益后，管理员在仓库目录执行以下命令，并核对 API 返回结果：

```powershell
gh api --method PUT repos/David-goldenman/Shanghaitech-2026-Hackthon/branches/main/protection --input .github/main-protection.json
gh api repos/David-goldenman/Shanghaitech-2026-Hackthon/branches/main/protection
```

只有返回成功且读取到上述规则，才能把文档状态更新为“强制启用”。这不是购买、公开仓库或增加账户权限的自动流程。

## 失败处理与回退

点开失败检查查看具体步骤，修复后推送同一 PR；网络故障可在 Actions 重跑。不要通过改名、删检查或忽略失败来合并。工作流升级有回归时，通过普通 PR 恢复上一版工作流及检查入口，保留稳定的检查名称；已启用的分支保护继续要求审核和检查。保护配置变更应单独审阅并保存变更前的 API 配置，按保存的配置恢复后再次读取确认。

参考：[GitHub 私有仓库分支保护可用范围](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[保护 API](https://docs.github.com/en/rest/branches/branch-protection)、[uv 的 Actions 接入](https://docs.astral.sh/uv/guides/integration/github/)。
