# 教务系统

分类为教务系统（侧栏位于作业管理与通知之间），使用共享 IDS 的 `timetable` 目标读取上海科技大学教务系统。页面按 n 行 1 列排列四个板块：考试安排、GPA、培养方案和教务问答。

## 读取范围

| 板块 | 教务地址 | 说明 |
| --- | --- | --- |
| 考试安排 | `/eams/stdExamTable!innerIndex.action`、`/eams/stdExamTable!examTable.action` | 学生、当前学期与考试批次取自考试页，实际考试表为 `#contentDiv` 载入的网格 |
| GPA | `/eams/teach/grade/course/person!historyCourseGrade.action?projectType=MAJOR` | 第 1 个 `table.gridtable` 为学期汇总，第 2 个为课程成绩明细 |
| 培养方案 | `/eams/myPlan.action` | `#PrintA` 标签页中的 `table.planTable`，含分类、课程代码、名称、学分、建议修读学期、是否必修、开课院系与备注 |
| 学期目录 | `/eams/dataQuery.action`（`semesterCalendar`） | 所有学期 id 与学年，用于学期切换 |
| 课程目录与大纲 | `/eams/courseSearchOther.action`、`/eams/courseSearchOther!search.action`、`/eams/courseSearchOther!info.action` | 先读取查询表单，再按课程名／代码查询；大纲使用查询结果的 `syllabus_id` |

考试页、成绩页和培养方案页逐页读取，页面之间等待 1.2 秒。教务返回「请不要过快点击」等访问过快提示时等待 4 秒重试，最多 3 次；重试仍失败则保留上次数据并报告错误，提示文字不会进入页面数据。整轮快照同步固定 4 次请求；课程目录与大纲在明确查询时另行读取。

## 快照

`GET /snapshot` 为共享校园快照，`POST /sync` 启动同步（202）。`data` 使用校园数据契约：

- `courses`：成绩明细，`id` 为 `eams:grade:<规范学期>:<课程序号>`（如 `eams:grade:2025-fall:GEMA1001.01`），同一课程序号跨学年、跨学期分别保留。附带 `credits`、`score`、`point`、`category`、`published_at`、`kind:"grade"`。
- `assignments`：考试安排，附带 `kind:"exam"`、`exam_kind`、`date`、`start_time`、`window`、`location`、`status`、`note`、`due_at`（Asia/Shanghai）与指向成绩课程的 `course_id`；考试不会进入待办筛选。
- `metadata`：`semester`、`semester_id`、`student_id`、`semesters`、`exams{batch,batch_id,batches}`、`gpa{overall,weighted_credits,earned_credits,semesters}`、`study_plan{title,groups[path,courses],requirements,notes}`。`requirements` 保留应修学分、小计与全程总计的学校原文，`notes` 保留备注；方案标题中的年份是方案版本。
- `issues`：某个板块读取失败（含 HTTP 403/404）时保留该板块上次数据并写入提示，其余板块照常更新；登录失效继续交给共享登录恢复，整轮失败时框架保留上次成功快照。

总绩点按明细中学分与绩点加权计算，未给出绩点的课程不计入；累计获得学分按学期汇总相加。

## 接口

前缀为 `/api/v1/modules/eams`。

| 接口 | 请求/用途 |
| --- | --- |
| `GET /snapshot` | 快照，含三个板块 |
| `POST /sync` | 重新同步，返回 202 |
| `GET /exams?semester_id=&batch_id=` | 读取指定学期（可选批次）的考试安排；当前学期返回快照缓存，其他学期实时读取 |
| `POST /ask` | `{question}`，把考试、成绩与培养方案摘要交给共享 AI 服务，返回 `{answer, model, usage}` |
| `GET /course-search?q=&page=1` | `q` 为 1–160 字符的课程名或代码，`page` 为 1–100；返回 `{items,page,page_size,total,scope:"course_catalog",notice}` |
| `GET /course-info?syllabus_id=` | 正整数大纲 ID；返回 `{id,title,text,url,scope:"course_syllabus",truncated}`，正文最多 24000 字符 |

`/ask` 只发送上述摘要（约 10 KB，上限 20000 字符），不发送 Cookie、会话或页面原始 HTML；未启用统一 AI 服务时返回 409。

`/exams` 与 `/ask` 在读取快照、使用认证客户端或调用 AI，以及返回结果时检查账号版本。处理中账号变化返回 409，丢弃原账号结果；排队中的 AI 请求在执行前再次检查，避免发送已过期的账号资料。考试 `course_id` 与成绩使用相同的规范学期和课程序号。

课程目录查询和大纲查询同样核对 IDS 账号版本，复用共享登录恢复。目录每页请求 20 项，记录含课程代码／名称、学分、学时、院系、教师、大纲 ID 与来源链接；隐藏表单参数只供后端使用。目录与大纲不代表未来某学期已确定开课，选课建议需结合培养方案、历史修读记录及学校选课安排。该 API 供首页学习助手等模块调用，本身不调用 AI。

## 页面

考试板块可用学期下拉切换往年考试，批次多于一个时另给批次下拉，结果在本次页面内缓存，没有考试时显示「当学期没有安排考试时间，请等待」。GPA 板块显示总绩点、各学期汇总与可展开的成绩明细。培养方案板块默认折叠。教务问答为单轮基本问答。

## 检查

```sh
uv run python modules/eams/checks/check_eams.py   # 合成页面、跨学期成绩、板块降级及账号切换隔离
node --check modules/eams/web/index.js
```

检查使用合成 HTML 夹具与 `httpx.MockTransport`，不读取账号、不访问真实教务，也不产生 AI 费用。
