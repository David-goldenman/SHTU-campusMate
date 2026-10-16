# 课程中心

界面以本学期的课程为入口，每门课程汇总已连接平台的可用内容，提供资料、作业、公告、讨论、录播、上课安排及平台成绩条目分类与原站链接。页面使用 `navigation.layout:primary`，平台来源保持 API 与同步能力。可查看其他学期、搜索课程，并用可勾选列表手动关联不同平台的同一课程。

自动关联先规范课程代码中的空格、横线与大小写，再按代码和学期合并。缺少代码时，只在相同规范名称和学期唯一对应一个已知课程代码时关联；有多个候选保留独立，交由用户手动选择。

通过 `context.api` 读取六个来源的公开快照，维护自身课程关联设置。代码与规范学期一致时自动合并；缺失代码的唯一名称匹配见上文，其他课程保持独立。`GET /snapshot` 返回聚合课程、八类内容、来源状态及读取范围。本学期依次采用教务当前学期、ELRC 学校当前学期；二者都未提供时才按上海日期估计。`POST /sync` 请求已配置账号的来源同步。

`GET /catalog/{collection}` 支持 course_id、current、pending、source、q、offset、limit，limit 最大 500。pending 只适用于作业，要求来源为 Gradescope 或 Blackboard、明确开放且明确未提交；未知状态保持独立。`GET /course?course_id=聚合ID` 返回各平台课程、资料、讨论、录播、作业和折叠课表。

`GET/PUT /groups` 读取或完整保存 `{groups:[{id,title,course_ids}]}`；每组 2–20 个已知来源课程，每门课仅属于一个手动组，空数组恢复自动关联。模块不读取其他模块数据库。项目 `check.sh` 执行来源不可用、学期关联、三态待办及手动关联检查。

`POST /context` 接收 `{course_id?:string, context_ids?:string[]}`，返回 `{items,courses,text,context,account_revision,revision}`。这是助手和通知模块使用的公开资料选择接口：默认选择本学期课程及邮件；指定课程时只取该课程资料并排除邮件；显式空 context_ids 得到空资料，未提供则按课程范围选择。每条正文最多 1800 字、最多 400 条、序列化上下文最多 85000 字符；截断计数放在 context 中。items 带 source_revision，revision 结合当前账号及所选资料版本；调用方完成异步 AI 操作后仍需核对 account_revision。未知课程返回 404，失效选择返回 422，读取过程中切换账号返回 409。来源模块缺失按 snapshot 的 issues 降级；本接口只读缓存，不触发同步或 AI。
