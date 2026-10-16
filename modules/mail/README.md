# 校园邮箱

使用共享 `coremail` 认证与 sid，读取收件箱最近 100 封；正文按需读取且设置 `markRead=false`。`GET /snapshot`、`POST /sync` 为同步接口；`GET /message?message_id=mail:原标识` 返回清理后的正文与附件元数据。正文保留表格和段落，移除脚本、表单、事件与远端图片。原邮箱用于附件查看。

`GET/PUT /rules` 读取或保存 `{rules:[{id,field,contains,label,enabled}]}`，最多 100 条；field 为 title、sender 或 body_text。`POST /classify` 执行首条命中的规则。`GET/POST /labels` 读取或保存分类；保存请求为 `{message_id,label,reason?,by?}`。手动标签优先于规则、AI 和 Agent；AI 请求 `POST /ai-classify {message_ids:[...]}`，最多 25 封，调用共享 AI 并校验返回邮件 ID。

`POST /agent/token` 返回新令牌并撤销旧令牌。`GET /agent/pending` 需要专用 Bearer 令牌；该令牌只允许读取待分类邮件及写入本模块 `/labels`，写入时无需框架 CSRF，并强制记为 agent。令牌按账号版本保存在模块 secrets，分类与正文保存在模块 Store。切换账号后旧缓存与令牌不可见。网页普通写请求使用框架令牌。

`stop(context)` 停止同步。运行项目 `check.sh` 或模块 `checks/check_mail.py`，覆盖正文安全、异常记录、缓存、分类优先级、AI 输出验证及 Agent 权限；均使用合成邮件。
