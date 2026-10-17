# 共享认证服务

框架提供 Gradescope、Piazza、学校 IDS 与 Coremail 四个独立认证提供方。认证层保存账号与会话、完成登录与二次验证、向 Python 模块提供已验证的 HTTP 客户端；具体课程、邮件与文件功能由各模块实现。提供方 ID 固定为 `gradescope`、`piazza`、`ids`、`coremail`。IDS 的登录目标固定为 `blackboard`、`elrc`、`timetable`，默认 `blackboard`。

## 用户连接流程

1. 设置 → 账号与登录 → 打开官方登录窗口。在原站完成密码、短信、验证码等验证，应用不读取输入的密码。
2. 返回点击“登录完成，连接账号”。服务验证当前账号，加密保存会话，关闭并清理临时窗口。之后同步前会检查登录状态。
3. 学校 IDS 可选“本机免密码登录”：点击“连接并绑定本机”并确认。应用沿用 QJQ 的引导顺序，自动进入学校账号安全页、点击“绑定当前设备”以触发学校身份复核；用户只完成学校要求的验证，应用检测通过后自动注册设备并关闭窗口。若学校尚未开启“生物验证”，先在学校页面开启再重试。学校新增独立的“Campus 工作台 · 本机”凭据；私钥以当前 Windows 用户的 DPAPI 加密。应用无需保存学校密码，也不复制 QJQ 或其他程序的私钥。这是软件设备凭据，不是调用 Windows Hello 的硬件生物认证。
4. 会话失效时，已绑定的 IDS 设备可自动恢复课表、Blackboard 和 ELRC 登录；密码方式按提供方支持情况恢复。二次验证或失败会暂停自动尝试，在设置显示原因。点击“检查连接与恢复”可主动重试。Coremail 使用已保存 Cookie 与 SID，服务端会话过期后在保留浏览器资料的官方窗口重新连接。Gradescope/Piazza 仅导入会话时也需重新连接，保存密码是可选项。

恢复按需触发，不持续轮询或保证永不过期。绑定结果不确定时先加密保留私钥，可点击“检查上次绑定结果”，不会连续注册设备。删除本机凭据只清除本机私钥；学校端设备需到账号安全页自行撤销。

Gradescope、Piazza 与 IDS 的卡片提供“账号密码登录”：输入账号密码，点击“保存并登录”即可完成两个步骤；服务确认保存后清空密码框。已保存密码的同一账号可留空直接登录，修改账号时必须重新填写密码。密码登录遇到二次验证时，卡片显示原因，可继续打开官方窗口并在完成后连接。每张卡片独立显示进度与结果，操作期间禁用其控件；其他账号、AI 配置及尚未提交的输入保持原状。设备绑定进度也在原卡片更新。

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
| `POST /api/v1/auth/{provider}/refresh` | `{target?}` 或空请求体 | 主动探测并允许一次恢复 |
| `POST /api/v1/auth/ids/device/browser` | 无 | 打开学校账号安全页 |
| `POST /api/v1/auth/ids/device/start` | `{confirmation:"REGISTER_THIS_DEVICE"}` | 开始可见的学校验证引导，复核通过后自动绑定；最多等待 10 分钟 |
| `POST /api/v1/auth/ids/device/bind` | `{confirmation:"REGISTER_THIS_DEVICE"}` | 用户确认后注册独立设备并连接 |
| `POST /api/v1/auth/ids/device/recover` | 无 | 验证待确认凭据，成功后启用 |
| `DELETE /api/v1/auth/ids/device` | 无 | 删除本机正式及待确认设备私钥 |
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

每次获取客户端先验证固定登录目标；发现失效时自动尝试一次设备凭据或密码登录。登录被拒绝或出现二次验证后，自动尝试暂停，用户主动检查连接、登录、更新凭据或成功导入会话后继续。连接失败不触发密码重试。模块收到 `LoginRequired` 或 `VerificationRequired` 时向调用方暴露该状态，由共享设置页处理登录；模块不保存密码、不复制 Cookie，也不自行弹出验证窗口。

后台来源同步使用 `context.auth.read_with_recovery(provider, operation, target=..., cancelled=...)`。`operation(client)` 必须是可重复的只读获取操作；当业务分页中途抛出 `LoginRequired`，服务重新登录一次并重新读取，二次验证不自动重试。`authenticated_client` 上下文自身只处理进入时的恢复，不能重放任意业务操作。

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

后台来源可传入 `authenticated_client(provider, target=..., cancelled=threading.Event())`。等待共享账号锁期间会检查取消事件；模块停止后无需等待其他 IDS 来源完成全部同步。

`account_revision` 代表服务端确认的账号归属，`session_revision` 代表会话保存次数。相同账号重新导入或续期保留账号版本；换账号则切换到独立版本，旧请求必须在回写/返回前检查版本。已识别账号再次连接可复用其版本，来源快照也可能需要重新同步。Gradescope 使用服务端用户 ID；IDS 从各来源确认学校账号；Coremail 使用 uid；Piazza 使用个人资料标识。`identity_verified` 表示已取得标识；标识映射只在加密 Vault 中保存。`automatic_recovery` 表示已有可用恢复方式，IDS 另含 `device:{configured,pending,enabled,name}`。

ELRC/Piazza 原有本地资料、关注课程和阅读状态按账号分区；首次升级只把仍可验证的原会话与既有归属关联。无法确认归属的历史缓存保留在本机，不自动归给新登录，需在当前账号重新同步。手动连接其他学校账号后，原账号的设备凭据自动停用，避免后台恢复回另一个账号。

## 存储与清理

`backend/core/vault.py` 的 `Vault` 默认写入项目 `.private/vault.dpapi`，使用 Windows DPAPI `CurrentUser` 加密整份 JSON，先写加密临时文件再原子替换。`get()` 返回副本，`save()`、`delete()`、`delete_prefix()` 与 `clear()` 统一管理秘密。认证键为 `auth:credentials:{provider}` 和 `auth:session:{provider}`；账号、密码、Cookie、sid 与其他密钥全部留在加密 Vault。普通认证状态写入 Store 的 `auth:state:{provider}`，其中只含状态、提示、阻断标志与探测时间。DPAPI 文件与当前 Windows 账号绑定，运行于该账号或启用 Windows 互操作的 WSL。

验证浏览器的固定用户目录位于 `.private/runtime/auth/{provider}`。成功导入会话或正常退出服务时关闭框架创建的独立窗口，并保留 Cookie、localStorage 与浏览器身份；删除提供方或切换账号时清除对应目录。导入失败时保留窗口供用户继续验证。私有运行数据由 Git 忽略，打包和交付按代码文件清单进行。

`AuthService.clear_all()` 清除四个提供方的账号、会话、状态与浏览器资料；`close()` 在服务退出时关闭窗口并保留资料。完整凭据清理由框架统一调用 Vault 清空方法，模块不直接打开 Vault 文件。认证开发只修改 `backend/services/auth/`、`backend/core/vault.py`、`scripts/browser.mjs`、`scripts/dpapi.ps1` 及对应文档和检查。

设备私钥与签名计数器保存在 `auth:device:ids`，待确认注册保存在 `auth:device-pending:ids`。Vault 通过进程间文件锁串行读取、修改和原子替换；设备签名期间持有事务锁，即使后续登录失败也保存已增加的计数器。账号与设备状态接口不会返回私钥、凭据 ID 或签名计数器。

## 验证范围

`checks/check_auth.py` 使用合成凭据和模拟原站，检查 DPAPI 往返与原子落盘、Cookie 的安全属性及主机范围、一次自动重登、失败与二次验证后暂停、导入筛选、状态输出和独立清理；`check_auth_browser.py` 验证关闭与清除浏览器资料的区别。运行 Windows `check.ps1` 或 WSL `check.sh`，或在项目 uv 环境中执行该检查。真实账号与二次验证需要用户在本项目独立初始化，实际会话有效性由固定只读登录探测确认。

`checks/check_auth_recovery.py` 覆盖同账号续期、账号 A/B 隔离与切回、旧请求拒绝、分页中途一次恢复、MFA 不重试、其他账号设备停用、未知旧会话不迁移、跨 Vault 实例更新、失败后计数器持久化，以及注册结果不确定后的恢复。所有身份与密钥均为合成数据。

自动引导只在固定 IDS 个人中心运行，只点击账号安全入口和一次绑定按钮，不填写密码或验证码，不替代学校复核。后台等待可在退出应用或删除设备/账号时取消。设置页轮询安全的进度状态，离开设置即停止前端轮询。`checks/check_device_guide.mjs` 覆盖限定来源和一次点击约束；后台编排使用合成复核状态验证。

## 浏览器身份与重启恢复

登录窗口使用用户电脑安装的 Edge，并为各服务保留固定的应用登录资料，位置为 `.private/runtime/auth/<provider>`。导入成功、关闭窗口或停止服务只关闭进程；再次打开复用 Cookie、站点存储与已建立的浏览器身份。删除账号或切换账号时，才清除对应浏览器资料。个人日常浏览器的资料不由工作台读取。

API 请求优先验证 Vault 中的 Cookie 与服务参数；保存同一账号的新密码保留现有会话和身份，显式登录也优先复用有效会话。来源确认会话失效后，读请求进行一次实际续期。IDS、Gradescope 与 Piazza 的恢复方式依各服务支持情况决定；邮箱的 SID 由学校控制有效期，保存 Cookie 不能延长已过期的服务端会话。学校要求验证时，通过原资料目录完成验证再导入。

网络失败保留会话与上次确认的连接状态，并显示本次请求错误。Gradescope 使用已登录首页的 `gon.page_context.user_trn` 确认用户 ID，账号设置页可能要求再次验证，因此不用于每次读取前的身份探测。
