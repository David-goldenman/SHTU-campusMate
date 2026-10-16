# 共享 AI 与插件运行时

共享服务提供基础对话、文本与 JSON 生成，以及基于 DeepSeek Harness 官方运行时的插件任务。基础接口调用 `https://api.deepseek.com/chat/completions`；插件入口通过 `deepseek-harness-sdk==0.1.5rc1` 启动官方 `sdk-minimal` 配置，由原生 Cordis 插件提供工具和业务能力。两种入口共用设置中的 `deepseek-flash` 或 `deepseek-v4-pro` 与 Vault 密钥。

服务位于 `backend/services/ai/`，由框架启动时创建一个 `AIService(vault, store)` 实例，所有模块通过共享上下文使用该实例。模块负责挑选资料、组织提示和管理自己的结果；AI 服务仅处理调用方传入的内容。对话历史由对应模块决定如何保存，调用时通过 `messages` 显式传入。

AI 工具和工作流的统一扩展方式是独立的原生 Harness 插件模块。新增能力先确定模块 ID、工具输入输出、所需服务和写操作范围，再按 [团队开发流程](DEVELOPMENT.md#开发流程) 实现。共享服务维护模型连接、Key、SDK 与运行时策略；插件维护业务能力，调用模块负责资料授权范围和结果校验。基础文本处理继续使用共享 `generate`、`chat`。

## 设置和凭据

普通设置保存在 Store 的 `ai:settings`，内容是 `enabled` 与 `model`。API Key 交给 Vault，键名为 `ai:deepseek`，值为 `{"api_key": "..."}`，以 Windows 当前用户的 DPAPI 加密保存到 `.private/vault.dpapi`。`.private/` 由项目忽略规则统一排除；应用的 HTTP 响应只返回 `key_saved` 状态。新项目首次启动时 AI 处于关闭状态，需要用户在设置中填写自己的官方 API Key。

更新设置中的空白 `api_key` 表示沿用已保存的密钥。删除密钥时同时提交 `enabled: false` 和 `delete_key: true`。启用 AI 必须已有密钥；更新密钥和删除密钥使用独立请求。

## HTTP 接口

所有路径以 `/api/v1` 开头，请求遵守框架统一的本机访问与写入验证要求。请求及响应均使用 JSON。

| 方法与路径 | 请求 | 响应 |
| --- | --- | --- |
| `GET /ai/settings` | — | `{"enabled": false, "model": "deepseek-flash", "key_saved": false}` |
| `PUT /ai/settings` | `enabled`、`model`，可选 `api_key`、`delete_key` | 与读取设置一致 |
| `POST /ai/generate` | `prompt`，可选 `context`、`format` | `content`、`model`、`usage` |
| `POST /ai/chat` | `messages`，可选 `format` | `content`、`model`、`usage` |
| `GET /ai/plugins` | — | `plugins`，包含模块 ID、启停与状态 |
| `POST /ai/run` | `prompt`、`plugins`，可选 `context` | `content`、`model`、`session_id`、`tools` |

`generate` 和 `chat` 的 `format` 为 `text` 或 `json`，默认 `text`。文本响应的 `content` 是字符串；JSON 响应的 `content` 是一个 JSON 对象。它们的 `usage` 包含 `prompt_tokens`、`completion_tokens`、`total_tokens`，由官方响应提供。

生成请求示例：

```json
{
  "prompt": "概括资料中的三件重点事项，并保留来源链接。",
  "context": "调用模块整理的资料正文与来源链接",
  "format": "text"
}
```

对话请求示例：

```json
{
  "messages": [
    {"role": "system", "content": "根据用户提供的资料回答，并注明资料不足的地方。"},
    {"role": "user", "content": "请总结以下资料：……"}
  ],
  "format": "text"
}
```

`prompt` 长度为 1–16000 字符，`context` 至多 120000 字符。对话支持 1–100 条消息，角色为 `system`、`user` 或 `assistant`，每条内容为非空字符串，全部内容合计至多 120000 字符。HTTP 入口校验这些限制，模块在服务端直接调用时遵守相同约定。

基础生成与对话采用一次性完整响应，官方请求最长等待 90 秒，输出上限 6000 tokens。官方返回余额、认证、限流、网络或格式错误时，接口返回安全的 `502` 错误说明；未配置或关闭 AI 时返回 `409`，设置冲突返回 `400`，请求字段不符合约定返回 `422`。官方错误正文及密钥不写入这些说明。

## 模块接入

后端模块使用统一上下文中的共享 AI 实例：

```python
answer = context.ai.generate(
    prompt="总结这段资料，保留原文给出的来源链接。",
    context="由本模块读取并整理的资料",
    format="text",
)
text = answer["content"]

answer = context.ai.chat(
    messages=[{"role": "user", "content": "将这段文本归类为 JSON：……"}],
    format="json",
)
```

前端模块通过共享 API 客户端调用同一组 HTTP 接口。API Key 的读写和官方请求统一经过本服务，模块只提交与自身职责相关的资料。发送前由模块决定内容范围，并在需要时告知用户数据将送往 DeepSeek；账号密码、Cookie 和会话令牌应留在认证服务中。引用来源、课程关联、分类规则、对话保存和结果呈现由使用该服务的模块实现。

## 原生 Harness 插件

需要 AI 调用工具完成工作的新增功能使用独立模块 ID，在该模块的 `harness/` 中实现。框架负责凭据、官方运行时启动和模块生命周期；提示、工具、业务处理和结果校验由模块维护。一个目录同时拥有页面、Python API 和原生插件时，它们共用模块的启停与刷新。基础 AI 助手页面负责资料选择与结果展示，具体工具由独立插件模块提供。

```text
modules/<id>/
  module.json
  harness/
    package.json
    index.js
  server/
    __init__.py
  web/
    index.js
```

`harness/package.json` 使用标准 npm 包格式，提供 `name`、`type: "module"` 与 `main`。入口导出 Cordis 的 `apply(ctx, config)`，通过 `inject` 声明所需服务；使用 `ctx.tools.register(defineTool(...))` 注册工具。完整示例是 [校园截止时间工具](../modules/deadlines/harness/index.js)。官方 `dsh.bundle.patch` 包也可放在该目录，由原生包管理流程加载它的配置层。入口和配置文件位于自己的 `harness/` 目录内。

`GET /ai/plugins` 列出带 `harness/` 的模块，返回已启用、停用或加载失败的记录；调用方按 `status: "ready"` 选择可用能力。插件的 `id` 是宿主模块 ID，`package.json.name` 是 npm 包名。纯插件模块可以只提供 `module.json` 和 `harness/`，由共享 `/ai/run` 调用。通过现有模块管理启用、停用和刷新，调用时显式选择 1–16 个模块 ID。

服务端签名为 `context.ai.run(prompt, context=None, *, plugins)`。共享 AI 方法是同步调用，在异步模块路由中使用线程池：

```python
from fastapi.concurrency import run_in_threadpool

result = await run_in_threadpool(
    context.ai.run,
    prompt="按截止时间整理所选事项，保留资料来源。",
    context=selected_text,
    plugins=["deadlines"],
)
text = result["content"]
```

```json
{"prompt":"按截止时间整理所选事项","context":"调用方选择的资料","plugins":["deadlines"]}
```

前端使用 `context.services.ai.plugins()` 和 `context.services.ai.run(body)`。`run` 的 prompt 长度为 1–16000 字符，context 最长 120000 字符；plugins 需要唯一，值对应模块 ID。响应 `content` 是最终文本，`tools` 是 `{id,name,is_error}` 数组。调用未启用的插件返回 404；任务执行中，相关模块的停用、刷新和清数据返回 409；初始化、插件安装、模型或运行时错误返回安全的 502 说明。

任务响应示例：

```json
{
  "content": "已按明确截止时间整理所选事项。",
  "model": "deepseek-flash",
  "session_id": "session-example",
  "tools": [{"id":"call-example","name":"order_deadlines","is_error":false}]
}
```

`content` 为模型最终文本，结构化业务结果由调用模块提出格式要求并校验；`tools` 表示实际工具调用及错误状态。普通工具错误由运行时交还模型，模型仍可能完成该任务并返回 200。`session_id` 用于标识这次任务，当前入口按独立任务执行并清理会话；连续对话的历史由调用模块管理。未启用 AI 返回 409，空插件数组或重复模块 ID 返回 422，同一任务中的 npm 包名冲突返回 400。插件必须处于 `ready` 状态；已停用、缺失或加载失败的插件返回 404。

每次任务创建独立官方运行时，用 `dsh plugin add file:<插件目录>` 安装所选包，再按官方 SDK 协议执行。包管理需要 PATH 中的 pnpm，普通运行时由 Python 依赖自带。原生包的第三方依赖遵循它的 package.json；运行时内置的 Cordis 与工具接口可声明为可选 peerDependencies。直接插件按 `main` 挂载，bundle 按自己的原生配置层挂载。依赖其他服务的插件需要在 bundle 中显式组合这些服务；兼容范围是服务端 Cordis 插件及其所依赖的当前版本接口。纯前端插件使用校园模块的网页入口开发。

原生 `apply(ctx, config)` 接收 Cordis 上下文。普通插件使用默认配置，专用配置和服务依赖由插件的原生 bundle 组合。Python 的 `ModuleContext` 由模块后端使用；工具 `execute(args, execution)` 接收经 schema 校验的模型参数和取消信号。模块通过公开校园数据 API 选择输入，将资料作为 `run.context` 文本提交；工具补充校验日期、标识和大小等业务约束，并响应 `execution.signal`。

业务后端在返回或保存结果前校验输出 schema、资料引用、账号版本及工具错误。持久化使用模块的 Store 或 data_dir。涉及写入时，由相应公开接口校验当前账号和操作参数；普通插件配置及源代码保存非秘密配置，用户秘密由模块 `context.secrets` 或共享 Vault 管理。

当前任务配置将默认工具范围交给所选插件，并关闭官方最小配置中的 Shell、文件工具、目录切换工具和会话日志上传组件。包安装、缓存、工作目录和 SDK 会话位于本项目 `.codex/`，任务结束时释放运行时并删除临时会话。每次启动会产生额外等待；一次任务可以多轮调用模型，SDK 单次请求或通知等待上限为 90 秒，每轮输出上限为 6000 tokens。业务持久结果仍由模块保存到自己的数据目录。

插件是受信任的本地代码，与宿主拥有相同系统权限，所选插件也会运行在持有 AI 凭据的进程内。安装前审核代码与外部访问行为；宿主目录约定用于协作和数据管理。工具的注册和清理由 Cordis 的 effect 生命周期管理，后台工作同样需要在插件释放时结束。

原生插件开发以 [官方 Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md) 和 [工具开发接口](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-tool.md) 为准；项目锁定 SDK 版本，升级时运行原生插件检查。AI 助手页面的“插件任务”使用所选缓存资料和插件工具，校验最终 JSON 与资料引用，并展示工具调用状态。

## 验证

在 WSL 运行 `bash ./check.sh`。基础 AI 检查使用 `httpx.MockTransport` 与内存存储；`checks/check_harness.py` 启动实际官方运行时，对接本地模拟模型，覆盖工具执行、参数校验、原生 bundle、热更新、运行中生命周期与密钥边界。模块检查验证资料、输出 schema 和界面使用的接口；学习资料集成检查验证 ELRC/Piazza 缓存进入助手与插件任务。检查使用合成凭据，所有临时资料位于 `.codex/`，不产生官方 API 调用费用。
