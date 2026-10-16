# 时间表

分类与模块 ID 为 `timetable`，页面路由为 `#timetable`。页面汇总教务上课安排、Blackboard／Gradescope 带截止时间的 quiz 与作业、教务系统考试。每周课程按教学周和节次展示；有日期的事项按时间排序，可切换即将到来／全部／已过去，以及作业／考试类型。页面显示来源与缓存更新时间，已提交事项保留提交状态。

## 接口

前缀为 `/api/v1/modules/timetable`。

| 接口 | 用途 |
| --- | --- |
| `GET /snapshot` | 教务课程与 `timetable` 活动，供课程中心等调用 |
| `POST /sync` | 使用共享 IDS 的 `timetable` 目标同步上课安排，返回 202 |
| `GET /schedule` | 读取上课安排与 Blackboard、Gradescope、eams 的当前账号快照，返回汇总时间表 |
| `POST /schedule/sync` | 启动上述四个来源同步，返回 202 和各来源结果 |

`/schedule` 返回 `{status,updated_at,data,sources}`。`data` 保留上课快照的八个集合、`metadata`，增加 `events`、`undated`，并在 `issues` 汇总来源提示。`events` 保留来源事项字段，增加规范时区时间 `at`、`event_type: "deadline" | "exam"` 与 `course_title`，按时间和 ID 排序。考试的 `at` 为开始时间，作业与 quiz 为截止时间；日期已公布但时刻待定的考试明确显示“具体时间待公布”。`undated` 统计缺少有效日期的事项，页面引导到作业管理或教务系统查看。`sources` 记录各可用来源的状态和缓存更新时间。

汇总读取只访问公开快照，不触发学校网络请求或持久化副本。来源停用或不可用时提示原因，其余来源仍显示；请求期间账号切换返回 409。每周课程按原站周次展示；课程未提供日历日期时保持教学周与节次，不推测开学日期。原始上课活动包含星期 1–7、起止节次、教学周数组、教师、教室和课程 ID。学期、每天节数与周次范围从原站读取，跨年周次遵循 EAMS 活动位串规则。

同步经过共享认证与有界重试，解析缺少学期、课程映射或节次时保留缓存并显示错误。`stop(context)` 取消后续请求并等待同步退出，前端卸载取消轮询并移除样式。运行 `bash ./check.sh`，或在项目 uv 环境运行 `python modules/timetable/checks/check_timetable.py`；合成检查覆盖上课解析、跨时区事项排序、来源停用与读取期间切换账号。
