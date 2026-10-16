# 共享 AI 服务

共享服务直接调用 DeepSeek 官方 `https://api.deepseek.com/chat/completions`，支持 `deepseek-flash` 和 `deepseek-v4-pro`。它负责统一配置、凭据读取、文本与 JSON 生成以及外部错误处理。当前采用普通对话补全协议；DeepSeek Harness 的工具执行内核属于另一种运行方式，框架使用上述 HTTP 服务接口。

服务位于 `backend/services/ai/`，由框架启动时创建一个 `AIService(vault, store)` 实例，所有模块通过共享上下文使用该实例。模块负责挑选资料、组织提示和管理自己的结果；AI 服务仅处理调用方传入的内容。对话历史由对应模块决定如何保存，调用时通过 `messages` 显式传入。

## 设置和凭据

普通设置保存在 Store 的 `ai:settings`，内容是 `enabled` 与 `model`。API Key 交给 Vault，键名为 `ai:deepseek`，值为 `{"api_key": "..."}`，以 Windows 当前用户的 DPAPI 加密保存到 `framework/.private/vault.dpapi`。`.private/` 由项目忽略规则统一排除；应用的 HTTP 响应只返回 `key_saved` 状态。新项目首次启动时 AI 处于关闭状态，需要用户在设置中填写自己的官方 API Key。

更新设置中的空白 `api_key` 表示沿用已保存的密钥。删除密钥时同时提交 `enabled: false` 和 `delete_key: true`。启用 AI 必须已有密钥；更新密钥和删除密钥使用独立请求。

## HTTP 接口

所有路径以 `/api/v1` 开头，请求遵守框架统一的本机访问与写入验证要求。请求及响应均使用 JSON。

| 方法与路径 | 请求 | 响应 |
| --- | --- | --- |
| `GET /ai/settings` | — | `{"enabled": false, "model": "deepseek-flash", "key_saved": false}` |
| `PUT /ai/settings` | `enabled`、`model`，可选 `api_key`、`delete_key` | 与读取设置一致 |
| `POST /ai/generate` | `prompt`，可选 `context`、`format` | `content`、`model`、`usage` |
| `POST /ai/chat` | `messages`，可选 `format` | `content`、`model`、`usage` |

`format` 为 `text` 或 `json`，默认 `text`。文本响应的 `content` 是字符串；JSON 响应的 `content` 是一个 JSON 对象。`usage` 包含 `prompt_tokens`、`completion_tokens`、`total_tokens`，由官方响应提供。

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

服务当前采用一次性完整响应，最长等待 90 秒，输出上限 6000 tokens。官方返回余额、认证、限流、网络或格式错误时，接口返回安全的 `502` 错误说明；未配置或关闭 AI 时返回 `409`，设置冲突返回 `400`，请求字段不符合约定返回 `422`。官方错误正文及密钥不写入这些说明。

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

## 验证

在项目环境中运行 `python checks/check_ai.py`。自检使用 `httpx.MockTransport` 和临时内存存储，覆盖配置、密钥边界、文本与 JSON 响应、消息校验、密钥清除和外部错误。它使用合成凭据，不产生官方 API 调用费用。
