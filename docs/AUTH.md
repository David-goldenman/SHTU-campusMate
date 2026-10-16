# 共享认证服务

框架提供 Gradescope、Piazza、学校 IDS 与 Coremail 四个独立认证提供方。认证层保存账号与会话、完成登录与二次验证、向 Python 模块提供已验证的 HTTP 客户端；具体课程、邮件与文件功能由各模块实现。提供方 ID 固定为 `gradescope`、`piazza`、`ids`、`coremail`。IDS 的登录目标固定为 `blackboard`、`elrc`、`timetable`，默认 `blackboard`。

## HTTP 接口

服务默认地址为 `http://127.0.0.1:16666`，接口说明见 `/api/docs`，结构见 `/api/openapi.json`。写操作先读取 `GET /api/v1/bootstrap` 的 `csrf_token`，放入 `X-Framework-Token` 请求头；浏览器使用同源访问。全部认证接口只返回状态，账号密码、Cookie、sid 与令牌在进程内部使用。

| 方法与路径 | 请求 | 返回 |
| --- | --- | --- |
| `GET /api/v1/auth/providers` | 无 | `{providers: [...]}` |
| `GET /api/v1/auth/{provider}/status` | 无 | 单个提供方状态 |
| `PUT /api/v1/auth/{provider}/credentials` | `{username, password}` | 保存后的状态；保存会清除旧会话 |
| `POST /api/v1/auth/{provider}/login` | `{target?}` 或空请求体 | 密码登录并验证后的状态 |
| `POST /api/v1/auth/{provider}/browser` | `{target?}` 或空请求体 | 打开独立验证窗口后的状态 |
| `POST /api/v1/auth/{provider}/import-session` | `{target?}` 或空请求体 | 探测、加密导入并关闭窗口后的状态 |
| `DELETE /api/v1/auth/{provider}` | 无 | 清除该提供方账号、会话与验证窗口后的状态 |

`target` 仅用于 IDS。验证窗口与导入接口应指定相同目标，例如 `{"target":"elrc"}`。窗口直接打开固定原站；用户在原站完成验证码、短信或其他二次验证，再调用导入接口。Coremail 通过该流程登录。其他提供方可先尝试密码登录，需要验证时转入窗口。

状态响应示例使用合成账号：

```json
{
  "id": "ids",
  "name": "学校 IDS",
  "username": "synthetic-user",
  "has_password": true,
  "has_session": true,
  "status": "ready",
  "target": "elrc",
  "targets": ["blackboard", "elrc", "timetable"],
  "checked_at": "2026-10-01T00:00:00+00:00"
}
```

`status` 为 `not_connected`、`login_required`、`verification_required` 或 `ready`；`message` 提供当前操作提示。`has_session` 仅表示本地保存了会话。`ready` 与 `checked_at` 表示上次固定目标探测成功，状态查询本身不联网，服务端是否已让会话失效需要下一次只读探测确认。Cookie 的到期字段无法证明会话仍有效，未知期限的会话也保留原状。

登录失败返回 401，需要验证码或浏览器验证返回 409，未知提供方返回 404，无效请求返回 400 或 422，远端连接失败返回 502。失败后读取状态接口可获取操作提示。HTTP 校验错误不回显输入的秘密。

## Python 模块接入

模块从框架注入的 `context.auth` 获取共享服务。所有请求与响应消费都留在上下文内，客户端退出后更新 Cookie 会加密写回：

```python
def read_account(context):
    with context.auth.authenticated_client("ids", target="blackboard") as client:
        response = client.get("https://elearning.shanghaitech.edu.cn:8443/learn/api/public/v1/users/me")
        response.raise_for_status()
        return response.json()
```

每次获取客户端先验证固定登录目标；发现失效时最多自动密码登录一次。密码被拒绝或出现二次验证后，自动尝试暂停，用户主动调用登录、更新凭据或成功导入会话后继续。连接失败不触发密码重试。模块收到 `LoginRequired` 或 `VerificationRequired` 时向调用方暴露该状态，由共享设置页处理登录；模块不保存密码、不复制 Cookie，也不自行弹出验证窗口。模块若在业务响应中识别出登录失效，可以抛出这两个异常，结束当前请求。

Coremail 的会话另含 sid。该参数仅供后端同源 RPC 使用，不能返回前端或记录到日志：

```python
with context.auth.authenticated_client("coremail") as client:
    params = context.auth.session_parameters("coremail")
    response = client.post(
        "https://mail.shanghaitech.edu.cn/coremail/s/json",
        params={**params, "func": "user:getAttrs"},
        json={"optionalAttrIds": []},
    )
    response.raise_for_status()
```

客户端统一管理 Cookie，请求应使用原站 HTTPS 地址，不手动设置 Cookie 头或传入每次请求的 Cookie。导入与写回会筛选提供方所属域名，保留 Secure、HttpOnly、SameSite、Path、Expires 和 host-only 属性；发出请求时执行严格的主机范围策略。HttpOnly 与 SameSite 是浏览器属性，Python 客户端保存这些属性用于会话往返。

后台来源可传入 `authenticated_client(provider, target=..., cancelled=threading.Event())`。等待共享账号锁期间会检查取消事件；模块停止后无需等待其他 IDS 来源完成全部同步。返回状态中的 `account_revision` 在保存账号、导入会话和忘记登录时更新，用于隔离来源缓存。

## 存储与清理

`backend/core/vault.py` 的 `Vault` 默认写入项目 `.private/vault.dpapi`，使用 Windows DPAPI `CurrentUser` 加密整份 JSON，先写加密临时文件再原子替换。`get()` 返回副本，`save()`、`delete()`、`delete_prefix()` 与 `clear()` 统一管理秘密。认证键为 `auth:credentials:{provider}` 和 `auth:session:{provider}`；账号、密码、Cookie、sid 与其他密钥全部留在加密 Vault。普通认证状态写入 Store 的 `auth:state:{provider}`，其中只含状态、提示、阻断标志与探测时间。DPAPI 文件与当前 Windows 账号绑定，运行于该账号或启用 Windows 互操作的 WSL。

验证浏览器的临时用户目录固定在项目 `.codex/auth/{provider}`。成功导入会话、删除提供方或正常退出服务时，先关闭框架创建的独立窗口，再删除该目录中的 Cookie、localStorage 与缓存。导入失败时保留窗口供用户继续验证；下次重新打开验证窗口会处理上次留下的目录。`.private` 与 `.codex` 均在项目忽略范围内，打包和交付不包含这两处目录。

`AuthService.clear_all()` 清除四个提供方的账号、会话、状态与验证窗口；`close()` 在服务退出时关闭窗口并清理临时目录。完整凭据清理由框架统一调用 Vault 清空方法，模块不直接打开 Vault 文件。认证开发只修改 `backend/services/auth/`、`backend/core/vault.py`、`scripts/browser.mjs`、`scripts/dpapi.ps1` 及对应文档和检查。

## 验证范围

`checks/check_auth.py` 使用合成凭据和模拟原站，检查 DPAPI 往返与原子落盘、Cookie 的安全属性及主机范围、一次自动重登、失败与二次验证后暂停、导入筛选、状态输出和独立清理。运行项目 `check.sh`，或在项目 uv 环境中执行该检查。真实账号与二次验证需要用户在本项目独立初始化，实际会话有效性由固定只读登录探测确认。
