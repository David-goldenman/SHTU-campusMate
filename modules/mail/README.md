# 校园邮箱

邮箱以分类文件夹和紧凑单行列表作为默认视图，打开邮件后主区域用于正文阅读；返回后聚焦对应邮件行，加载或失败时也可返回。阅读组织参考 [Thunderbird 邮件前端](https://github.com/thunderbird/developer-docs/blob/master/thunderbird-development/codebase-overview/mail-front-end.md)，使用项目 Nord 样式。左侧包含重点关注、兴趣推荐、一般通知、已筛选、收件箱、未读及日／周总结。分类为本地智能文件夹，原邮件保留在学校邮箱；页面和单封邮件均提供官方网页入口。正文保留段落、列表、表格、对齐、强调和适当字号，过滤脚本、追踪图片及任意样式。已有正文缓存继续用于离线阅读。

## 后台自动同步

本地服务运行且邮箱模块启用时，IMAP 自动同步默认开启，与网页是否打开无关。启动后立即检查，此后每 60 秒通过只读 `UID SEARCH ALL` 和最近 100 封的 `UID FLAGS` 比较邮件及已读状态；数量相同但 UID 改变也会触发同步。无变化不重新下载标题或正文、不调用 AI。发现变化后复用原同步队列，最多保存最近 100 封；手动与后台请求合并，分类、通知继续遵循已有偏好。

iOS 等不支持模型工具的运行环境在新快照成功发布后启动已有的语义分类；支持原生工具的环境继续由后台助手队列复核。`checks/check_tools_free_sync.py` 用合成数据验证首次同步和完成回调，不调用真实模型。

网络断开、超时或服务端临时错误保留密码和缓存，按 1、2、4、5 分钟（此后固定 5 分钟）重试。只有明确的认证拒绝才暂停并提示检查登录；更新凭据或成功检查连接后恢复。连接使用加密保存的专用密码；模块不持久保存连接和明文密码。电脑休眠、关机或服务停止期间不检查，恢复后补查。

- `GET /auto-sync`：返回 `enabled/configured/mode/interval_seconds/state/message/last_checked_at/last_synced_at/next_check_at/owner/session_revision/uid_validity/revision`。时间为 ISO 8601；固定间隔 60 秒，`mode=polling`。`state` 为 `starting/watching/syncing/retrying/login_required/paused/not_configured`。`revision` 仅在账号、设置、数据或连接状态改变时变化，无变化的检查时间更新不会触发页面重画。
- `PUT /auto-sync {enabled,owner?}`：按账号版本保存开关，默认开启；携带 `owner` 时若账号已切换返回 409。暂停会关闭后台检查和纯自动同步的活动连接，仍允许手动同步；已合并的手动任务继续完成。停用模块或退出服务时终止同步线程和连接。
- 邮箱页提供开关及最近检查时间。常驻 `web/background.js` 每 5 秒读取本地状态，发出 `campus:mail-status`，仅在版本变化时发出 `campus:mail-updated`。邮箱和首页通过通用 `sourcePanel(...,{refreshEvent})` 接收更新，不因每次心跳请求完整资料。读取邮件、搜索、滚动位置及未保存的分类偏好保留；切换账号或 UID 有效期改变时关闭旧邮件和旧账号编辑框。

每次连接复核账号及凭据版本，丢弃旧结果；检测到变更后关闭旧连接。暂停自动同步保留最近成功记录和诊断状态，临时检查失败也保留最近成功时间并记录诊断编号。检测到 `UIDVALIDITY` 改变时重建依赖 UID 的正文、分类和复核缓存，保留用户偏好；正文缓存标记 UID 有效期，读取和写回均校验代次；同步已确认新有效期但新快照尚未发布时，旧正文及分类写回返回 409。旧版 IMAP 缓存没有有效期时先同步确认，只重建依赖 UID 的缓存；非 IMAP 正文与用户偏好保留。旧有效期或凭据的外部 Agent 令牌失效。正文仍使用 `BODY.PEEK[]`，不修改原站已读状态。

合成检查 `checks/check_auto_sync.py`、`checks/check_auto_sync_web.py` 覆盖批量来信、同数量 UID 变化、状态变化、重试、登录拒绝、账号与凭据切换、UID 重置、暂停/清理和并发队列；共享认证错误分类由 `checks/check_imap_errors.py` 验证。

## 文件夹与日／周总结 API

IMAP 已配置但当前账号尚无同步记录时，来源状态为 `not_synced`（等待首次同步），不会提示重新登录。首页批量同步识别 IMAP 连接；同一邮箱更新专用密码继续保留当前邮件缓存和分类。专用密码由共享认证服务加密保存，不写入模块数据或返回前端。

- `GET /folders`：`folders[{id,name,count}]`、`scope:local-inbox`、`cached_count`。分类详情继续读取 `/intelligence` 中的 `messages[].classification`，手动分类优先。
- `GET /digests?period=day|week&anchor=YYYY-MM-DD`：返回北京时间的 `start/end`、按文件夹的 `counts`、`entries`、`coverage`、`fingerprint` 和已保存的 `report`；默认当天，周一至周日。每条邮件带稳定 ID、分类、已有摘要、学校网页和 `workbench_url`。GET 使用本地缓存，不调用模型。
- `POST /digests {period,anchor?}`：按用户操作生成总结。共享 `context.ai.generate(format="json")` 只接收本期邮件 ID、时间、标题、分类和已有摘要；不为总结额外下载正文。`report` 包含 `overview/highlights[{message_id,summary}]/generated_at/model`，校验引用属于本期且不重复后保存。

总结按账号版本及日期保存。分类、手动标签或邮件变更会使对应旧总结失效；账号在生成过程中变化返回 409。无邮件返回 400，无效日期或周期返回 422，模型结果无效返回 502。覆盖范围是已同步的最近最多 100 封收件箱邮件，并返回缓存数与校方总数，不能据此宣称覆盖整个历史邮箱。其他模块使用 `context.api('mail','/digests?...')` 或 `/folders` 读取，模块停用按公共契约返回不可用；引用进入时间表仍遵循现有确认流程。

日／周总结使用当前可见分类，已筛选邮件保留在数量和原始清单中。模型只接收其他分类的条目，重点摘要的引用须属于所选范围；整个日期范围都已筛选时直接显示说明。总结策略与分类版本共同参与缓存校验。

优先使用共享 `coremail` 认证中的 IMAP 专用密码连接 `imap.shanghaitech.edu.cn`（默认 SSL `993`，端口可编辑），通过 `UID SEARCH ALL` 读取收件箱最近 100 个 UID，正文使用 `BODY.PEEK[]`，不会把邮件标记为已读；未配置 IMAP 时才回退到官方网页会话与 sid。`GET /snapshot`、`POST /sync` 为同步接口；`GET /message?message_id=mail:原标识` 返回清理后的正文与附件元数据。正文保留表格和段落，移除脚本、表单、事件与远端图片。原邮箱用于附件查看。

设置页的学校邮箱卡片先提供 IMAP 登录，并带有可关闭的两页设置指引：第一页说明如何在学校邮箱“安全设置 → 客户端专用密码”生成专用密码，第二页说明复制密码并核对 `imap.shanghaitech.edu.cn`、`993` 与 SSL。保存后官方网页会话会被删除，IMAP 成为唯一邮箱连接方式；如需改用网页登录，先在卡片中删除 IMAP。所有主题与窄屏布局共用同一套表单和弹窗结构。

列表在桌面显示发件人、主题、摘要、分类和日期；窄屏顺序阅读。搜索覆盖当前文件夹的主题、发件人和摘要，输入时返回列表。分类偏好在独立表单编辑，批量复核通过“更多操作”进入；菜单支持 Esc 和点击外部关闭。纯文本换行转为段落和换行标记，清理后的 HTML 保留标题、列表、表格、粗体、居中和原文链接。正文按账号缓存，阅读不修改原站已读状态。

进入邮箱默认显示“重点关注”，其余邮件通过兴趣推荐、一般通知、已筛选和收件箱查看；文件夹显示数量，搜索限定当前文件夹。从邮件引用进入时直接显示对应原件。兴趣推荐仍可在通知中心查看，主动提醒与计数用于重点邮件；顶部铃铛提供统一通知入口。

## 偏好与语义复核

`GET/PUT /preferences` 管理按邮箱账号保存的学段、年级、专业、在修课程、形策／心理健康完成状态、兴趣及完整自然语言要求；GET 返回 `{preferences,buckets,interests}`，PUT 接收完整 preferences。兴趣模式为 `follow/digest/hide`；完成状态为 `unknown/required/done/na`。初始资料留待用户填写，兴趣类别独立保存。`GET /intelligence` 返回 `{owner,session_revision,uid_validity,messages:[{...message,classification}],preferences,buckets,interests}`，响应在聚合前后核对邮箱归属、凭据代次和 UID 有效期，任一变化返回 409。`GET /snapshot` 增加本模块专属的 `account_revision/session_revision`；页面发布前核对快照、分类结果和最新自动同步状态中的账号、凭据及 UID 有效期一致。页面以此 owner 绑定已显示内容；快照请求临时失败时，只有轻量状态再次确认同一邮箱归属、凭据和 UID 有效期才保留阅读区和未保存偏好，否则关闭并禁用旧表单、清理旧内容后重建。

本地分类每批只读取一次邮件快照、有效偏好和 AI 配置，避免对每封邮件重复读取加密存储；下次请求重新取得这些输入。单封复核和批量分类使用相同的输入版本计算，手动标签优先，账号在批量处理期间变化时返回 409。

四种显示位置为 `focus/recommend/digest/filter`。规则先给出保守初筛，`POST /review {message_id,force?:boolean}` 通过本模块原生 Harness 插件逐封语义复核，返回分类、摘要、理由、原文依据及可选活动。页面“复核最近邮件”每次最多五封。AI 读取完整偏好和所选正文，不执行邮件中的指令；IC 等缩写按完整词匹配，普通政治讲座与形策认定分别判断。证据须来自实际发送的标题或正文，不确定事项保留核对提示。缓存指纹包含账号、原文、偏好、模型与提示词；资料变化后重新复核。

`GET /review-context?message_id=` 为后台助手提供本次分类输入、schema、指纹及原文；按需读取正文。`POST /review-results {message_id,fingerprint,decision}` 校验 schema、资料版本和原文再保存；`POST /tools/review {decision}` 只供本模块当前 Harness 任务使用，短期令牌绑定邮件、指纹与账号。分类正文至多 14000 字符，联系方式替换后发送到共享模型服务。

形策保护只接受正文明确肯定的“计入／纳入形策”等认定，并结合用户仍需完成的设置。否定判断限定在考勤认定及其修正说明，“不需要提前报名”等独立说明不会否定明确认定；跨逗号的条件、疑问、待确认和更正仍需核对。否定、待定、互相矛盾的认定，或标题／正文仅出现“形策考勤”，均不强制改为重点。后台安排使用当前 `/review-context` 的初筛结果重新判断，不能仅信任旧分类的保护标记。语义提示词随认定规则更新，使旧提示词生成的缓存失效。

手动分类可带 `bucket`；显示位置与标签优先于规则和 AI。筛选只改变本工作台显示，原邮件保留。偏好和复核结果在本模块 Store 按账号版本保存，正文和旧标签沿用已有账号保护。校园后台助手使用这些公开 API 将重要事项送入通知中心，活动参加确认与时间校验见 [后台助手](../campus-agent/README.md)。

## 兼容接口与清理

`GET /preferences` 与 `/intelligence` 同时返回用户保存的 `preferences` 和结合公开学习档案、当前课程目录得到的 `effective_preferences`；自动补充的专业、年级和课程只参与分类，用户填写值优先。`PUT /preferences` 保存后立即重新初筛，并唤醒后台复核全部缓存邮件。`/intelligence` 返回 `review_status` 和每项分类的 `input_revision/review_pending`，界面按需刷新进度。新版本复核完成前使用当前规则，手动分类始终优先。

重点规则包括当前课程的作业发布、考试、实验材料、课件、讲义、预习及安排变更；课程来自课程中心 `GET /catalog/courses?current=true&limit=100` 和手动补充。学籍信息来自学习助手 `GET /profile`，入学年份按上海时区的学年计算当前年级。本科一、二年级默认关注形策，一年级关注心理活动，`done/na` 与明确的 `required` 设置优先。语义复核保留上述学习重点以及明确的兴趣筛选。活动时间交给后台核验，再由用户确认参加；邮件分类、通知和活动建议使用同一结果，调查问卷等截止不作为活动开始时间。

`GET/PUT /rules` 读取或保存 `{rules:[{id,field,contains,label,enabled}]}`，最多 100 条；field 为 title、sender 或 body_text。同步后自动按首条命中规则分类，`POST /classify` 可手动重新执行。`GET/POST /labels` 读取或保存分类；保存请求为 `{message_id,label,reason?,by?}`。手动标签优先于规则、AI 和 Agent；AI 请求 `POST /ai-classify {message_ids:[...]}`，最多 25 封，调用共享 AI 并校验返回邮件 ID。写回绑定操作开始时的账号版本，切换期间的旧操作返回 409。

`POST /agent/token` 返回新令牌并撤销旧令牌。`GET /agent/pending` 需要专用 Bearer 令牌；该令牌只允许读取待分类邮件及写入本模块 `/labels`，写入时无需框架 CSRF，并强制记为 agent。令牌按账号版本保存在模块 secrets，分类与正文保存在模块 Store。切换账号后旧缓存与令牌不可见。网页普通写请求使用框架令牌。

`stop(context)` 取消原生复核及同步。运行完整项目检查，或模块 `checks/check_mail.py`、`checks/check_intelligence.py`，覆盖正文安全、段落、规则与语义结果、缓存、手动优先、版本失效及账号隔离；均使用合成邮件。

/intelligence 的每条 classification 新增只读 event_window（可为 null），独立于 needs_check 的参加资格判断。窗口仅由当前有效复核的 event 与缓存正文核对日期、钟点和时区后生成，返回 starts_at/ends_at/expires_at/basis/source_revision；不能将截止、问卷或报名日期当活动。碎片换行的年月日会归一化；无结束时间或正文还有同日较晚时段时按北京时间当日结束，多于该日期的其他安排保持未知，不提前清理。没有调用 AI 或刷新学校来源。
