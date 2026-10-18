# 统一 HTTP API

开发入口为 `http://127.0.0.1:16666`，基础路径 `/api/v1`。通过命令行预览端口或设置修改端口时，所有相对路径保持一致。`GET /api/openapi.json` 返回共享服务与框架的 OpenAPI，`/api/docs` 提供交互式界面；每个后端模块另有 `/api/v1/modules/<id>/openapi.json`。

## 本地访问规则

服务仅绑定 `127.0.0.1`，校验 Host 与 Origin。先调用 `GET /api/v1/bootstrap` 获取本次服务的 `csrf_token`，后续 POST、PUT、PATCH 和 DELETE 都在请求头带 `X-Framework-Token: <csrf_token>`。服务重启后重新获取。浏览器共享 `api()` 及模块注入的 API 客户端自动处理该请求头。

JSON 请求使用 `Content-Type: application/json`。成功响应是直接 JSON；框架错误处理器返回 `{detail,code,action,request_id}`，`detail` 保持原有字符串或校验错误数组结构（`loc/msg/type`）。`action` 给出下一步操作，`request_id` 与响应头 `X-Request-ID` 一致；诊断日志只记编号、状态、错误代码与异常类型，不记录异常原文、URL、请求体或私人响应。共享前端保留 Error 的 `status/code/requestId/action`，展示字段位置、操作提示和编号。模块应通过 `HTTPException` 提供可公开说明；未知异常使用通用 500，不能直接回显异常文本。流式响应开始后的错误继续沿用模块自己的事件协议。

HTTP 400 表示参数或本地环境不符合要求（保留现有 RuntimeError 的 400 契约，但只公开明确标记的安全说明），401 表示需要登录，403 表示本地访问校验失败，404 表示资源未启用或不存在，409 表示需要二次验证、AI 未启用、模块忙、备份不可用或停止失败，422 表示字段校验失败，500 表示内部或本地存储错误，502 表示来源连接失败，503 表示忙碌，504 表示等待超时。超时后应先检查操作结果，避免重复提交。`code` 提供更具体的分类，如 `verification_required/storage_error/storage_busy/file_error`。

## 框架与设置

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/bootstrap` | `{version, csrf_token, categories, settings, modules}`；分类按侧栏顺序返回 |
| GET | `/health` | `{application:"campus-framework",version,launch_id}`；启动器校验本次服务已可访问 |
| GET | `/settings` | `{port, active_port, restart_required, appearance:{revision,resetRevision,value}, storage:{directory,encryption}}` |
| PUT | `/settings` | 请求 `{port:16666}`，返回完整设置；修改后重启生效 |
| PATCH | `/settings/appearance` | `{revision:0,patch:{theme?,companions?,reduceMotion?,options?}}` → `{revision,resetRevision,value}`；原子比较版本并合并外观，旧版本返回 409 |
| GET | `/themes` | `{api_version:1,default:"default",items:[Theme],errors:[]}`；发现本地主题、样式和界面入口，详见 [主题契约](UI_THEME.md) |
| POST | `/data/clear` | `{scope:"credentials"\|"modules"\|"all", confirmation:"CLEAR"}` → `{cleared:scope,backup:BackupInfo\|null}` |
| GET | `/data/backups` | `{backups:[BackupInfo]}`，新备份在前；损坏项 `valid:false`，仍可删除 |
| POST | `/data/backups` | 停止模块后创建快照，再重新加载；返回 `{backup:BackupInfo}` |
| POST | `/data/backups/{id}/restore` | `{confirmation:"RESTORE"}` → `{restored:id,backup:BackupInfo}`，backup 为恢复前的数据 |
| DELETE | `/data/backups/{id}` | `{confirmation:"DELETE_BACKUP"}` → `{deleted:id}`，只删除该备份 |

端口范围为 1024–65535，浏览器限制端口在系统边界拒绝。默认保存端口 16666，`--port` 只覆盖当次运行端口。

外观独立保存在当前项目目录的 SQLite `core/appearance`，不包含凭据。首次没有记录时返回 `{revision:0,resetRevision:0,value:null}`；`bootstrap.settings.appearance` 与 `GET /settings` 返回相同记录。客户端首次可将本浏览器已规范化的旧偏好作为 patch 迁入；有服务端记录时以服务端为准。首次成功保存产生 revision 1、resetRevision 0 和完整 `value:{theme:"default",companions:{},reduceMotion:false,options:{}}`（提供的字段覆盖默认值）。端口 `PUT /settings` 不覆盖外观，外观 PATCH 不修改端口；服务重启后沿用同一数据库恢复。清除凭据或模块数据保留外观；清除 `all` 删除其他 core 数据，并保存显式默认外观（版本继续递增，value 不回到 null），避免旧浏览器再次迁入刚清除的偏好；真正从未保存过外观的数据库才返回 null。模块数据备份不包含框架外观。

`resetRevision` 表示最近一次明确重置的版本屏障，取整数 0 至 revision；读取没有此字段的旧两字段记录时补 0。普通 PATCH 保持此值，清除 `all` 后将其设置为新的 revision。客户端发现此屏障变化时应采用服务器默认外观并取消重置前排队的修改，不得按普通 409 重放旧 patch；请求仍只含 revision 和 patch。

每次 PATCH 携带最近读取的 revision，后端在 SQLite 写事务中比较并递增；旧版本返回 409 且不写入，客户端应重新读取并仅重试尚未保存的局部 patch，不能用旧快照覆盖新记录。PATCH 保留未提供的字段；嵌套对象递归合并，数组、标量和 options 内的 null 显式替换。顶层仅接收 theme、companions、reduceMotion、options；主题/人物选项 ID 格式为 `[a-z][a-z0-9-]{0,47}`，companions 以主题 ID 分区，options 每个主题对应任意受限 JSON 对象。不要求主题目前已安装，也不枚举主题或过滤其未知配置键，因此暂缺/未来主题的偏好可保留。

patch 和合并后的完整外观各限制为 UTF-8 JSON 64 KiB、最多 8 层、4096 个值节点；对象/数组每层最多 128 项，键最长 128 字符，文字最长 8192 字符，数字须有限且绝对值不超过 `2^53-1`。递归拒绝 `__proto__`、`constructor`、`prototype` 键、非法字段和类型，返回 422。revision 是 0 至 `2^53-1` 的整数（不接受布尔值/字符串）；同样要求写请求 CSRF 令牌。主题展示仍按主题契约决定，服务端保存某主题并不表示该主题已安装。


`launch_id` 是每次启动的公开实例标识，不是认证凭据，不能替代 CSRF token。Windows 启动器将健康响应与本目录 `.private/runtime/launcher/server.json` 匹配后打开 Edge。健康接口沿用 Host/Origin 与本机访问限制，不返回路径、账号或密钥。

清除 `credentials` 时停止模块及登录窗口，清除 Vault 中所有共享和模块秘密、认证状态，并关闭 AI，再挂载模块；普通模块数据保留。清除 `modules` 时停止模块、清除全部模块状态、秘密和文件，再挂载模块；共享登录、AI 与框架设置保留。`all` 执行两类清除并恢复默认设置，当前监听端口持续到服务重启。模块代码与清单始终由开发者维护，数据清除操作只处理本地数据。

`modules/all` 清除前自动备份，备份失败则不清除。备份仅含 SQLite 的 `module:*` 行和 `.private/modules/` 文件，不包含 core 状态、Vault、登录浏览器或运行时目录。快照存于 `.private/backups/<id>/`，保留至用户单独删除；`all` 清除也保留备份。`BackupInfo` 含 `id,created_at,reason,size_bytes,file_count`，列表另含 `valid`；reason 为 `manual/before_clear/before_restore`。备份包含私人资料，沿用私有目录的 Git 忽略和本机访问范围。

创建、恢复、清除要求模块请求结束并成功执行 stop，否则返回 409。恢复先校验格式、模块命名空间和文件清单，拒绝路径穿越、符号链接与 Windows junction；再备份当前数据。模块行在 SQLite 事务内替换，文件替换失败或数据库写入失败时回滚文件。操作结束或失败均重新加载模块。恢复保留当前账号、凭据、AI 配置和启停选择；模块仍按当前账号版本读取记录。只有本地备份，没有外部上传或定时任务。突然断电无法保证数据库和文件跨介质原子性，可在服务可用后用自动保留的恢复前备份重新恢复。

## 模块管理

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/modules` | `{modules:[ModuleInfo],categories:[Category]}` |
| POST | `/modules/reload` | 扫描模块目录、释放并重新加载，返回 `{modules:[ModuleInfo],categories:[Category]}` |
| PUT | `/modules/<id>` | `{enabled:true\|false}`，返回 `{modules:[ModuleInfo],categories:[Category]}` |
| 任意 | `/modules/<id>/<route>` | 模块自己的公开后端接口，由该模块文档说明 |

`Category` 包含 `id,label,icon,description,order,layout`，从已安装模块的导航声明生成，最后附加框架设置。清单、启停和刷新均返回同一分类列表；页面只显示存在已启用前端模块的业务分类。

`ModuleInfo` 包含 `id`、`name`、`version`、`category`、`navigation`（可空）、`enabled`、`status`、`has_frontend`、`frontend_url`、`background_url`。`has_frontend` 表示模块目录提供页面入口；侧栏根据启用状态和该字段显示分类，加载失败的页面仍保留错误入口。有效入口另有 `api_version:1` 和 `harness` 布尔值，已就绪模块包含当前 `revision`；失败时包含可公开的 `error`。状态为 `ready`、`disabled` 或 `error`。后端或纯插件模块的 `frontend_url` 为 `null`。`harness:true` 表示模块提供原生 Harness 入口。

`runtime` 为本次模块实例的内存状态：`loaded_at,active_requests,pending_calls,last_request:{at,status,duration_ms}|null,last_success_at,last_error,workers`。最近错误保留至重新加载，即使后来请求成功也不会抹去；若来自统一错误处理器，还带 `code/request_id`。状态页手动读取，不用高频轮询；`ready` 只表示加载成功。worker 为 `{name,kind:thread|task,status:running|stopped|idle|cancelled|error}`；线程存活不代表一次业务检查成功，Future 的 idle 只表示正常结束，来源同步结果仍以业务 snapshot 为准。刷新与重启重置状态，不落盘保存历史。

前端资源入口由服务返回，例如 `/module-assets/notes/<revision>/web/index.js?v=<revision>`。模块应原样使用入口地址和相对导入，版本路径覆盖其子资源。停用或更新后，旧版本资源返回 404。模块接口热切换前要求相关请求完成；有执行中请求返回 409，调用方在完成后重试。

## 共享认证

提供方 ID 为 `gradescope`、`piazza`、`ids`、`coremail`。IDS 的 `target` 为 `blackboard`、`elrc`、`timetable`，默认 `blackboard`。接口仅负责认证和会话，内容读取由业务模块自己的 API 实现。

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/auth/providers` | `{providers:[ProviderStatus]}` |
| GET | `/auth/network` | 最近的校园网络检测；首次 `{checked_at:null,services:[]}`，不发起外部请求 |
| POST | `/auth/network/check` | 无参数；匿名检测五个固定校园入口，返回 DNS、直连、代理对照和处理建议；详见 AUTH.md |
| POST | `/auth/network/explain` | `{failures:[{id,target,kind,at,host?}]}`；结合实际同步错误和新入口检测给出内联诊断，最多 6 项；详见 AUTH.md |
| GET | `/auth/<provider>/status` | 单个 `ProviderStatus`；读取已保存状态 |
| PUT | `/auth/<provider>/credentials` | `{username,password}` → `ProviderStatus` |
| POST | `/auth/<provider>/login` | 可选 `{target}`，登录或验证会话，返回状态 |
| POST | `/auth/<provider>/browser` | 可选 `{target}`，打开独立验证窗口 |
| POST | `/auth/<provider>/import-session` | 可选 `{target}`，导入、探测、加密保存并关闭临时窗口 |
| POST | `/auth/<provider>/refresh` | 可选 `{target}`，主动探测并恢复登录 |
| POST | `/auth/ids/device/browser` | 打开学校账号安全页 |
| POST | `/auth/ids/device/start` | `{confirmation:"REGISTER_THIS_DEVICE"}`，打开验证引导并在复核通过后自动绑定 |
| POST | `/auth/ids/device/bind` | `{confirmation:"REGISTER_THIS_DEVICE"}`，确认后绑定本机免密码设备 |
| POST | `/auth/ids/device/recover` | 验证待确认的设备绑定 |
| DELETE | `/auth/ids/device` | 删除本机设备凭据，学校端登记需另行撤销 |
| DELETE | `/auth/<provider>` | 清除此提供方的本地凭据、会话与临时验证资料 |

`ProviderStatus` 含 `id`、`name`、`username`、`has_password`、`has_session`、`status` 以及可选的 `message`、`checked_at`、`targets`。Cookie、密码、登录票据和 Coremail sid 仅由服务端使用。二次验证在用户可见的登录窗口完成。Python 内部使用 `context.auth.authenticated_client(provider, target=None)`，完整例子与过期策略见 [认证文档](AUTH.md)。

## 时间表

`GET /modules/timetable/schedule?week_start=YYYY-MM-DD` 汇总当前账号的上课安排、Blackboard／Gradescope 带时间的 quiz 与作业、教务考试和个人安排，返回 `calendar{week_start,week_end,week_one,week_one_source,teaching_week,days:[{date,events}]}`；省略日期时使用北京时间本周。`week_one_source` 说明 `week_one` 的来源：`manual` 为手动填写，`school` 为学校校历，`null` 表示尚未确定；有课表但日期未确定时不展开课程，返回来源提示及不完整的冲突检查；已有个人安排和截止事项继续显示。校历读取失败时保留已识别的学校日期与手动值。`POST /modules/timetable/schedule/sync` 启动对应来源同步（202）。来源停用时保留其他来源的显示，聚合期间账号切换返回 409。`/calendar-settings` 的 GET/PUT/DELETE 读取、手动设置或恢复学期起始日期（返回同名的 `source` 字段，取值与 `week_one_source` 一致），`POST /calendar/refresh` 更新学校校历；手动值按账号与学期保存，自动更新保持同学期手动值。`/events` 提供本机 Quiz、展示、活动、讲座的增删改查。原始上课数据继续通过 `/snapshot`、`/sync` 提供；具体字段见 [时间表接口](../modules/timetable/README.md)。

## 共享 AI

首页学习助手的业务入口为 `/modules/academic-assistant/chat`，会按问题调用所需数据 API，再由官方 Harness 组织回答；共享 AI 继续提供运行时与模型服务。业务接口和外部发送范围见下方及 [模块说明](../modules/academic-assistant/README.md)。

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/ai/settings` | 当前 `enabled/provider/model/display_name/custom/base_url/protocol/key_saved` 和 `providers` 列表 |
| GET | `/ai/catalog` | 官方 Harness 锁定版本的 39 个内置提供商、模型 ID 与三种自定义协议 |
| PUT | `/ai/settings` | 按需提交 `enabled/provider/model/custom/base_url/protocol/display_name/api_key/delete_key`；保存密钥默认启用 |
| DELETE | `/ai/providers/{id}` | 删除该提供商的配置与密钥；当前提供商被删除时暂停 AI |
| POST | `/ai/generate` | `{prompt, context?:string, format?:"text"\|"json"}` |
| POST | `/ai/chat` | `{messages:[{role,content}], format?:"text"\|"json"}` |
| GET | `/ai/plugins` | `{plugins:[ModuleInfo]}`，提供原生插件的模块及状态 |
| POST | `/ai/run` | `{prompt,context?:string,plugins:[模块ID]}` → `{content,model,session_id,tools:[{id,name,is_error}]}` |

生成和对话返回 `{content, model, usage:{prompt_tokens,completion_tokens,total_tokens}}`，`content` 按格式为文本或 JSON 对象。模型为 `deepseek-flash` 或 `deepseek-v4-pro`。启用 AI 前保存 Key；不填 Key 表示保留，删除 Key 时单独设置 `delete_key:true` 并关闭 AI。`generate` 的 prompt 最长 16000 字符，context 最长 120000 字符；chat 最多 100 条消息，消息合计最长 120000 字符。

AI 处理调用方明确提供的文本，不会自动读取模块缓存或登录资料。需要聊天历史、来源引用、分类规则或报告保存时，由对应业务模块管理并提供上下文。详见 [AI 文档](AI.md)。

`run` 通过官方 Harness 的原生 Cordis 插件执行任务。prompt 最长 16000 字符，context 最长 120000 字符；显式选择 1–16 个唯一插件 ID，模块管理负责启停和刷新。执行中的插件模块保持活动请求，生命周期操作按现有约定返回 409。原生插件、依赖安装和临时会话的说明见 [AI 插件接口](AI.md#原生-harness-插件)。

调用示例为 `{"prompt":"整理所选事项","context":"调用方选择的资料","plugins":["deadlines"]}`。响应 `content` 为最终文本；`tools[].is_error` 表示单次工具是否失败，工具错误可能由模型处理后继续完成任务。`session_id` 标识本次独立任务。插件列表包含各启停状态，调用方选择 `status:"ready"`；纯插件模块通过共享 AI 接口执行，其 `/modules/<id>/` 下的 HTTP 接口由可选 Python 后端提供。

| 状态 | 插件任务含义 |
| --- | --- |
| 400 | 所选模块的 npm 包名重复 |
| 403 | 本地访问或写入验证失败 |
| 404 | 所选插件缺失、停用或未就绪 |
| 409 | AI 未配置、关闭，或活动任务阻止生命周期操作 |
| 422 | 共享任务请求长度不符、插件数组为空或模块 ID 重复 |
| 502 | 插件安装、模型、运行时失败，或任务未完整结束 |

新增 AI 工具与工作流使用独立模块的原生插件，统一经过共享 `context.ai.run`（HTTP 入口为 `/ai/run`）；基础文本功能使用 `/ai/chat` 和 `/ai/generate`。共享契约维持 `api_version:1`，业务输出 schema、资料引用与持久化约定由模块 API 定义，并随功能 PR 更新。

## 首页学习助手与课程查询

会话索引：`GET /modules/academic-assistant/conversations → {items,active_id}`；`POST` 同路径新建（201）；`POST /conversations/{id}/select → {conversation,messages}`；`PUT /conversations/{id} {title?,archived?}`；`DELETE` 同路径删除。以上均位于模块命名空间内，按账号隔离；归档对话可读取，发送返回 409，恢复后继续。已有单段记录首次读取时迁入索引。完整字段与持久化见模块 README。

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/modules/academic-assistant/chat` | `{messages,conversation_id}`，当前账号组合选中的本机对话 |
| POST | `/modules/academic-assistant/chat` | `{message,conversation_id?}` → `{role,text,citations,navigation,tools,model,created_at,conversation_id}` |
| POST | `/modules/academic-assistant/chat/stream` | `{message,conversation_id?}` → NDJSON：`activity`、`reset`、`delta`、`complete` 或 `error` |
| DELETE | `/modules/academic-assistant/chat` | 删除当前对话，保留学习档案 |
| GET | `/modules/academic-assistant/profile` | `{profile,academic}` |
| PUT | `/modules/academic-assistant/profile` | `{major,cohort_year,direction,weekly_hours,notes}`，需要已验证 IDS |
| DELETE | `/modules/academic-assistant/profile` | 清除当前 IDS 的学习偏好与助手学业记录 |
| GET | `/modules/academic-assistant/activity` | `{active,steps:[{name,label,status}]}`，状态为 `running/done/error` |
| GET | `/modules/academic-assistant/presets` | `{items:[{label,prompt}]}`，插件提供的常用学习问题 |
| GET | `/modules/eams/course-search?q=&page=1` | 学校课程目录 `{items,page,page_size,total,scope,notice}` |
| GET | `/modules/eams/course-info?syllabus_id=` | 教学大纲 `{id,title,text,url,scope,truncated}` |

学习助手会按问题将所需课程、作业、课表、课件文字、录播／讨论、相关通知／邮件、已有课程记录、培养方案与学习档案发送至设置中选择的模型提供商。引用只接受本次读取资料中的 ID 与连续原文；文件引用带真实 `page` 与原文件入口。服务不代交作业、不执行选课；页面操作是已知工作台分类导航。专用 `/tools/*` 只接受当前任务的短期 Bearer 令牌，用户侧写入仍使用统一 CSRF 保护。字段、分页、文件大小与存储约定见 [学习助手](../modules/academic-assistant/README.md)。

流式聊天的 `delta.text` 为正文增量，`complete.message` 与普通聊天结果一致，只有该事件表示成功。流开始后的失败以 `error:{status,detail}` 返回；中断、停止和失败均不保存半段聊天。引用先经工具核对，最终消息保留页码与原文；完整事件字段及生命周期见 [学习助手](../modules/academic-assistant/README.md)。

课程查询复用 IDS 的教务会话，实时读取课程名称／代码及教学大纲；`scope` 分别为 `course_catalog` 和 `course_syllabus`。这两个接口提供课程目录与课程要求，学期实际开课和可选资格仍需核对学校公布的选课安排。培养方案快照新增原始 `requirements` 和 `notes`，见 [教务模块](../modules/eams/README.md)。

## 邮件复核与后台协作

| 方法 | 模块内路径 | 请求与结果 |
| --- | --- | --- |
| GET | `mail/intelligence` | 当前邮件与分类、`preferences/effective_preferences`、`review_status`；分类带 `input_revision/review_pending` |
| GET/PUT | `mail/preferences` | GET 返回偏好与枚举；PUT 接收完整偏好 |
| POST | `mail/review` | `{message_id,force?}`，原生 Harness 逐封复核 |
| GET | `mail/review-context?message_id=` | 本次原文、偏好、分类 schema 与资料指纹 |
| POST | `mail/review-results` | `{message_id,fingerprint,decision}`，校验原文与资料版本 |
| GET | `campus-agent/status` | 后台状态、待处理数量、通知及活动建议 |
| PUT | `campus-agent/settings` | `{enabled}`，关闭时取消当前检查 |
| POST | `campus-agent/check` | 合并一轮最近资料检查，202 |
| POST | `campus-agent/refresh` | 唤醒待复核队列，202，保留启停设置 |
| GET | `campus-agent/queue` | 后台启停、运行、待复核数量及错误 |
| GET | `campus-agent/proposals` | 当前账号的建议与参加状态 |
| POST | `campus-agent/proposals/{id}/accept`、`/dismiss` | 明确参加或不参加；接受后幂等写入时间表 |
| POST | `notifications/imports` | 带账号版本、稳定 ID、资料版本和来源的通知 |
| POST | `timetable/events/import` | 安排字段 + `{origin_id,account_revision}`，重复导入保留手动编辑 |

表中路径均以 `/modules/` 为前缀。跨模块通知与日程导入要求 `account_revision` 为当前共享账号版本，不一致返回 409。网页仍使用 CSRF 保护，原生工具只在自己的固定工具路径使用任务令牌。通知中心提供 `/agent/status`、`/agent/settings`、`/agent/check` 和 `/proposals/{id}/accept|dismiss` 代理接口。详细 schema、字数限制、状态与资料范围分别见 [邮箱](../modules/mail/README.md)、[后台助手](../modules/campus-agent/README.md)、[通知](../modules/notifications/README.md) 与 [时间表](../modules/timetable/README.md)。

## 邮件文件夹与总结

`GET /modules/mail/folders` 提供本地收件箱、未读和智能分类文件夹的数量；完整分类记录继续通过 `/intelligence` 读取。`GET /modules/mail/digests?period=day|week&anchor=YYYY-MM-DD` 返回北京时间的日期范围、分类统计、邮件条目、覆盖范围与已保存总结，不调用模型。`POST /modules/mail/digests {period,anchor?}` 按用户操作生成 `overview/highlights`，校验邮件引用并按账号与日期保存。邮件条目带 `workbench_url`，可返回工作台单封阅读页。范围为最近最多 100 封已同步收件箱邮件；正文不因生成总结额外下载。细节见 [邮箱接口](../modules/mail/README.md#文件夹与日周总结-api)。
