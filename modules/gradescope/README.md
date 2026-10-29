# Gradescope

作业输出兼容的 `submitted` 三态，以及 `submission_status`、`submission_evidence`、`submission_reason`、`checked_at` 和 `exempt`。状态区分未提交、草稿、已提交、已评分、豁免和待核实。只有数值成绩才作为评分依据，0 分有效，空的成绩标签或破折号不能证明提交；明确的 No Submission 优先于分数占位。豁免不列入待办。详情的开放能力仍独立处理，不用截止时间推断提交状态。作业同时保留 `due_at`（按时提交的截止时间）与 `late_due_at`（迟交截止时间）：时间图出现两个截止点时，`due_at` 取较早者，只有存在更晚的迟交窗口时才填写 `late_due_at`。

使用共享 `gradescope` 认证。`GET /snapshot` 返回所有可见课程、作业与题目资料；`POST /sync` 启动后台同步。作业提交状态为 true、false 或 null；开放能力优先采用详情的 `submission_allowed`，列表按钮提供已开放证据。没有入口的预告保留稳定本地标识，原始 `source_id` 为 null。课程详情失败单独提示并保留缓存，其余课程继续读取。

`GET /assignment?course_id=101&assignment_id=202` 实时读取作业状态、在线题干和题目元数据。`GET /file` 使用相同参数，重新解析当前题目下载地址。签名文件地址留在服务端，只允许 Gradescope 及已确认的上传服务，文件传输后清理项目内暂存。

模块负责自身 Store 与生命周期，账号和会话通过共享认证。运行项目 `check.sh` 或 `checks/check_gradescope.py`，验证学期、预告作业、未知状态、详情能力与稳定下载接口。
