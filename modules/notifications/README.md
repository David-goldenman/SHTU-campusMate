# 重要通知

通知中心汇总带来源的学习待办、邮件重点、服务故障和活动建议，保留已读状态。页面提供后台助手的启停与“检查一次”，活动卡片展示时间、地点与原文依据；可选活动使用“参加并加入时间表”或“不参加”。确认后显示时间表入口，参加确认与原站报名分别处理。右下角常驻提醒由独立的 `campus-agent` 模块提供。

`POST /imports` 接收 `{account_revision,id,title,summary,source_revision,importance?,why?,citations?,proposal_id?,event_at?}`，按当前账号及稳定 ID 更新；账号不一致返回 409。每条 citation 为 `{id,title,source,url}`，importance 为 `urgent/important/normal`。相同资料保留已读，资料版本更新恢复未读；导入通知最多保留最近 300 条，原有提炼结果单独保留。

`GET /agent/status`、`PUT /agent/settings {enabled}`、`POST /agent/check` 通过公开 API 代理后台助手；缺失时保留本模块的通知显示。`POST /proposals/{id}/accept|dismiss` 代理明确参加／拒绝动作，错误状态沿用来源接口。后台普通写入使用框架保护，任务工具使用各自模块的短期令牌。

通过课程中心公开 API 和共享 AI 提炼本学期课程与校园邮件中的重要事项。`GET /snapshot` 读取通知、错误与资料范围；`POST /generate?force=false` 生成，相同资料与上海日期复用已有结果，force=true 重新分析。每条通知必须引用实际所选资料，来源 URL 由缓存提供；格式、日期或引用错误保留上次结果并返回 502。

`PUT /{notice_id}/read {read:true}` 更新已读。通知 ID 由标题与来源组成；相同来源内容保留已读，来源文字更新后恢复未读。`GET/PUT /settings {auto_generate:true}` 控制自动提炼，默认关闭。开启且共享 AI 已配置时，后台每 30 秒检查资料变化；仅变化时调用模型。模块停用会唤醒并等待后台任务结束，已发出的模型请求沿用共享服务的超时限制。

通知与错误按账号版本隔离，普通状态保存在本模块 Store。项目 `check.sh` 使用合成模型结果验证去重、已读状态、引用、失败缓存与后台清理。

资料范围经课程中心公开 `POST /context` 获取；课程中心停用或缺失返回 409 提示，模块自身仍可加载、停用与恢复，已有历史按账号隔离保留。
