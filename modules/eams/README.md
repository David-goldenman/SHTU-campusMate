# 教务系统

分类为教务系统（侧栏位于作业管理与通知之间），使用共享 IDS 的 `timetable` 目标读取上海科技大学教务系统。页面按 n 行 1 列排列四个板块：考试安排、GPA、培养方案和教务问答。

## 读取范围

| 板块 | 教务地址 | 说明 |
| --- | --- | --- |
| 考试安排 | `/eams/stdExamTable!innerIndex.action`、`/eams/stdExamTable!examTable.action` | 学生、当前学期与考试批次取自考试页，实际考试表为 `#contentDiv` 载入的网格 |
| GPA | `/eams/teach/grade/course/person!historyCourseGrade.action?projectType=MAJOR` | 第 1 个 `table.gridtable` 为学期汇总，第 2 个为课程成绩明细 |
| 培养方案 | `/eams/myPlan.action` | `#PrintA` 标签页中的 `table.planTable`，含分类、课程代码、名称、学分、建议修读学期、是否必修、开课院系与备注 |
| 学期目录 | `/eams/dataQuery.action`（`semesterCalendar`） | 所有学期 id 与学年，用于学期切换 |

考试页、成绩页和培养方案页逐页读取，页面之间等待 1.2 秒。教务返回「请不要过快点击」等访问过快提示时等待 4 秒重试，最多 3 次；重试仍失败则保留上次数据并报告错误，提示文字不会进入页面数据。整轮同步固定 4 次请求。

## 快照

`GET /snapshot` 为共享校园快照，`POST /sync` 启动同步（202）。`data` 使用校园数据契约：

- `courses`：成绩明细，`id` 为 `eams:grade:<课程序号>`，附带 `credits`、`score`、`point`、`category`、`published_at`、`kind:"grade"`。
- `assignments`：考试安排，附带 `kind:"exam"`、`exam_kind`、`date`、`start_time`、`window`、`location`、`status`、`note`、`due_at`（Asia/Shanghai）与指向成绩课程的 `course_id`；考试不会进入待办筛选。
- `metadata`：`semester`、`semester_id`、`student_id`、`semesters`、`exams{batch,batch_id,batches}`、`gpa{overall,weighted_credits,earned_credits,semesters}`、`study_plan{title,groups[path,courses]}`。
- `issues`：某个板块读取失败时保留该板块上次数据并写入提示，其余板块照常更新；整轮失败时框架保留上次成功快照。

总绩点按明细中学分与绩点加权计算，未给出绩点的课程不计入；累计获得学分按学期汇总相加。

## 接口

前缀为 `/api/v1/modules/eams`。

| 接口 | 请求/用途 |
| --- | --- |
| `GET /snapshot` | 快照，含三个板块 |
| `POST /sync` | 重新同步，返回 202 |
| `GET /exams?semester_id=&batch_id=` | 读取指定学期（可选批次）的考试安排；当前学期返回快照缓存，其他学期实时读取 |
| `POST /ask` | `{question}`，把考试、成绩与培养方案摘要交给共享 AI 服务，返回 `{answer, model, usage}` |

`/ask` 只发送上述摘要（约 10 KB，上限 20000 字符），不发送 Cookie、会话或页面原始 HTML；未启用统一 AI 服务时返回 409。

## 页面

考试板块可用学期下拉切换往年考试，批次多于一个时另给批次下拉，结果在本次页面内缓存，没有考试时显示「当学期没有安排考试时间，请等待」。GPA 板块显示总绩点、各学期汇总与可展开的成绩明细。培养方案板块默认折叠。教务问答为单轮基本问答。

## 检查

```sh
uv run python modules/eams/checks/check_eams.py   # 合成页面，含访问过快重试、板块降级与接口
node --check modules/eams/web/index.js
```

检查使用合成 HTML 夹具与 `httpx.MockTransport`，不读取账号、不访问真实教务，也不产生 AI 费用。
