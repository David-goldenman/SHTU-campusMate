# 教育 System Prompt · QJQ

归属今日讨论中的「教育 system prompt 优化 QJQ」。从 QJQ 迁入五种教育模式的 System Prompt、回答 Schema 与逐字引用校验，挂载在**AI助手**。

## 使用

先在框架设置中配置共享 DeepSeek 服务。在 AI助手填写问题，选择答疑、分步提示、自测、学习计划或通知核对；可检索 ELRC 本学期已同步资料，也可手动补充一段原文。勾选资料后可先「预览请求」，再点击「发送所选资料并生成」。

预览只组装请求，不调用远程模型。生成通过 `context.ai.chat(..., format="json")`，只发送当前问题、学习模式和所选资料；最多 12 条证据，每条 4000 字。回答须符合 Schema，引用 ID 与引文须出现在提供的原文中；没有引用时必须明确记录不确定性。校验通过只说明格式与引文有效，不代表结论已经由老师或人工核实。

ELRC 关闭或尚未同步时仍可手动输入资料。检索走其公开 `GET /api/v1/modules/elrc/catalog` 与 `/search` 接口；没有跨模块 Python 导入或私有数据读取。切页会取消前端请求、移除监听器与模块样式。本模块没有后台任务，不在本地持久化提问或回答；已经提交给共享 AI 服务的请求可能在页面关闭后继续完成。

## 接口

前缀为 `/api/v1/modules/education`。

| 接口 | 请求/用途 |
| --- | --- |
| `GET /modes` | 模式名称和输入限制 |
| `POST /preview` | `{question, mode, sources}`，返回组装的 `messages`，`calls_ai:false` |
| `POST /answer` | 同样的请求，返回 `{answer, model, usage}` |

`sources` 至少包含唯一的 `source_id` 与 `text`；可包含 `source_kind`、`course_name`、`semester`、`lesson_label` 和起止秒数。`answer` 包含 `mode`、`answer`、`citations`、`uncertainty`、`next_steps`。模型输出校验失败返回安全的 502 提示，不把未验证回答展示为成功结果。

## 本次迁移范围

| 成员 | 模块 | 从原材料复用的部分 |
| --- | --- | --- |
| QJQ | `modules/elrc` | 虚拟社区课程、转写、学校摘要、检索 |
| QJQ | `modules/education` | 五种教育提示词、Schema、引用校验 |
| WYT | `modules/piazza` | 分享包中的 Piazza 只读采集、帖子/回复/附件解析与重要程度规则 |

根据用户要求，微信和 QQ 暂不接入。原分享 ZIP 含 QQ，所以没有把整包提交。QJQ 的旧独立 UI、学习计划数据库与复习包工作台、群聊总结、桌面安装器、本机环境、配置、缓存和验收截图也不属于这次三项模块迁移。原始本地材料未修改。主框架、公共 UI、认证、AI、依赖和锁定文件保持现有接口，本次提交只位于这三个模块目录。

## 检查

在仓库规定的 WSL + uv 环境中（先设置 `UV_PROJECT_ENVIRONMENT="$PWD/.codex/venv"`、`UV_CACHE_DIR="$PWD/.codex/uv-cache"`）：

```sh
uv run python modules/education/checks/check_modules.py
bash ./check.sh
node --check modules/elrc/web/index.js
node --check modules/education/web/index.js
node --check modules/piazza/web/index.js
```

集成检查使用临时目录 `.codex/tmp/`、内存秘密存储、`httpx.MockTransport` 与合成 AI；不读取用户账号，不访问真实学校/Piazza，不产生 AI 费用。覆盖三模块完整请求链、原文时间轴、学期隔离、失败保留缓存、重复采集/已读状态、引用拒绝、CSRF、OpenAPI、启用/停用/刷新。
