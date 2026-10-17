# Blackboard

使用共享 IDS 的 `blackboard` 目标。`GET /snapshot`、`POST /sync` 提供未完成课程、内容树、资料、作业、成绩与公告。课程代码、学期和完成状态来自课程门户；资料保留目录层级。内容树限制 32 层、10000 节点，并检测重复与循环；REST 分页采用公共限制。

课程标题中的 `2026 秋`、`2026秋`、`2026年秋季` 和完整学年学期均可识别；旧缓存缺少学期时也按标题中的明确年份与季节补充。标题本身没有学期的课程保留空值，由课程中心结合其他来源的课程代码和学期依据关联。

提交情况独立于截止日期、开放状态和本地进度。`submitted` 保持三态，新增 `submission_status` 区分 `not_submitted`（未提交）、`draft`（草稿）、`submitted`（已提交）、`needs_grading`（已提交待评分）、`graded`（已评分）、`exempt`（豁免）和 `unknown`（待核实）。已提交、待评分、已评分输出 true；未提交和草稿输出 false；没有证据时输出 null。豁免另有 `exempt: true`，不列待办，已有提交／评分证据仍可保留 submitted=true。

判定先读取成绩和提交活动：待评分是已正式提交；数值 0 是有效成绩，空串、破折号、布尔值与非有限数不是成绩证据。活动标签只读取状态区域，不从作业标题推断。缺少成绩列、有列但状态不明、草稿或成绩与未提交记录冲突时，只读访问作业历史：正式历史页的尝试日期与提交内容证明已提交；上传表单证明尚未提交；草稿标记仍为草稿。本次成绩／活动仍有正式提交证据时，不因另一条草稿记录转为未提交。请求仅使用 GET，不上传文件、保存草稿或提交作业。

`submission_evidence` 为 `gradebook`、`activity`、`submission_history`、`cached` 或 `unavailable`；`submission_reason` 说明判定依据，`checked_at` 记录本次检查时间。历史明确提供时补充 `submitted_at`、`due_at`、`due_at_evidence` 和 `max_score`，日期采用北京时间，不把只有日期的文字猜成午夜。作业原站链接直达对应作业。

本次读取失败时保留上次可确认的提交情况和检查时间，标记 `submission_stale: true` 并提示部分失败；没有历史证据则保持 null。旧缓存未提供上述字段的 null 继续按兼容规则输出 false，新同步的 unknown／exempt 不做这种转换。作业页、课程中心、待办与 AI 使用同一状态；缓存结果仍可展示，但不能宣称本次已核实。开放状态仍独立判断，逾期不等于入口关闭。

状态含义参考 Anthology 的[尝试状态说明](https://support.anthology.com/apex/downloadArticleasPDF?id=kaEPU0000005Knh2AE)和[豁免说明](https://help.anthology.com/blackboard/instructor/en/grading/grading-assessments/grant-exceptions-and-exemptions.html)；解析边界以本模块合成检查和原站实际结构为准。

`GET /file?material_id=规范资料ID` 从当前账号快照确认文件，再读取 Blackboard 附件 API 或已确认的 `/bbcswebdav/` 路径；认证、目标校验、暂存和清理由公共服务处理。`stop(context)` 结束同步线程。项目 `check.sh` 自动执行本模块合成检查。
