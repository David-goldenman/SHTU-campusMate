# 图片与扫描课件读取

学习助手有两条读取路径：用户确认支持图片且效果合适的视觉模型直接读取页面；其他情况使用本地文字提取与 OCR。配置不会改变日常对话模型。默认自动选择，未配置视觉模型时使用本地路径。

## 用户配置

1. 设置 → AI 服务 → 图片识别模型：填写 API 地址、协议、模型 ID 和独立 API Key。支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages，由现有官方 Harness 适配器发送图片。确认接口支持图片、效果适合使用，并允许发送所需图片后保存。密钥加密保存在本机，不回显；更换地址需重新提供密钥。暂停顶部 AI 服务会同时暂停识图。
2. 首页学习助手 → 对话操作 → 资料读取：选择自动、优先直接识图、仅文字提取与本地 OCR；可控制识图失败后的回退、本地 OCR 后端和每次读取 1–4 页。
3. Windows 默认使用已安装的中文或英文系统 OCR。Docling 是可选增强环境，单独安装后填写其 Python 可执行文件路径。

“仅文字提取与本地 OCR”控制图片处理位置，提取的文字仍会随问题交给所选对话模型。应用不会仅凭模型名称判断视觉质量；质量确认来自用户。更换模型、协议或地址时界面会清除能力与质量确认。

## 处理范围

- PDF 使用物理页码，PNG/JPEG/WebP 作为单页图片。按请求页范围渲染，长边最多 2200 像素；单文件至多 30 MB，PDF/PPTX 至多 1000 页。
- 本地路径优先提取文字层，Windows OCR 对短于 40 个非空白字符的 PDF 页再尝试识别。这是决定是否尝试 OCR 的简单规则，不是解析质量评分。选择 Docling 时，对所读 PDF 页逐页增强解析；希望解释图示时，可以启用已确认的视觉模型。
- PPTX 保留现有文字提取与演示顺序；图片、图表及公式排版需导出 PDF 后读取。旧版 PPT 与加密 PDF 暂不处理。
- 关键词优先定位已有文字层；返回 `processed_pages/next_page/search_scope/unreadable_pages`。扫描页尚未读取不能被解释为没有相关内容。
- 引用分别标注文字层、识图转录、OCR 转录与 AI 图像解释。识别转录可能有误，图像解释不能冒充教师原文。

识图失败且允许回退时，保留可提取文字，必要时运行本地 OCR，并返回实际方式与提示。失败后的回退结果不固定缓存，以便下次重新尝试。没有可读结果时明确返回未读页。停用模块、停止回答、切换账号、修改读取设置或视觉配置时，取消任务并拒绝保存过时结果。

## 可选 Docling 环境

Docling 不加入默认安装包，避免所有用户承担模型与深度学习依赖。开发与用户环境均可使用独立 Python；例如在项目目录执行：

```powershell
uv venv .private/runtime/docling --python 3.12
uv pip install --python .private/runtime/docling/Scripts/python.exe "docling==2.140.0"
```

若 Windows 的 uv 安装脚本被本机安全软件拦截，可在该独立环境使用标准 pip 安装。然后在“资料读取”选择 Docling，填写 `.private/runtime/docling/Scripts/python.exe` 的完整绝对路径。首次使用可能下载模型，应提前准备并用不含个人资料的扫描页检查。模型下载与本地 OCR 不会发送课件给模型 API；本文没有承诺模型仓库在所有网络均可访问。

## 开发接口与边界

共享 AI 只负责独立视觉连接与通用图片调用：

- `GET/PUT /api/v1/ai/vision/settings`：`enabled/base_url/protocol/model/supports_images/quality_confirmed`；写入还可带 `api_key/delete_key`。读取仅返回 `key_saved/ready/revision` 等公开状态。
- `context.ai.vision(prompt, images, expected_revision=..., check_cancelled=...)`：图片使用 `{media_type, data}`（Base64）；最多 4 张、编码合计 16 MB。任务使用自己的临时 Harness 工作区和官方附件服务，结束后清理。
- `GET/PUT /api/v1/modules/academic-assistant/reader/settings`：`mode/fallback/ocr_backend/docling_python/max_pages`；配置属于学习助手，不放入框架。
- 课程文件下载继续调用来源模块公开接口。来源文件、文字层和页级结果按账号隔离。来源版本变化替换缓存；解析方式、设置版本和视觉配置变化使增强结果失效。

文件解析、PDF 渲染和 OCR 在受管理的工作进程中运行，每个学习助手实例一次处理一个文件。工作进程不读取学校凭据；视觉 Key 留在共享服务。当前能力复用 `study_document`，没有引入第二个 agent 框架或独立数据库。

## 验证

`checks/check_ai_vision.py` 使用本地模拟 API 验证官方 Harness 三种协议的图片请求与独立凭据，不调用真实付费模型。`modules/academic-assistant/checks/check_reader.py` 覆盖选择策略、缓存、用户禁用、回退、失败重试、过时配置、进程取消与扫描 PDF 渲染。Windows 实机可加 `--live-ocr`；Docling 实机可加 `--docling-python <Python绝对路径>`。浏览器检查运行 `node checks/check_document_ui.mjs <本机地址>`。完整回归沿用 `check.ps1/check.sh`。

接口依据：[OpenAI 图片输入](https://developers.openai.com/api/docs/guides/images-vision)、[Harness 模型配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)、[Docling 本地配置](https://docling-project.github.io/docling/usage/advanced_options/)。
