# 作业管理

提交情况由来源证据决定，新增 `submission_status` 区分未提交、草稿、已提交、待评分、已评分、豁免和待核实。`submitted` 继续表示原站是否提交，本地 `local_status=done` 不改变它。豁免、待评分和已评分不会进入待办；未知状态在作业页保留为“待核实”待办，课程中心 `pending` 筛选和时间表提醒则按更严格规则排除未知；草稿仍需正式提交，在本学期且来源开放时保留为待办。

快照为每条作业提供 `needs_review`、`source_status`、`source_updated_at` 和 `source_stale`。读取失败保留上次结果并明确显示缓存，未知和过期缓存集中出现在“待核实”；已知的缓存待办数量保留，不把网络失败解释为作业已完成。详情显示判定依据和检查时间，原站明确提供的提交时间与截止时间分别展示。

`cached`（超过刷新周期）与 `syncing` 状态也标记 `source_stale=true`、`needs_review=true`，保留已知待办，不用旧提交记录自动消除提醒。`GET /snapshot` 增加 `coverage:{status,sources}`：status 为 `ready/partial/unavailable`，sources 列出 Blackboard、Gradescope、E 云课堂的 `id/status/updated_at`。它只描述已读取平台的范围；`ready` 不保证课堂、邮件或群通知中的全部作业已收录。无可用结果时返回 unavailable，已有缓存但部分来源异常时返回 partial。页面可展开查看每个来源与更新时间。

本学期之前的课程和截止日期早于本学期起点的作业统一归入“已结束”，不再进入待办、迟交、时间表提醒或课程中心待办统计；这些历史作业若产生“提交情况未能核实”等来源提示，也不会再显示。当前学期起点优先取课程来源的学期元数据，时间表页面同时采用已设置或学校校历确认的第一教学周日期。

`summary.submission_states` 统计全部缓存的七种互斥状态，`summary.needs_review` 为全部缓存需核实的记录数；`by_source[平台]` 提供该平台自己的 `submission_states/needs_review` 及原有 `total/unsubmitted/pending`。七种状态相加等于同范围 `total`，`submitted` 仅表示提交已确认、评分情况未确认；所有正式提交为 `submitted/needs_grading/graded` 之和。`unsubmitted` 包括明确未提交和草稿，不含豁免与未知；所有统计与关键词或分页无关。

来源没有提供截止时间时，若作业仍开放且可行动，默认使用本学期第 18 教学周周日 23:59（北京时间）作为估计截止，并在记录中标记 `due_default=true`、`due_source="default"`；页面显示“待完成 · 时间待定”，不把它伪装成来源日期。有学期起点时才会生成该估计，无法确定学期起点时保持无日期。用户可在作业卡片内联设置截止时间，修改按账号版本保存在 `assignment-due:<账号>`，记录返回 `due_source="manual"`；也可恢复默认，原来源快照不被改写。`GET /snapshot` 同时返回 `due_overrides`。

有估计日期与完全无日期的作业均提供“设置时间”。估计日期不进入首页最近截止、24 小时内或逾期筛选，统一进入“时间待定”；手动设定后使用用户确认的时间。恢复默认重新采用来源日期或时间待定。读取作业前后都核对账号版本，在途换号返回 409。

依赖课程中心公开 API。`GET /snapshot` 汇总 Gradescope 与 Blackboard 作业，返回按发布时间倒序的列表、六类计数 `counts` 与按截止时间排序的 `pending`。`pending` 仅包含本学期仍可提交的项目（含迟交），供主页统计使用。`PUT /deadline` 接收 `{assignment_id,due_at,account_revision}`；`due_at` 为带时区时间或 `null`（恢复默认），账号版本不匹配返回 409，未知作业返回 404。

`summary` 为当前账号全部缓存作业统计，包含 `total`（记录总数）、`unsubmitted`（未提交总数）、`pending`（本学期待办数）和 `by_source`（各来源的同名统计）。统计不受前端搜索、课程筛选或 AI 分页影响，页面筛选后的待办集合单独计算。截止时间缺失或已过不会单独排除待办；开放状态、当前学期及提交状态仍分别判断。首页和 AI 使用同一待办集合及统计。

每条作业带 `category`：

- `pending`：未确认已提交、来源开放且尚未截止；缺少截止时间时只要来源开放也归入该类，并采用第 18 教学周周日的估计日期。
- `late`：未确认已提交、来源开放但已过截止时间，`overdue=true`。
- `graded`：已提交且已公布分数（`0` 分同样有效），页面单独突出显示得分。
- `completed`：已提交但尚无分数。
- `ended`：本学期之前的全部作业（即使来源仍显示开放或提交状态无法核实），以及来源已关闭、尚未开放或开放状态未知；只有本学期的明确提交才归入完成类，开放但提交状态尚未解析的项目仍提醒待办。

## 调整顺序

待完成、迟交、已批改、已完成和已结束及无需我提交六个分区内的卡片可拖动排序，也可聚焦卡片后按 ↑/↓ 或使用卡片右侧箭头移动。顺序通过 `PUT /order` 按账号版本保存在本机 Store 中，刷新后保持；新增作业追加到末尾，来源列表变化时服务端拒绝过期顺序并提示重新排序。

页面默认查看待完成，状态栏可切换全部、待完成、迟交、已批改、已完成和已结束，并结合 24 小时内、已逾期、时间待定、学期及关键词筛选。无来源截止时间的待办显示“待完成 · 时间待定”和默认估计日期，卡片内可直接展开日期时间输入框设置或恢复默认；手动截止时间同样可再次内联调整。紧凑作业行显示课程、题目、截止、提交状态与得分；点题目在弹窗查看题干、状态依据、文件和原站入口。`POST /sync` 通过课程中心更新已配置来源。`GET /detail?assignment_id=规范ID` 实时读取 Gradescope 详情或返回 Blackboard 已缓存题目资料；资料下载使用所属来源模块的公开地址。模块不读取其他 Store。项目 `check.sh` 验证五类状态、零分成绩、未知提交／开放状态与历史课程。

## 无需我提交（本地选择）

小组只需一人提交、队友已提交时，作业卡片选择“无需我提交”，原因可选 `team_submitted`（队友已提交）、`not_required`（老师说明无需提交）或 `other`（需填写说明），备注最多 500 字。单独的“无需我提交”分类显示原因、原站状态并提供“恢复提醒”。恢复后根据当前来源状态重新分类，不强制变成待办。

`PUT /handling` 接收 `{assignment_id,status,reason,note,expected_revision,account_revision}`；status 为 `waived` 或 `required`（恢复）。首次 expected_revision 为空串，后续使用该作业 handling.revision；成功返回 `{assignment_id,handling,account_revision}`。账号或本地版本冲突返回 409，未知作业 404，原因不完整 422。恢复仍保存版本，防止旧标签页覆盖新选择。

状态按账号版本和稳定作业 ID 保存在本模块 `assignment-handling:<账号>`；刷新、来源同步和重启不覆盖。`GET /handling` 只返回 `{items:{作业ID:handling},account_revision}`，不调用课程中心或来源，因此课程中心可安全回读而不递归。停用或移除作业模块时，调用方说明本地选择不可用并保留来源数据。

快照的原站 `submission_status/submitted/exempt` 不变；本地选择为 `handling:{status,reason,note,updated_at,revision}`。waived 项返回 `reminder_suppressed=true`、`category=waived`、`pending=false`、`overdue=false`，`source_category` 保留原分类。`summary.waived` 与各来源同名字段单列数量，七类原站状态与 unsubmitted 仍按原证据统计。`counts.waived` 是第六个分类，支持原有排序接口。

首页和学习助手使用同一 pending 集合；课程中心展示和 /context 保留本地选择，pending 筛选排除；时间表的截止事件、四周提醒和新导出的作业 ICS 排除。已导出到外部的静态 ICS 不会自动更新。通知仅在全部关联作业已可靠提交或被明确标记无需提交时自动已读，原因 `assignment_not_required` 单列；恢复后重新出现。混合其他待办、成绩反馈、手动已读/未读选择保持原语义。此操作不向学校写入，不表示本人已提交或学校豁免，也不取消用户另外创建的独立提醒。

回归：`checks/check_handling.py` 覆盖跨模块一致性、重载、来源状态不变、恢复、混合通知、账号隔离和并发旧版本；`checks/check_ui_theme.mjs` 覆盖四主题的保存、取消、恢复、原因转义及移动端。
