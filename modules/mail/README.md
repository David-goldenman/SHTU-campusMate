# 校园邮箱

邮箱以分类文件夹和紧凑单行列表作为默认视图，打开邮件后主区域用于正文阅读；返回后聚焦对应邮件行，加载或失败时也可返回。阅读组织参考 [Thunderbird 邮件前端](https://github.com/thunderbird/developer-docs/blob/master/thunderbird-development/codebase-overview/mail-front-end.md)，使用项目 Nord 样式。左侧包含重点关注、兴趣推荐、一般通知、已筛选、收件箱、未读及日／周总结。分类为本地智能文件夹，原邮件保留在学校邮箱；页面和单封邮件均提供官方网页入口。正文保留段落、列表、表格、对齐、强调和适当字号，过滤脚本、追踪图片及任意样式。已有正文缓存继续用于离线阅读。

## 文件夹与日／周总结 API

- `GET /folders`：`folders[{id,name,count}]`、`scope:local-inbox`、`cached_count`。分类详情继续读取 `/intelligence` 中的 `messages[].classification`，手动分类优先。
- `GET /digests?period=day|week&anchor=YYYY-MM-DD`：返回北京时间的 `start/end`、按文件夹的 `counts`、`entries`、`coverage`、`fingerprint` 和已保存的 `report`；默认当天，周一至周日。每条邮件带稳定 ID、分类、已有摘要、学校网页和 `workbench_url`。GET 使用本地缓存，不调用模型。
- `POST /digests {period,anchor?}`：按用户操作生成总结。共享 `context.ai.generate(format="json")` 只接收本期邮件 ID、时间、标题、分类和已有摘要；不为总结额外下载正文。`report` 包含 `overview/highlights[{message_id,summary}]/generated_at/model`，校验引用属于本期且不重复后保存。

总结按账号版本及日期保存。分类、手动标签或邮件变更会使对应旧总结失效；账号在生成过程中变化返回 409。无邮件返回 400，无效日期或周期返回 422，模型结果无效返回 502。覆盖范围是已同步的最近最多 100 封收件箱邮件，并返回缓存数与校方总数，不能据此宣称覆盖整个历史邮箱。其他模块使用 `context.api('mail','/digests?...')` 或 `/folders` 读取，模块停用按公共契约返回不可用；引用进入时间表仍遵循现有确认流程。

使用共享 `coremail` 认证与 sid，读取收件箱最近 100 封；正文按需读取且设置 `markRead=false`。`GET /snapshot`、`POST /sync` 为同步接口；`GET /message?message_id=mail:原标识` 返回清理后的正文与附件元数据。正文保留表格和段落，移除脚本、表单、事件与远端图片。原邮箱用于附件查看。

列表在桌面显示发件人、主题、摘要、分类和日期；窄屏顺序阅读。搜索覆盖当前文件夹的主题、发件人和摘要，输入时返回列表。分类偏好在独立表单编辑，批量复核通过“更多操作”进入；菜单支持 Esc 和点击外部关闭。纯文本换行转为段落和换行标记，清理后的 HTML 保留标题、列表、表格、粗体、居中和原文链接。正文按账号缓存，阅读不修改原站已读状态。

进入邮箱默认显示“重点关注”，其余邮件通过兴趣推荐、一般通知、已筛选和收件箱查看；文件夹显示数量，搜索限定当前文件夹。从邮件引用进入时直接显示对应原件。兴趣推荐仍可在通知中心查看，主动提醒与计数用于重点邮件；顶部铃铛提供统一通知入口。

## 偏好与语义复核

`GET/PUT /preferences` 管理按邮箱账号保存的学段、年级、专业、在修课程、形策／心理健康完成状态、兴趣及完整自然语言要求；GET 返回 `{preferences,buckets,interests}`，PUT 接收完整 preferences。兴趣模式为 `follow/digest/hide`；完成状态为 `unknown/required/done/na`。初始资料留待用户填写，兴趣类别独立保存。`GET /intelligence` 返回 `{messages:[{...message,classification}],preferences,buckets,interests}`。

四种显示位置为 `focus/recommend/digest/filter`。规则先给出保守初筛，`POST /review {message_id,force?:boolean}` 通过本模块原生 Harness 插件逐封语义复核，返回分类、摘要、理由、原文依据及可选活动。页面“复核最近邮件”每次最多五封。AI 读取完整偏好和所选正文，不执行邮件中的指令；IC 等缩写按完整词匹配，普通政治讲座与形策认定分别判断。证据须来自实际发送的标题或正文，不确定事项保留核对提示。缓存指纹包含账号、原文、偏好、模型与提示词；资料变化后重新复核。

`GET /review-context?message_id=` 为后台助手提供本次分类输入、schema、指纹及原文；按需读取正文。`POST /review-results {message_id,fingerprint,decision}` 校验 schema、资料版本和原文再保存；`POST /tools/review {decision}` 只供本模块当前 Harness 任务使用，短期令牌绑定邮件、指纹与账号。分类正文至多 14000 字符，联系方式替换后发送到共享模型服务。

形策保护只接受正文明确肯定的“计入／纳入形策”等认定，并结合用户仍需完成的设置。否定判断限定在考勤认定及其修正说明，“不需要提前报名”等独立说明不会否定明确认定；跨逗号的条件、疑问、待确认和更正仍需核对。否定、待定、互相矛盾的认定，或标题／正文仅出现“形策考勤”，均不强制改为重点。后台安排使用当前 `/review-context` 的初筛结果重新判断，不能仅信任旧分类的保护标记。语义提示词随认定规则更新，使旧提示词生成的缓存失效。

手动分类可带 `bucket`；显示位置与标签优先于规则和 AI。筛选只改变本工作台显示，原邮件保留。偏好和复核结果在本模块 Store 按账号版本保存，正文和旧标签沿用已有账号保护。校园后台助手使用这些公开 API 将重要事项送入通知中心，活动参加确认与时间校验见 [后台助手](../campus-agent/README.md)。

## 兼容接口与清理

`GET/PUT /rules` 读取或保存 `{rules:[{id,field,contains,label,enabled}]}`，最多 100 条；field 为 title、sender 或 body_text。同步后自动按首条命中规则分类，`POST /classify` 可手动重新执行。`GET/POST /labels` 读取或保存分类；保存请求为 `{message_id,label,reason?,by?}`。手动标签优先于规则、AI 和 Agent；AI 请求 `POST /ai-classify {message_ids:[...]}`，最多 25 封，调用共享 AI 并校验返回邮件 ID。写回绑定操作开始时的账号版本，切换期间的旧操作返回 409。

`POST /agent/token` 返回新令牌并撤销旧令牌。`GET /agent/pending` 需要专用 Bearer 令牌；该令牌只允许读取待分类邮件及写入本模块 `/labels`，写入时无需框架 CSRF，并强制记为 agent。令牌按账号版本保存在模块 secrets，分类与正文保存在模块 Store。切换账号后旧缓存与令牌不可见。网页普通写请求使用框架令牌。

`stop(context)` 取消原生复核及同步。运行完整项目检查，或模块 `checks/check_mail.py`、`checks/check_intelligence.py`，覆盖正文安全、段落、规则与语义结果、缓存、手动优先、版本失效及账号隔离；均使用合成邮件。
