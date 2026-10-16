# 统一 HTTP API

开发入口为 `http://127.0.0.1:16666`，基础路径 `/api/v1`。通过命令行预览端口或设置修改端口时，所有相对路径保持一致。`GET /api/openapi.json` 返回共享服务与框架的 OpenAPI，`/api/docs` 提供交互式界面；每个后端模块另有 `/api/v1/modules/<id>/openapi.json`。

## 本地访问规则

服务仅绑定 `127.0.0.1`，校验 Host 与 Origin。先调用 `GET /api/v1/bootstrap` 获取本次服务的 `csrf_token`，后续 POST、PUT、PATCH 和 DELETE 都在请求头带 `X-Framework-Token: <csrf_token>`。服务重启后重新获取。浏览器共享 `api()` 及模块注入的 API 客户端自动处理该请求头。

JSON 请求使用 `Content-Type: application/json`。成功响应是直接 JSON；失败通常为 `{ "detail": "说明" }`，字段校验失败为 `{ "detail": [{ "loc": [...], "msg": "说明", "type": "类型" }] }`。字段校验响应保留定位信息。HTTP 400 表示参数或本地环境不符合服务要求，401 表示需要登录，403 表示本地访问校验失败，404 表示资源未启用或不存在，409 表示需要二次验证、AI 未启用、模块忙或停止失败，422 表示请求字段不符合定义，502 表示外部服务失败。模块可以用自己的可公开错误信息补充这些状态。

## 框架与设置

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/bootstrap` | `{version, csrf_token, categories, settings, modules}`；分类按侧栏顺序返回 |
| GET | `/settings` | `{port, active_port, restart_required, storage:{directory,encryption}}` |
| PUT | `/settings` | 请求 `{port:16666}`，返回完整设置；修改后重启生效 |
| POST | `/data/clear` | `{scope:"credentials"\|"modules"\|"all", confirmation:"CLEAR"}` → `{cleared:scope}` |

端口范围为 1024–65535，浏览器限制端口在系统边界拒绝。默认保存端口 16666，`--port` 只覆盖当次运行端口。

清除 `credentials` 时停止模块及登录窗口，清除 Vault 中所有共享和模块秘密、认证状态，并关闭 AI，再挂载模块；普通模块数据保留。清除 `modules` 时停止模块、清除全部模块状态、秘密和文件，再挂载模块；共享登录、AI 与框架设置保留。`all` 执行两类清除并恢复默认设置，当前监听端口持续到服务重启。模块代码与清单始终由开发者维护，数据清除操作只处理本地数据。

## 模块管理

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/modules` | `{modules:[ModuleInfo]}` |
| POST | `/modules/reload` | 扫描模块目录、释放并重新加载，返回 `{modules:[ModuleInfo]}` |
| PUT | `/modules/<id>` | `{enabled:true\|false}`，返回 `{modules:[ModuleInfo]}` |
| 任意 | `/modules/<id>/<route>` | 模块自己的公开后端接口，由该模块文档说明 |

`ModuleInfo` 包含 `id`、`name`、`version`、`category`、`enabled`、`status`、`frontend_url`。有效入口另有 `api_version:1` 和 `harness` 布尔值，已就绪模块包含当前 `revision`；失败时包含可公开的 `error`。状态为 `ready`、`disabled` 或 `error`。后端或纯插件模块的 `frontend_url` 为 `null`。`harness:true` 表示模块提供原生 Harness 入口。

前端资源入口由服务返回，例如 `/module-assets/notes/<revision>/web/index.js?v=<revision>`。模块应原样使用入口地址和相对导入，版本路径覆盖其子资源。停用或更新后，旧版本资源返回 404。模块接口热切换前要求相关请求完成；有执行中请求返回 409，调用方在完成后重试。

## 共享认证

提供方 ID 为 `gradescope`、`piazza`、`ids`、`coremail`。IDS 的 `target` 为 `blackboard`、`elrc`、`timetable`，默认 `blackboard`。接口仅负责认证和会话，内容读取由业务模块自己的 API 实现。

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/auth/providers` | `{providers:[ProviderStatus]}` |
| GET | `/auth/<provider>/status` | 单个 `ProviderStatus`；读取已保存状态 |
| PUT | `/auth/<provider>/credentials` | `{username,password}` → `ProviderStatus` |
| POST | `/auth/<provider>/login` | 可选 `{target}`，登录或验证会话，返回状态 |
| POST | `/auth/<provider>/browser` | 可选 `{target}`，打开独立验证窗口 |
| POST | `/auth/<provider>/import-session` | 可选 `{target}`，导入、探测、加密保存并关闭临时窗口 |
| DELETE | `/auth/<provider>` | 清除此提供方的本地凭据、会话与临时验证资料 |

`ProviderStatus` 含 `id`、`name`、`username`、`has_password`、`has_session`、`status` 以及可选的 `message`、`checked_at`、`targets`。Cookie、密码、登录票据和 Coremail sid 仅由服务端使用。二次验证在用户可见的登录窗口完成。Python 内部使用 `context.auth.authenticated_client(provider, target=None)`，完整例子与过期策略见 [认证文档](AUTH.md)。

## 共享 AI

| 方法 | 路径 | 请求或响应 |
| --- | --- | --- |
| GET | `/ai/settings` | `{enabled, model, key_saved}` |
| PUT | `/ai/settings` | `{enabled, model, api_key?, delete_key?}` → 安全配置状态 |
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

新增 AI 工具与工作流使用独立模块的原生插件，统一经过 `/ai/run`；基础文本功能使用 `/ai/chat` 和 `/ai/generate`。共享契约维持 `api_version:1`，业务输出 schema、资料引用与持久化约定由模块 API 定义，并随功能 PR 更新。
