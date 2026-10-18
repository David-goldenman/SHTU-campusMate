# 时间表

课程课表与手机日程按课程中心 `GET /appearance` 提供的开课院系配色，图例与课程详情保留院系文字；体育课显示 Font Awesome 跑步图标，书院与体育均为红色。课程中心停用时保留可用课表和原有中性色，时间表不自行推断院系。配色只作用于课程，截止事项、考试和活动保留各自类型标记。

`GET /schedule` 额外返回 `network_failures` 数组，转发来源的网络故障标记；页面在课表上方自动显示检测结果、处理建议和重试同步按钮。恢复后清除旧故障，不影响已缓存课程或本地安排。

`timetable` 页面采用每周七天课程表，纵轴为教务节次，课程跨越其实际节数；同一节次的重叠课程并列显示。钟点可用时显示在节次旁，旧缓存只有节次时仍立即正确排列，不编造钟点，也不把课程放进“其他”。定时安排、截止事项、全天与时间待定事项在独立周表分行显示，各行按实际时间排序。移动端显示逐日安排，课程按节次排列，其他事项按类型和时间排列。页面标注今天与明天，课程卡片展示节次、可用钟点和地点；点击查看详情。时间表整合教务课程、Blackboard／Gradescope 的作业与 Quiz 截止、教务考试，以及用户添加的 Quiz、展示、活动和讲座。页面在周表上方按上周、本周、下周、下下周列出未确认已提交且来源仍开放（含已迟交）的 Blackboard／Gradescope 作业；其他已提交、已批改、已关闭、开放状态未知或属于本学期之前的项目不进入该提醒区。来源中的 Quiz 时间仍按其截止时刻解释；用户可为实际开始时刻另建安排。

前缀为 `/api/v1/modules/timetable`。

课程网格的动态节次、跨节长度和重叠列通过 CSSOM 属性设置，遵循框架 `style-src 'self'` 的内容安全策略；HTML 模板不使用会被该策略阻止的内联 `style` 属性。

已取消课程默认从电脑周课表和手机逐日安排中隐藏，不占课表格子。本周存在取消记录时，工具栏提供“显示已取消课程”开关；打开后可查看状态，并点击课程选择“恢复教务原安排”。该开关与安排类型筛选同时生效，每次进入页面默认关闭。取消记录仍保留在 `/schedule` 日历数据中，重新同步不会清除，恢复、版本检查和冲突检查沿用原有接口。

| 接口 | 用途 |
| --- | --- |
| `GET /snapshot`、`POST /sync` | 原始课程与上课活动；同步返回 202 |
| `GET /schedule?week_start=YYYY-MM-DD` | 全部有日期的事项、指定周的日历与近四周待交作业，默认北京时间本周 |
| `POST /schedule/sync` | 启动课表、Blackboard、Gradescope 与教务同步 |
| `GET /calendar-settings` | 当前学期采用的日期、来源、学校链接与检查时间 |
| `PUT /calendar-settings` | `{week_one:"YYYY-MM-DD"}`，保存本学期第 1 教学周的周一 |
| `DELETE /calendar-settings` | 用户主动恢复学校校历日期 |
| `POST /calendar/refresh` | 重新读取学校公开校历，保留手动日期 |
| `GET /calendar/image?page=N` | 返回缓存的校历 PDF 第 N 页 PNG（1–4） |
| `GET /events`、`POST /events` | 查询与创建个人安排，创建返回 201 |
| `PUT /events/{id}`、`DELETE /events/{id}` | 修改与删除自己添加的安排 |
| `GET /capabilities` | 本地支持的安排类型、动作、范围及冲突检查说明 |
| `POST /commands` | 带账号版本、幂等操作 ID 和预期记录版本的新增、修改、删除与课程调整 |
| `GET /changes` | 当前学校账号最近 50 条成功操作回执 |

`/schedule` 返回 `{status,updated_at,data,sources,calendar,school_calendar,homework}`。`school_calendar` 为 `{available,pages,url,pdf_url,checked_at,error,version,due}`：`available` 表示已有可显示的页面图片，`version` 用于前端缓存键，`due` 提示页面自动或手动更新校历。`homework` 固定以北京时间当前教学周为基准，覆盖上周、本周、下周与下下周：`{week_start,start,end,items,pending,late}`，每项含 `id/title/url/source/course_title/due_at/category/week_start/offset/late`；只收录这两个来源中未确认已提交、来源开放且截止时间落在窗口内的作业，`offset=-1..2` 对应四周。窗口不随查询的 `week_start` 改变，便于始终看到近四周待办。`data` 保留原始集合，增加按时间排序的 `events` 与来源提示。`events` 包含 `event_type`、带时区的 `at`、可选 `ends_at`、名称、来源、课程名和地点。`event_type` 为 `deadline/exam/quiz/presentation/activity/lecture/calendar`。`calendar` 包含 `week_start/week_end/week_one/week_one_source/teaching_week/periods/days`；`periods` 为完整节次轴 `{period,start,end}`，缺失的钟点为 `null`。每个 day 为 `{date,events}`，先列按起止节次排序的课程（`event_type:class`），再列按实际时刻排序的日程。课程钟点来自教务课表的节次表，缺失时保留节次，不假设钟点。旧缓存兼容在读取日历时完成，不改写快照、账号、教学周或个人安排；下次同步按来源补充钟点。解析部分缺失的节次钟点时不移动后续节号。考试仅公布日期时明确标注时间待公布。

个人安排类型支持 `quiz/exam/tutorial/study/presentation/activity/lecture`。时间可选带时区的 `starts_at/ends_at?`，或 `date/period_start/period_end`；起止节次为 1–30，结束不得早于开始，不混用两种模式。可选 `course_title/location/notes`。安排按 IDS 账号版本隔离。教务课程原始快照由来源维护，本地覆盖记录用于请假、停课、调课与恢复，重新同步不会改写这些记录。

`POST /commands` 请求为 `{action,account_revision,request_id,record_id?,expected_revision?,event?,adjustment?}`。`action` 为 `create/update/delete/adjust_class`，`request_id` 为 UUID，账号版本来自 `/schedule`。修改或删除使用读取记录的 `revision`；缺失、过时或切换账号返回 409。相同请求 ID 的相同请求返回原回执，不重复执行，复用 ID 改参数返回 409。`event` 是新增的完整字段或修改的部分字段；换用钟点或节次时清除另一模式。旧 `/events` 接口保留兼容，页面和主页 AI 使用版本检查的命令接口。

## 近四周网格

页面顶部提供可展开的近四周作业日程，位于上一周、本周、下一周按钮上方；它是 5 行 × 8 列的网格（1 行表头 + 4 个教学周，1 列周次 + 7 个星期），覆盖上周、本周、下周和下下周。每个单元格列出该日的作业截止和待完成／迟交作业，显示 Blackboard 或 Gradescope 提交平台，迟交项目带醒目标记。表格独立于课程周表，切换周按钮或筛选不会改变它，“今天”高亮随日期推移更新。下方本周课程与日程默认展开，包含冲突检查；移动端按日浏览。课程格子每节高 76px，课名最多两行，单节课一行，时间与地点各一行；点击查看完整名称、院系、地点和课程调整，卡片内部不滚动。

课程 `adjustment` 为 `{lesson_id,on_date,action,scope?,until_date?,to_date?,starts_at?,ends_at?,period_start?,period_end?,location?,notes?}`。动作 `leave/cancel/move/restore`，范围 `once`（默认）或 `following`（从这一次起、截至可选日期的同一排课系列，不自动扩展到课程的其他排课系列）。只调地点也用 `move`。调整按学校账号与学期保存，同一原始上课日期以最新适用规则为准；`restore` 恢复原教务安排。跨周调课在原位置标注“已调课”，目标周显示新安排；只改地点不生成重复卡片。缺失来源课程 ID 时保留覆盖并提示。

回执含 `{applied,before,after,affected_count,week_start,checked_weeks,conflicts,local_only}`。冲突检查比较节次或已知钟点区间，排除已请假、已取消及调课前位置；连续调整检查各目标周，并纳入当前可用的来源考试、校历及个人安排。来源缺失、仅有节次或缺少结束时间时 `conflicts.complete=false`，不能据此声称无冲突。日历也返回 `conflicts`，页面展示时间重叠；课程覆盖仅影响本地时间表，不办理学校端请假审批或正式调课。

`POST /events/import` 接收个人安排字段及 `{origin_id,account_revision}`，供已确认的跨模块安排导入。账号版本为共享 `account_revision(context)`；不一致返回 409。相同账号与 origin_id 使用稳定安排 ID，已存在则返回 `{...event,existing:true}`，保留用户修改。后台建议的接受／拒绝状态由来源模块保存，防止用户删除后被重复添加。前端继续通过普通个人安排接口编辑或删除导入项。

学校统一入口为 [官网校历栏目](https://www.shanghaitech.edu.cn/1024/list.htm)。按教务学年匹配文章及 PDF，优先选择栏目中最新且匹配当前学年的条目；缺少学年标题时使用列表第一项，并通过 PDF 内的学期日期确认。每周检查一次，并在开学和学期结束前后三天各复核一次；上次识别失败时下次读取会立即重试，页面“更新校历”按钮可立即检查。缓存 PDF 后使用 `pypdfium2` 逐页生成 PNG，显示在“本周详情 · 节次与冲突”下方的可折叠校历面板中；点击图片在弹窗放大，点击弹窗外关闭。文本 PDF 直接提取；图片 PDF 使用 Windows 内置 PDF 与中文 OCR，Windows 原生和 WSL 入口共用该路径。识别只接受有效周一起点，同一 PDF 中个别 OCR 噪声日期不影响其他学期；同时解析明确的校运动会停课说明。法定假期和额外调课以学校后续通知为准。停课日显示校历事项并跳过上课活动。图片识别缺少系统语言组件或识别失败时，保留缓存并提示手动填写。

自动校历按学年保存，手动起点按学校账号与学期保存。同一学期的自动刷新不会覆盖手动值；进入新学期会自动使用匹配的新校历，旧学期的手动设置继续保留。页面提供“恢复学校日期”，用户可显式取消当前学期的手动覆盖。学校学期名称、原始教学周和实际日历保持独立，解析错误不影响其他来源同步。日期只采用手动设置或已识别的学校校历，`week_one_source`（设置接口的 `source`）为 `manual`、`school` 或 `null`。校历读取失败时保留这些已知日期；没有确定日期时不猜测学期起点、不展开课程，并提示设置日期，已有个人安排和截止事项继续显示。有课程尚未展开时，日历和编辑回执的 `conflicts.complete=false`，不能据此声称无课或没有冲突。

所有聚合通过公开 API；来源停用时提示原因，其余来源仍显示。读取期间切换账号返回 409。`stop` 取消后续请求并等待后台结束，页面卸载取消请求、轮询和样式。运行 `python modules/timetable/checks/check_timetable.py`（含合成 PDF 渲染与图片接口），界面验证使用 `node checks/check_web.mjs`，所有夹具为合成资料。


观星台／星夜手记主题的页面末尾可显示蓝白校园图片轮播，在设置 → 外观中独立开关。图片不附场景说明，默认 20 秒切换；可暂停、手动切换，并在离屏或减动态时停表。装饰使用共享 campus-moments 组件并随模块清理，不参与数据同步、课程布局或日程计算。
