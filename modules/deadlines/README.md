# 截止时间整理

独立的原生 DeepSeek Harness 插件模块，在设置中启停和刷新。AI 助手的“插件任务”选择本模块后，可调用 `order_deadlines` 按明确截止时间排列所选事项。时间顺序用于安排参考，提交状态与开放能力以原始资料为准。

`harness/package.json` 是标准 npm 包，`index.js` 导出 Cordis 的 `apply` 并注册工具。输入为 `items:[{id,title,due_at}]`，最多 400 项；截止时间采用带时区的有效日期，输出为保留原字段的排序结果 JSON 字符串。模块以原生工具入口运行，页面与资料选择由调用模块提供。后端使用 `context.ai.run(prompt=..., context=..., plugins=["deadlines"])`，HTTP 入口为 `POST /api/v1/ai/run`。

工具的注册与释放遵循 Cordis effect 生命周期。任务运行时，宿主保护本模块的生命周期；结束时释放官方运行时。模块使用调用方显式传入的资料。`checks/check_harness.py` 用真实官方运行时与本地模拟模型验证工具、参数、bundle、更新和边界，验证资料位于项目 `.codex/`。
