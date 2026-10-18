# CampusMate 技术与第三方资源说明

AAA罗德岛工程部    2026 年 10 月 18 日

CampusMate 采用本地网页、模块化后端与 DeepSeek Harness 原生插件，连接校园学习资料并支持带依据的问答和本地安排操作。本文说明技术架构、数据处理、主要依赖及第三方资源的用途和授权状态。版本依据为 2026 年 10 月 18 日的项目源码、uv.lock、随包许可证与素材记录。

## 总体架构

| 层次 | 主要实现 | 职责 |
| --- | --- | --- |
| 网页界面 | 原生 JavaScript ES Modules | 导航、课程与作业界面、邮件、时间表、流式对话、响应式主题 |
| 主框架 | Python 与 FastAPI | 模块发现、路由、启停、设置、普通状态存储与通用 UI 接口 |
| 共享认证 | 官方登录窗口与会话客户端 | 凭据加密、会话复核、账号版本及各平台连接 |
| 共享 AI | 官方 Harness SDK 与运行时 | 提供商配置、模型调用、原生 Cordis 插件及任务生命周期 |
| 业务模块 | modules 下的独立目录 | 来源解析、资料选择、业务工具、结果校验及本地操作 |

模块通过注入上下文与文档化 API 协作。框架提供导航、存储、凭据、AI 和模块调用接口；业务规则留在所属模块。模块停用时取消请求和后台任务，保留自身持久数据；依赖缺失时返回明确的不可用或部分结果。主题通过清单加载样式或替换视图，继续使用相同业务接口。

## 运行环境

主要运行环境为 Windows x64、Python 3.12、本机 Microsoft Edge 和 Node.js 22 及以上版本。uv 根据 pyproject.toml 与 uv.lock 准备 Python 环境；Harness 原生插件使用 pnpm，项目可通过 Corepack 提供本地工具。双击 run.cmd 或执行 .\run.ps1 启动本地网页，stop.cmd 用于停止。

## 模块组成

当前共有 19 个模块。来源层包括教务、Blackboard、Gradescope、Piazza、ELRC、E 云课堂和校园邮箱；聚合层包括课程中心、作业管理、时间表、学习通知和校园总览；AI 相关模块包括学习助手、AI 工具、课程学习助手、校园后台助手和截止时间整理；延伸模块为校园地图和群消息。

## 资料处理与 AI 工作流

### 登录和资料同步

共享认证分别管理 IDS、Coremail、Gradescope 与 Piazza。用户在官方独立窗口完成登录，应用复核会话后由业务模块读取课程、作业和邮件。IDS 可在用户确认后绑定独立本机设备凭据，以恢复登录；邮箱支持 IMAP 专用密码及网页会话。

来源先保留可用缓存，再在后端执行同步。页面切换不终止来源同步，返回后读取当前进度。账号、资料与偏好使用版本标识；异步结果写入前复核版本，避免将旧账号结果保存到当前账号。跨模块导入携带稳定来源标识，重复导入保留用户编辑。

### 带引用的查询与回答

学习助手经官方 Harness 加载团队编写的原生插件，按问题调用业务工具。课程资料选择统一通过课程中心的 POST /context 完成；插件再使用来源模块公开接口读取所需内容。最终回答由业务模块校验引用和账号版本后保存，界面展示原文、页码及来源入口。

PDF 优先提取文字层，PPTX 按演示顺序读取文字；扫描页与图片可使用 Windows 本地 OCR、可选 Docling，或经用户确认的视觉模型。系统区分文件原文、OCR 转录和图像解释。模型调用仅发送当前任务所需的资料，使用用户配置的服务与 API Key。

### 本地写入与活动确认

时间表修改通过带账号版本、请求 ID 和记录版本的命令接口执行，返回变更前后内容、影响数量与冲突检查。相同请求重复提交返回原回执，防止重复新增。请假、停课与调课记录属于本地覆盖，不代办学校端审批。活动由通知提出建议，经用户明确参加确认后加入时间表。

## 存储与隐私

密码、会话票据、设备私钥及模型 Key 由 Vault 统一保存，在 Windows 使用当前用户 DPAPI 加密。普通设置与缓存使用本地 SQLite 和模块数据目录，普通业务资料不因此视为全部加密。私有目录为 .private/，运行环境与浏览器资料由 .private/runtime/ 管理，开发验证资料放在 .codex/。

资料、会话、偏好与建议按账号隔离。课程群仅处理用户授权的本人本机来源；群原文不进入其他后台工作流。演示使用匿名或合成身份、群名和个人安排，课程事实与必要短摘录保留来源，不随演示材料分发原始私有缓存和凭据。

## 主要 Python 依赖

以下为 uv.lock 锁定的直接依赖及本机安装包中的许可证。DeepSeek Harness 的内部依赖继续适用上游各自的许可；完整传递依赖以锁定文件和上游第三方声明为准。

| 组件 | 锁定版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| deepseek-harness-sdk | 0.1.5rc1 | 官方 Agent 运行时接入 | MIT |
| shanghaitech-ids-passkey | 0.1.0 | IDS 设备凭据与登录 | 随包 LICENSE 为 MIT |
| fastapi | 0.143.1 | HTTP API 服务 | MIT |
| uvicorn | 0.54.0 | ASGI 服务器 | BSD-3-Clause |
| httpx | 0.28.1 | HTTP 与代理客户端 | BSD-3-Clause |
| beautifulsoup4 | 4.15.0 | 网页内容解析 | MIT |
| cryptography | 50.0.2 | 密钥与签名处理 | Apache-2.0 或 BSD-3-Clause |
| filelock | 4.2.0 | 跨进程文件锁 | MIT |
| pypdf | 6.20.1 | PDF 文字与页结构 | BSD-3-Clause |
| pypdfium2 | 5.14.0 | PDF 页渲染 | BSD-3-Clause、Apache-2.0 及底层依赖许可 |
| Pillow | 12.3.0 | 图像处理 | MIT-CMU |
| tzdata | 2026.5 | Windows 时区数据 | Apache-2.0；时区数据另见随包声明 |
| zstandard | 0.25.0 | 压缩内容解码 | BSD-3-Clause |
| defusedxml | 0.7.1 | 受约束的 XML 解析 | PSFL |

### 固定版本与许可依据

IDS 组件固定到提交 7c4df62716ceb3d94452d22f3d07f19ff1b8db8b，来源为 vvbbnn00/shanghaitech-ids-passkey。锁定版本安装包附带 MIT LICENSE，版权声明为 Copyright (c) 2026 vvbbnn00，项目保留其原始许可与署名。

官方 Harness SDK、运行时及 Cordis 插件机制用于通用 Agent 能力，校园业务工具与工作流由团队编写。MIT、BSD、Apache 等许可的版权及声明要求继续随相应组件适用；本项目的原创声明不替代这些许可。

## 其他第三方代码与外部数据

| 资源 | 实际用途 | 来源与许可 |
| --- | --- | --- |
| markdown-it 15.0.3 | 网页 Markdown 渲染；本地提供官方 ESM 包 | MIT；原 LICENSE 保存在 web/vendor/markdown-it/ |
| Font Awesome Free 6.7.2 | 体育课程使用 person-running.svg | SVG 为 CC BY 4.0；保留图内署名及 web/vendor/fontawesome/LICENSE.txt |
| wcdb-key-tool 的底层片段 | 微信只读接入的 Cipher 结构及 WCDB 常量适配 | TANGandXUE / CloudDreamAI，MIT；保留 native/WCDB_LICENSE.txt |
| OpenStreetMap | 校园道路、水系、绿地与室外步行路网 | © OpenStreetMap contributors，ODbL 1.0；界面保留署名 |
| 学校官方地图及公开网页 | 建筑轮廓、名称、校门、电梯位置与公开校历等 | 保留学校来源及查阅信息；现有材料未附统一开放许可 |
| coordtransform 2.1.2 | 离线导入时转换 OSM 坐标；运行时不需安装 | wandergis/coordtransform，MIT |
| OneBot 接口服务 | QQ 本机消息接入；可由用户独立部署 NapCat 等服务 | 项目调用接口，不随产品打包 QQ 或服务端；遵守所选发行版许可 |
| Windows OCR 与可选 Docling | 本地扫描页识别 | 系统 OCR 随 Windows；Docling 为独立可选环境，其软件及模型按实际安装版本许可 |

### 数据使用范围

OSM 衍生底图与路网按 ODbL 保留来源、稳定要素标识及相应许可，和学校建筑数据分开保存。学校公开网页可访问这一事实不等同于取得开放再分发许可。地图中的入口、施工、无障碍与通行信息仍需现场核验，路线为室外试用结果。

Blackboard、Gradescope、Piazza、Coremail、教务与教学社区等平台的名称、服务和课程内容属于相应权利人。项目通过用户本人可访问的账号读取资料，遵守平台使用要求；课程文件、邮件原文和个人记录不因接入本项目而转为团队作品或开放数据。

用户配置的模型 API 属于外部服务，按相应提供商条款使用。产品不附带模型权重；启用视觉模型时，界面另外确认图片发送范围。

## UI 参考与图像资源

工程功能设计的外部参考为 DeepSeek Harness 的 Agent 与原生插件机制。明日方舟及 Hermes Agent 官网均用于 UI 视觉参考；Hermes 的功能设计与工程实现未用于本项目。Default 主题采用 Nord 配色，通用组件层级参照项目中记录的 Material 3 设计规范。

| 资源类别 | 项目中的使用 | 权利与记录 |
| --- | --- | --- |
| 明日方舟视觉语言 | PRTS 终端布局、黑白工业面板和人物展示；参考官网及主题 README 列示的 UI 资料 | 视觉参考与实际美术素材分别说明；相关品牌权利归原权利人 |
| 明日方舟实际美术与对白 | amiya.png、两张 rhodes-deck 场景图及人物对白 | 来源为公开素材镜像；角色、场景和对白权利属于鹰角网络及相关权利人，现有材料未附专项授权证明 |
| Hermes Agent 官网 | 观星台和星夜手记的古典图像表达与版式参考 | Nous Research 官网视觉参考；主题主图通过独立提示词生成，记录见 art-prompts.json |
| 项目品牌与艺术插图 | 校园品牌图、艺术主题主图和人物图像 | 团队提供设计输入并经生成式 AI 辅助制作或处理；记录见 docs/BRAND.md 与主题素材说明 |
| 校园照片 | 蓝白艺术主题的校园轮播图 | 由用户提供原照片后进行生成式风格处理；保留来源文件名与 campus-prompts.json |
| Nord 与 Material 3 | 默认主题配色及通用组件组织规范 | Nord 项目为 MIT；Material 3 为公开设计规范，外部标识及素材保留原权利归属 |

### 授权说明

公开素材镜像提供下载路径，并不自动授予原始游戏美术的再分发权。PRTS 中的游戏素材属于第三方资源，其使用应符合权利方规则；对需要另行授权的分发与宣传用途，应取得相应授权。团队自行编写的主题代码与第三方美术的权利分别归属。

生成式图像的输入、提示词与处理记录保存在项目素材目录。校园原照片和外部视觉参考仍保留各自来源与权利，不将生成处理等同于取得原素材的全部权利。项目主品牌资料、主题图像与实际游戏素材分别记录。

## 验证范围与交付状态

仓库统一入口为 Windows check.ps1 与 WSL check.sh，覆盖框架、模块接口、启停与重新启用、依赖缺失、共享认证、官方 Harness 及相关前端行为。自动回归使用合成账号、模拟 HTTP 和模型，避免将真实私有资料写入夹具。

docs/LIVE_ACCEPTANCE.md 记录 2026 年 10 月 16 日起的真实来源登录、基础同步、重启恢复与学习助手资料问答。不同来源、附件格式及日期的范围分别记录；E 云课堂、扫描件增强和新增交互按对应模块记录继续验收。群消息真实课程群增量、地图现场条件和手机日历实机导入属于后续验证事项。

## 上游资源与本地记录

[DeepSeek Harness 官方源码与 MIT 许可证](https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE)

[shanghaitech ids passkey 官方仓库](https://github.com/vvbbnn00/shanghaitech-ids-passkey)

[wcdb key tool 上游仓库](https://github.com/TANGandXUE/wcdb-key-tool)

[Font Awesome Free 许可说明](https://fontawesome.com/license/free)

[OpenStreetMap 版权与 ODbL 说明](https://www.openstreetmap.org/copyright)

[coordtransform 上游仓库](https://github.com/wandergis/coordtransform)

[上海科技大学官方地图](https://map.shanghaitech.edu.cn/)

[明日方舟官方网站](https://ak.hypergryph.com/)

[阿米娅立绘的素材镜像记录](https://github.com/ArknightsAssets/ArknightsAssets2/blob/cn/assets/dyn/arts/characters/char_002_amiya/char_002_amiya_1.png)

[Hermes Agent 官方网站](https://hermes-agent.nousresearch.com/)

[Nord 配色项目](https://github.com/nordtheme/nord)

[Material 3 设计规范](https://m3.material.io/)

代码与依赖依据：README.md、pyproject.toml、uv.lock、docs/MODULES.md、docs/AI.md、docs/AUTH.md、docs/DOCUMENT_READING.md，以及业务模块 README 与随包 LICENSE。

视觉与素材依据：docs/ART_THEMES.md、docs/BRAND.md、web/themes/arknights/README.md、web/themes/assets/README.md、web/themes/assets/art-prompts.json、web/themes/assets/campus-prompts.json、web/brand/prompts.json 和 web/vendor/ 下的许可文件。

