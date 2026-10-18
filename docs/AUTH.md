# 共享认证服务

桌面安装版使用随包的 Electron 独立登录窗口，凭据和浏览器资料保存在安装目录 `.private/`；源码网页入口继续使用本机 Edge。两者沿用相同的登录、会话复核与账号隔离接口。

框架提供 Gradescope、Piazza、学校 IDS 与 Coremail 四个独立认证提供方。认证层保存账号与会话、完成登录与二次验证、向 Python 模块提供已验证的 HTTP 客户端；具体课程、邮件与文件功能由各模块实现。提供方 ID 固定为 `gradescope`、`piazza`、`ids`、`coremail`。IDS 的登录目标固定为 `blackboard`、`elrc`、`ecourse`、`timetable`，默认 `blackboard`。学校邮箱同时支持推荐的 IMAP 专用密码登录与官方网页会话；配置 IMAP 后优先使用 IMAP，网页会话及其缓存会被删除。E 云课堂使用原站登录页中的已登录账号标识验证身份，其课程数据由独立模块只读同步。

## 本地凭据与资料

账号密码、IMAP 专用密码、Cookie／SID、设备私钥与模型 API Key 统一保存在 `.private/vault.dpapi`，使用当前 Windows 用户的 DPAPI 加密。普通设置、学习档案和缓存记录位于 `.private/settings.sqlite3`、`.private/modules/`，属于本地普通数据；模块备份位于 `.private/backups/`，不包含 Vault 或认证窗口资料。这些目录均由 Git 忽略，应用从本机 Vault 读取凭据，源码不提供默认 Key。

认证窗口使用 `.private/runtime/auth/<提供方>/` 的独立浏览器资料。导入会话、取消验证或退出服务时清理历史、图标缓存、标签恢复、同步索引与页面缓存，避免带 SID 的登录 URL 长期残留；保留加密 Cookie、Local State 与站点存储以复用登录。清理失败明确提示，不删除持久凭据。认证窗口启动使用 `--disable-sync`；断开账号时删除整个对应浏览器资料目录。

检查凭据存储时不得把解密值、Cookie、SID 或 Key 写入报告、截图、日志、提交与 PR。检查和自动回归使用合成凭据；私有工作目录不进入版本控制。

## 用户连接流程

1. 设置 → 账号与登录 → 打开官方登录窗口。在原站完成密码、短信、验证码等验证，应用不读取输入的密码。
2. 学校账号在官方窗口完成登录后，应用自动验证并加密保存会话，关闭窗口，逐项连接 Blackboard、教学社区、E 云课堂和教务。等待最多 10 分钟，也可点击“登录完成，连接全部服务”手动检查。其他提供方返回点击“登录完成，连接账号”。窗口资料保留用于下次登录；同步前仍会检查会话。
3. 学校 IDS 可选“本机免密码登录”：点击“连接并绑定本机”并确认。应用沿用 QJQ 的引导顺序，自动进入学校账号安全页、点击“绑定当前设备”以触发学校身份复核；用户只完成学校要求的验证，应用检测通过后自动注册设备并关闭窗口。若学校尚未开启“生物验证”，先在学校页面开启再重试。学校新增独立的“Campus 工作台 · 本机”凭据；私钥以当前 Windows 用户的 DPAPI 加密。应用无需保存学校密码，也不复制 QJQ 或其他程序的私钥。这是软件设备凭据，不是调用 Windows Hello 的硬件生物认证。
4. 会话失效时，已绑定的 IDS 设备可自动恢复课表、Blackboard 和 ELRC 登录；密码方式按提供方支持情况恢复。二次验证或失败会暂停自动尝试，在设置显示原因。点击“检查连接与恢复”可主动重试。Coremail 使用已保存 Cookie 与 SID，服务端会话过期后在保留浏览器资料的官方窗口重新连接。Gradescope/Piazza 仅导入会话时也需重新连接，保存密码是可选项。

成功连接学校账号后，应用重启会启动一次校内连接检查；之后恢复按来源读取需要触发，不持续轮询或保证永不过期。原站验证码和二次验证仍由用户完成。绑定结果不确定时先加密保留私钥，可点击“检查上次绑定结果”，不会连续注册设备。删除本机凭据只清除本机私钥；学校端设备需到账号安全页自行撤销。

校内四项各自显示状态；某项要求验证或网络不可达时，其他项仍继续检查。统一认证凭据被拒绝则共用一次恢复暂停，重启不会清除；主动连接、更新凭据或成功导入可解除暂停。已续期的 IDS 会话会保留，避免因为某个业务平台失败而反复续期。自动读取核对学校账号身份，不能静默切换账号；通过官方窗口明确导入另一账号时，清除旧连接状态并切换资料归属。所有后台任务在删除账号和退出时取消。

邮箱、Gradescope、Piazza 仍独立连接，目前未确认其可用的上科大 SSO 入口；证据和接入条件见 [SSO 核查](SSO_RESEARCH.md)。

Gradescope、Piazza 与 IDS 的卡片提供“账号密码登录”：输入账号密码，点击“保存并登录”即可完成两个步骤；服务确认保存后清空密码框。已保存密码的同一账号可留空直接登录，修改账号时必须重新填写密码。密码登录遇到二次验证时，卡片显示原因，可继续打开官方窗口并在完成后连接。每张卡片独立显示进度与结果，操作期间禁用其控件；其他账号、AI 配置及尚未提交的输入保持原状。设备绑定进度也在原卡片更新。

## 学校邮箱 IMAP（推荐）

设置 → 账号连接 → 学校邮箱首先显示 IMAP 登录。使用学校邮箱“安全设置 → 客户端专用密码”生成的专用密码，不填写统一认证密码。收件服务器固定为 `imap.shanghaitech.edu.cn`，端口可编辑，默认 `993` 且启用 SSL/TLS；关闭 SSL 时按普通 IMAP 连接（常用端口 `143`）。卡片内的“设置指引”提供可关闭的两页说明：第一页对应学校邮箱中的设置入口与专用密码生成位置，第二页对应复制专用密码并核对 IMAP 服务器与端口。

保存前服务使用 `imaplib` 实际登录并选择只读的 `INBOX`，成功后才写入 Vault。账号与专用密码保存在 `auth:imap:coremail`，不返回前端；状态只暴露 `configured/host/port/ssl/username/password_saved/verified_at`。接口为 `GET/PUT/DELETE /api/v1/auth/coremail/imap` 与 `POST /api/v1/auth/coremail/imap/check`；PUT 请求体为 `{username,password,port,ssl}`，同一账号可留空密码继续使用已保存值。

IMAP 成功后，认证层删除 `auth:credentials:coremail`、`auth:session:coremail` 与邮箱浏览器资料，并切换账号版本，避免旧网页缓存继续生效。存在 IMAP 时，官方网页登录入口在设置页隐藏，打开官方窗口、导入会话和网页认证客户端均被拒绝；如确需改用网页方式，先删除 IMAP 登录。删除账号、清除凭据与应用完整清理都会同时删除 IMAP 配置。邮件模块通过 `AuthService.imap_connection()` 获取只读连接，凭证不进入模块；同步使用 `UID SEARCH ALL` 读取最近 100 个 UID，正文使用 `BODY.PEEK[]`，不会把邮件标记为已读。

## 校园网络、代理与校外 VPN

### 网络检测

教务、Blackboard、ELRC 同步遇到网络错误时，时间表、课程中心及来源页直接自动检测并显示原因、处理建议和重试入口。ELRC 的更新目录和逐课同步也显示同类提示；登录、权限和解析错误保留原有提示，不触发网络诊断。同步成功后清除旧故障提示，失败保留已有缓存。后台失败在页面读到新故障标记时诊断，不持续轮询网络。

`POST /api/v1/auth/network/explain` 接收 `{failures:[{id,target,kind,at,host?}]}`（1–6 项），同样要求框架 CSRF。target 仅为 timetable/blackboard/elrc/ecourse，kind 仅为 `dns_error/tls_error/timeout/proxy_error/protocol_error/configuration_error/connection_error`。返回 `{reports:[{failure_id,target,name,failed_at,checked_at,diagnosis,entry,vpn_guide}]}`；使用固定入口，不访问传入 host，只用它匹配已知学校入口。故障标记不含请求路径、参数、异常原文或账号信息。实际同步的 DNS/TLS/配置错误优先；当前入口可达时明确说明无法证明失败的资料接口恢复，不把单独代理对照失败当成本次直连同步失败的原因。新故障不复用早于故障发生时间的检测。

设置 → 网络检测会在首次进入时检查统一认证、教务、Blackboard、ELRC 和邮箱入口，可在切换网络或连接 VPN 后重新检测。每个服务显示系统 DNS、工作台直连和已配置 HTTPS/ALL 代理的匿名对照结果；实际校园同步仍默认绕过普通代理。返回 401 表示服务已响应但需要登录，403 表示访问受限，5xx 表示网络已连通但服务响应异常，不把这些状态当成 VPN 未连接。

无效代理配置可能在同步客户端初始化时阻止请求，即使匿名直连探测成功也应先修正配置。代理路径失败的同时返回 401 时保留登录提示；实际请求的 TLS/配置错误优先于独立 DNS 探测的超时，避免将已观察到的连接错误误判为 VPN 或 DNS 问题。

`GET /api/v1/auth/network` 只读取本进程最近检测（首次为 `{checked_at:null,services:[]}`）；`POST /api/v1/auth/network/check` 使用框架 CSRF 发起固定入口检测，无请求参数，不允许自定义 URL。响应包含 `checked_at,summary,scope,reachable_count,total,proxy_configured,campus_location,vpn_status,services`；每个 service 包含 `id,name,host,port,dns{status,addresses,kinds},direct{status,reachable,http_status?,elapsed_ms},proxy,diagnosis{code,confidence,title,message,actions}`。`proxy` 未配置时为 null；不返回代理地址、用户名、密码、响应正文、Cookie 或跳转票据。

检测仅发送匿名 HTTPS GET，读取响应头后关闭，不跟随跳转、不读取 Vault、不改变账号或网络配置。系统 DNS 等待最多 3 秒，单次 HTTP 探测总限时 6 秒，所有固定入口并发检查；同一进程合并并发检测并在完成后 5 秒内复用结果，界面注明时间。切页取消界面请求，已发出的服务端检查仍有上述上限；不启动后台定时检测。结果仅保存在内存，重启清除。

DNS 失败和实际连接错误是可确认的观测；内网地址不可达只提示“疑似校园网络或 VPN 路径问题”，保留服务故障的可能。198.18.0.0/15 解析结合连接失败仅提示疑似 Fake-IP/TUN。`campus_location`、`vpn_status` 均为 `unknown`，不根据 IP、进程或服务可达性推断物理位置及 VPN 已连接。入口可达不代表全部资料接口、账号权限或同步均正常。检测通过已有普通代理做对照（不受 NO_PROXY 绕过规则影响），TUN/透明代理仍可能拦截两条路径，不能把它们解释为两个独立物理网络。

### 默认路由

共享认证客户端对 `shanghaitech.edu.cn` 及其子域默认跳过 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`，覆盖教务、Blackboard 的 8443 端口、ELRC、IDS 和学校邮箱。域名由本机解析，连接交给操作系统网络；Gradescope、Piazza 等外部来源继续使用用户原有的 HTTP／SOCKS 代理配置。依赖包含 HTTPX 的 SOCKS 支持，避免用户配置 `ALL_PROXY=socks5://…` 时连客户端都无法创建。学校官方登录的独立 Edge 窗口同样跳过浏览器代理。该策略只在本应用中生效，不修改用户的系统代理、环境变量或路由表，保留证书验证与自定义 CA 支持。

| 使用环境 | 默认路径 |
| --- | --- |
| 已接入校园网 | 应用 → 系统网络 → 校园服务 |
| 校外且学校 VPN 已连接 | 应用 → 系统网络／学校 VPN 客户端 → 校园服务 |
| 校外且尚未连接学校 VPN | 可公开访问的服务照常使用；内网服务需用户先连接学校 VPN，再重新同步 |

直连表示跳过应用层代理，系统 VPN 仍可接管连接。校外访问校园内网资源，按[学校 VPN 接入指南（2026-09-07）](https://it.shanghaitech.edu.cn/2021/0424/c8423a63191/page.htm)安装并连接官方客户端，通过[学校 VPN 入口](https://vpn.shanghaitech.edu.cn)完成认证。应用不代填 VPN 密码／验证码，也不把 VPN 客户端进程存在当作连接成功的证明；以学校服务实际可达为准。公开入口是否允许校外访问可能变化，不能仅凭登录页面可打开就认定所有接口和附件可用。

若代理软件启用了 TUN、透明转发或 Fake-IP DNS，它仍可能接管应用的直连流量。应在该软件中将校园域名设为直连，并按学校 VPN 实际下发的校园网段设置 TUN 排除，让校园域名使用系统／校园 DNS，确保学校 VPN 的路径生效。应用不猜测固定校园网段或 DNS 地址，也不自动改动第三方代理和 VPN 配置。切换网络后可直接重试同步；WSL 运行方式还需确认 WSL 能使用宿主机的 VPN 路径，Windows 原生运行默认沿用 Windows 网络。

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
| `POST /api/v1/auth/ids/connect` | 无 | 202，启动或复用一次校内全部服务连接；状态接口读取进度 |
| `POST /api/v1/auth/ids/device/browser` | 无 | 打开学校账号安全页 |
| `POST /api/v1/auth/ids/device/start` | `{confirmation:"REGISTER_THIS_DEVICE"}` | 开始可见的学校验证引导，复核通过后自动绑定；最多等待 10 分钟 |
| `POST /api/v1/auth/ids/device/bind` | `{confirmation:"REGISTER_THIS_DEVICE"}` | 用户确认后注册独立设备并连接 |
| `POST /api/v1/auth/ids/device/recover` | 无 | 验证待确认凭据，成功后启用 |
| `DELETE /api/v1/auth/ids/device` | 无 | 删除本机正式及待确认设备私钥 |
| `DELETE /api/v1/auth/{provider}` | 无 | 清除该提供方账号、会话与验证窗口后的状态 |

`target` 仅用于 IDS，界面默认无需选择。指定目标用于处理某个服务的额外验证，例如 `{"target":"elrc"}`；导入未指定时使用最近打开窗口的目标。用户完成验证后学校登录等待任务自动导入，也可手动调用导入接口。Coremail 通过手动导入流程登录。其他提供方可先尝试密码登录，需要验证时转入窗口。

状态响应示例使用合成账号：

```json
{
  "id": "ids",
  "name": "学校统一登录",
  "username": "synthetic-user",
  "has_password": true,
  "has_session": true,
  "status": "ready",
  "target": "elrc",
  "targets": ["ecourse", "blackboard", "elrc", "timetable"],
  "checked_at": "2026-10-01T00:00:00+00:00"
}
```

`status` 为 `not_connected`、`login_required`、`verification_required`、`error` 或 `ready`；`message` 提供当前操作提示。`has_session` 仅表示本地保存了会话。`ready` 与 `checked_at` 表示上次固定目标探测成功，状态查询本身不联网，服务端是否已让会话失效需要下一次只读探测确认。Cookie 的到期字段无法证明会话仍有效，未知期限的会话也保留原状。

IDS 另外返回 `services:[{id,name,status,message?,checked_at?}]`、`browser_target` 和 `connection:{status,active_target?,completed?,total?,started_at?,finished_at?}`。连接状态为 `idle/waiting_for_login/connecting/complete/interrupted`；`complete` 表示本轮检查结束，成功数量从各项 `ready` 计算。只要仍有服务可用，总状态可保持 `ready`，界面须结合各项提示显示部分失败。连接任务去重、串行执行；新账号或删除操作使旧任务失效。状态中不包含任务令牌、秘密、Cookie 或学校返回的页面正文。

登录失败返回 401，需要验证码或浏览器验证返回 409，未知提供方返回 404，无效请求返回 400 或 422，远端连接失败返回 502。失败后读取状态接口可获取操作提示。HTTP 校验错误不回显输入的秘密。

## Python 模块接入

模块只需校验账号归属时调用 `context.auth.get_account_revision(provider)`。它每次直接读取当前持久化账号版本，与 `get_status(provider)['account_revision']` 一致，不缓存版本、不读取凭据或会话。资料快照、账号缓存和聚合查询在读取前后用该接口复核账号；需要显示登录状态或判断恢复方式时继续使用 `get_status`。凭据加密、文件事务与会话恢复不受此读取优化影响。

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

`backend/core/vault.py` 的 `Vault` 默认写入项目 `.private/vault.dpapi`，使用 Windows DPAPI `CurrentUser` 加密整份 JSON，先写加密临时文件再原子替换。`get()` 返回副本，`save()`、`delete()`、`delete_prefix()` 与 `clear()` 统一管理秘密。认证键为 `auth:credentials:{provider}`、`auth:session:{provider}` 与邮箱专用的 `auth:imap:coremail`；账号、密码、专用密码、Cookie、sid 与其他密钥全部留在加密 Vault。普通认证状态写入 Store 的 `auth:state:{provider}`，其中只含状态、提示、阻断标志与探测时间。DPAPI 文件与当前 Windows 账号绑定，运行于该账号或启用 Windows 互操作的 WSL。

验证浏览器的固定用户目录位于 `.private/runtime/auth/{provider}`。成功导入会话或正常退出服务时关闭框架创建的独立窗口，并保留 Cookie、localStorage 与浏览器身份；删除提供方或切换账号时清除对应目录。导入失败时保留窗口供用户继续验证。私有运行数据由 Git 忽略，打包和交付按代码文件清单进行。

`AuthService.clear_all()` 清除四个提供方的账号、会话、状态与浏览器资料；`close()` 在服务退出时关闭窗口并保留资料。完整凭据清理由框架统一调用 Vault 清空方法，模块不直接打开 Vault 文件。认证开发只修改 `backend/services/auth/`、`backend/core/vault.py`、`scripts/browser.mjs`、`scripts/dpapi.ps1` 及对应文档和检查。

设备私钥与签名计数器保存在 `auth:device:ids`，待确认注册保存在 `auth:device-pending:ids`。Vault 通过进程间文件锁串行读取、修改和原子替换；设备签名期间持有事务锁，即使后续登录失败也保存已增加的计数器。账号与设备状态接口不会返回私钥、凭据 ID 或签名计数器。

## 验证范围

`checks/check_auth.py` 使用合成凭据和模拟原站，检查 DPAPI 往返与原子落盘、Cookie 的安全属性及主机范围、一次自动重登、失败与二次验证后暂停、导入筛选、状态输出和独立清理；同时验证 IMAP 专用密码写入 Vault、端口与 SSL 参数传递、删除官方网页会话、网页入口被 IMAP 优先规则拒绝，以及状态接口不泄露密码。`modules/mail/checks/check_mail.py` 使用合成 IMAP 邮箱覆盖最近 100 封 UID 列表、未读标记、`BODY.PEEK[]` 正文读取、HTML 清理与附件元数据。`check_auth_browser.py` 验证关闭与清除浏览器资料的区别。运行 Windows `check.ps1` 或 WSL `check.sh`，或在项目 uv 环境中执行该检查。真实账号与二次验证需要用户在本项目独立初始化，实际会话有效性由固定只读登录探测确认。

`checks/check_auth_recovery.py` 覆盖同账号续期、账号 A/B 隔离与切回、旧请求拒绝、分页中途一次恢复、MFA 不重试、其他账号设备停用、未知旧会话不迁移、跨 Vault 实例更新、失败后计数器持久化，以及注册结果不确定后的恢复。所有身份与密钥均为合成数据。

自动引导只在固定 IDS 个人中心运行，只点击账号安全入口和一次绑定按钮，不填写密码或验证码，不替代学校复核。后台等待可在退出应用或删除设备/账号时取消。设置页轮询安全的进度状态，离开设置即停止前端轮询。`checks/check_device_guide.mjs` 覆盖限定来源和一次点击约束；后台编排使用合成复核状态验证。

## 浏览器身份与重启恢复

登录窗口使用用户电脑安装的 Edge，并为各服务保留固定的应用登录资料，位置为 `.private/runtime/auth/<provider>`。导入成功、结束验证或停止服务后清理导航记录，保留 Cookie、站点存储与已建立的浏览器身份供再次使用。删除账号或切换账号时，才清除对应浏览器资料。个人日常浏览器的资料不由工作台读取。

API 请求优先验证 Vault 中的 Cookie 与服务参数；保存同一账号的新密码保留现有会话和身份，显式登录也优先复用有效会话。来源确认会话失效后，读请求进行一次实际续期。IDS、Gradescope 与 Piazza 的恢复方式依各服务支持情况决定；邮箱的 SID 由学校控制有效期，保存 Cookie 不能延长已过期的服务端会话。学校要求验证时，通过原资料目录完成验证再导入。

网络失败保留会话与上次确认的连接状态，并显示本次请求错误。Gradescope 使用已登录首页的 `gon.page_context.user_trn` 确认用户 ID，账号设置页可能要求再次验证，因此不用于每次读取前的身份探测。
