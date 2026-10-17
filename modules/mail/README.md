# 校园邮箱

使用共享 `coremail` 认证与 sid，读取收件箱最近 100 封；正文按需读取且设置 `markRead=false`。`GET /snapshot`、`POST /sync` 为同步接口；`GET /message?message_id=mail:原标识` 返回清理后的正文与附件元数据。正文保留表格和段落，移除脚本、表单、事件与远端图片。原邮箱用于附件查看。

页面采用邮件列表与正文分栏，支持全文摘要筛选和主题／发件人搜索。纯文本换行转为段落和换行标记；清理后的 HTML 保留标题、列表、表格、粗体、居中和原文链接，使用本机 Nord 排版。正文按账号缓存，阅读不修改原站已读状态。

## 偏好与语义复核

`GET/PUT /preferences` 管理按邮箱账号保存的学段、年级、专业、在修课程、形策／心理健康完成状态、兴趣及完整自然语言要求；GET 返回 `{preferences,buckets,interests}`，PUT 接收完整 preferences。兴趣模式为 `follow/digest/hide`；完成状态为 `unknown/required/done/na`。初始资料留待用户填写，兴趣类别独立保存。`GET /intelligence` 返回 `{messages:[{...message,classification}],preferences,buckets,interests}`。

四种显示位置为 `focus/recommend/digest/filter`。规则先给出保守初筛，`POST /review {message_id,force?:boolean}` 通过本模块原生 Harness 插件逐封语义复核，返回分类、摘要、理由、原文依据及可选活动。页面“复核最近邮件”每次最多五封。AI 读取完整偏好和所选正文，不执行邮件中的指令；IC 等缩写按完整词匹配，普通政治讲座与形策认定分别判断。证据须来自实际发送的标题或正文，不确定事项保留核对提示。缓存指纹包含账号、原文、偏好、模型与提示词；资料变化后重新复核。

`GET /review-context?message_id=` 为后台助手提供本次分类输入、schema、指纹及原文；按需读取正文。`POST /review-results {message_id,fingerprint,decision}` 校验 schema、资料版本和原文再保存；`POST /tools/review {decision}` 只供本模块当前 Harness 任务使用，短期令牌绑定邮件、指纹与账号。分类正文至多 14000 字符，联系方式替换后发送到共享 DeepSeek 服务。

形策保护只接受正文明确肯定的“计入／纳入形策”等认定，并结合用户仍需完成的设置。否定、待定、互相矛盾的认定，或标题／正文仅出现“形策考勤”，均不强制改为重点。后台安排使用当前 `/review-context` 的初筛结果重新判断，不能仅信任旧分类的保护标记。语义提示词随认定规则更新，使旧提示词生成的缓存失效。

手动分类可带 `bucket`；显示位置与标签优先于规则和 AI。筛选只改变本工作台显示，原邮件保留。偏好和复核结果在本模块 Store 按账号版本保存，正文和旧标签沿用已有账号保护。校园后台助手使用这些公开 API 将重要事项送入通知中心，活动参加确认与时间校验见 [后台助手](../campus-agent/README.md)。

## 兼容接口与清理

`GET/PUT /rules` 读取或保存 `{rules:[{id,field,contains,label,enabled}]}`，最多 100 条；field 为 title、sender 或 body_text。同步后自动按首条命中规则分类，`POST /classify` 可手动重新执行。`GET/POST /labels` 读取或保存分类；保存请求为 `{message_id,label,reason?,by?}`。手动标签优先于规则、AI 和 Agent；AI 请求 `POST /ai-classify {message_ids:[...]}`，最多 25 封，调用共享 AI 并校验返回邮件 ID。写回绑定操作开始时的账号版本，切换期间的旧操作返回 409。

`POST /agent/token` 返回新令牌并撤销旧令牌。`GET /agent/pending` 需要专用 Bearer 令牌；该令牌只允许读取待分类邮件及写入本模块 `/labels`，写入时无需框架 CSRF，并强制记为 agent。令牌按账号版本保存在模块 secrets，分类与正文保存在模块 Store。切换账号后旧缓存与令牌不可见。网页普通写请求使用框架令牌。

`stop(context)` 取消原生复核及同步。运行完整项目检查，或模块 `checks/check_mail.py`、`checks/check_intelligence.py`，覆盖正文安全、段落、规则与语义结果、缓存、手动优先、版本失效及账号隔离；均使用合成邮件。
