# 时间表

`timetable` 页面采用每周七天表格，按上午、下午、晚上、截止事项与其他事项分行，标注今天与明天。移动端显示逐日安排。课程卡片展示该次上课时间和地点；点击查看详情。时间表整合教务课程、Blackboard／Gradescope 的作业与 Quiz 截止、教务考试，以及用户添加的 Quiz、展示、活动和讲座。来源中的 Quiz 时间仍按其截止时刻解释；用户可为实际开始时刻另建安排。

前缀为 `/api/v1/modules/timetable`。

| 接口 | 用途 |
| --- | --- |
| `GET /snapshot`、`POST /sync` | 原始课程与上课活动；同步返回 202 |
| `GET /schedule?week_start=YYYY-MM-DD` | 全部有日期的事项与指定周的日历，默认北京时间本周 |
| `POST /schedule/sync` | 启动课表、Blackboard、Gradescope 与教务同步 |
| `GET /calendar-settings` | 当前学期采用的日期、来源、学校链接与检查时间 |
| `PUT /calendar-settings` | `{week_one:"YYYY-MM-DD"}`，保存本学期第 1 教学周的周一 |
| `DELETE /calendar-settings` | 用户主动恢复学校校历日期 |
| `POST /calendar/refresh` | 重新读取学校公开校历，保留手动日期 |
| `GET /events`、`POST /events` | 查询与创建个人安排，创建返回 201 |
| `PUT /events/{id}`、`DELETE /events/{id}` | 修改与删除自己添加的安排 |

`/schedule` 返回 `{status,updated_at,data,sources,calendar}`。`data` 保留原始集合，增加按时间排序的 `events`、无有效日期的事项计数 `undated` 与来源提示。`events` 包含 `event_type`、带时区的 `at`、可选 `ends_at`、名称、来源、课程名和地点。`event_type` 为 `deadline/exam/quiz/presentation/activity/lecture/calendar`。`calendar` 包含 `week_start/week_end/week_one/teaching_week/days`；每个 day 为 `{date,events}`，其中已按教学周展开的课程使用 `event_type:class`。课程钟点来自教务课表的节次表，缺失时保留节次，不假设钟点。考试仅公布日期时明确标注时间待公布。

个人安排请求为 `{title,event_type,starts_at,ends_at?,course_title?,location?,notes?}`，时间必须含时区，结束晚于开始；类型限 `quiz/presentation/activity/lecture`。安排按 IDS 账号版本隔离。课程与来源事项通过对应模块维护；本模块只编辑个人安排。

学校统一入口为 [官网校历栏目](https://www.shanghaitech.edu.cn/1024/list.htm)。按教务学年匹配文章及 PDF，每周检查一次，手动刷新可立即检查。文本 PDF 直接提取；图片 PDF 使用 Windows 内置 PDF 与中文 OCR，Windows 原生和 WSL 入口共用该路径。识别只接受有效周一起点，并解析明确的校运动会停课说明；法定假期和额外调课以学校后续通知为准。停课日显示校历事项并跳过上课活动。图片识别缺少系统语言组件或识别失败时，保留缓存并提示手动填写。

自动校历按学年保存，手动起点按学校账号与学期保存。同一学期的自动刷新不会覆盖手动值；进入新学期会自动使用匹配的新校历，旧学期的手动设置继续保留。页面提供“恢复学校日期”，用户可显式取消当前学期的手动覆盖。学校学期名称、原始教学周和实际日历保持独立，解析错误不影响其他来源同步。

所有聚合通过公开 API；来源停用时提示原因，其余来源仍显示。读取期间切换账号返回 409。`stop` 取消后续请求并等待后台结束，页面卸载取消请求、轮询和样式。运行 `python modules/timetable/checks/check_timetable.py`，界面验证使用 `node checks/check_web.mjs`，所有夹具为合成资料。
