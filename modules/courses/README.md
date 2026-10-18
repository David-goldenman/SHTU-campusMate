# 课程中心

课程卡片和详情按开课院系显示颜色与文字标签：创管紫、创艺橙红、生命棕黄、物质绿、数学所深蓝、信息浅蓝，体育与书院红。院系优先取课程来源明确字段，缺失时按唯一课程代码匹配教务培养方案；冲突或未知保留中性色。`PE/CLPE` 课程代码标记体育课并显示 Font Awesome 跑步图标。

`GET /appearance` 返回 `{courses:[{id,course_ids,code,term,department,department_source,appearance}],palette}`，`appearance` 包含 `key/label/accent/tint/ink` 和可选 `icon`。时间表通过该公开接口匹配课程；课程模块不调用时间表的 `/schedule`，不会形成聚合循环。缺少教务模块仍可使用来源院系。所有院系判断位于课程模块；共享 UI 仅提供校验六位十六进制颜色的 `applyAccent(element, appearance)`。

E 云课堂（`ecourse`）通过公开快照接入课程、课件说明、公告和作业；统一同步会触发其只读刷新。原站提供的学期、课程代码及开课院系保留在课程来源记录中，附件通过原站课程栏目查看。来源停用按现有协议降级，首页助手通过 `/context` 使用同一份资料。

作业分类与作业管理共用提交状态标签，区分草稿、待评分、已评分、豁免和待核实；pending 筛选排除豁免与未知状态。`POST /context` 同时保留 `submission_status/submission_evidence/submission_reason/checked_at/submitted_at/submission_stale/exempt/due_at_evidence`，供 AI 与通知使用来源证据，而不是只看一个布尔值。

`GET /snapshot` 的 `network_failures` 转发已启用来源的网络故障标记。页面自动检测并在同步提示旁给出原因和处理建议，无需进入设置；仅来源明确的网络错误触发，成功重试后清除。

界面以本学期的课程为入口，每门课程汇总已连接平台的可用内容，提供资料、作业、公告、讨论、录播、上课安排及平台成绩条目分类与原站链接。页面使用 `navigation.layout:primary`，平台来源保持 API 与同步能力。可查看其他学期、搜索课程，并用可勾选列表手动关联不同平台的同一课程。

课程列表直接展示录播状态与已收录条数、待办及资料数量，支持「有录播／暂无录播／待确认」筛选。录播状态依据当前快照中按来源课程 ID 关联的 `lessons`，不把教学社区平台入口当作录播证据；只有来源读取成功、无该来源问题、无未关联录播且课程已关联教学社区时，零条记录才显示「暂无录播」。未同步、读取失败、缓存或课程尚未关联时显示「录播待确认」，已有录播仍保持可见。数量代表快照记录条数，不推断实际课时数。详情始终保留录播标签及空状态，有记录时提供直接进入录播列表和原站的入口。

搜索、录播筛选、课程切换和内容标签使用一次 `/snapshot` 的公开数据在本页完成，不反复请求聚合 `/course`；关联课程时才读取 `/groups`。课程待办数量与公开 `pending` 筛选保持一致：包含 Blackboard、Gradescope 和 E 云课堂中明确开放、未提交或草稿的作业，排除豁免、待核实和已提交状态。新增状态检查在 `checks/check_summary.py`，由完整检查入口自动运行。

浏览器回归使用 `node modules/courses/checks/check_web.mjs <本机地址>`，以合成数据检查录播证据与筛选、跨平台待办、课程关联、键盘切换、四种主题的电脑／手机布局和卸载清理。截图保存在 `.codex/tmp/courses-ui/`。公共工作区联动检查沿用 `node checks/check_campus_workspace.mjs <本机地址>`。

自动关联先规范课程代码中的空格、横线与大小写，再按代码和学期合并。缺少代码时，只在相同规范名称和学期唯一对应一个已知课程代码时关联；有多个候选保留独立，交由用户手动选择。

Piazza 的 Resources 文件与链接通过其公开快照进入“资料”，讨论帖继续放在“讨论”。文件可在浏览器查看或下载，使用 Piazza 模块的本机文件接口复用已保存登录态；目录中的资源更新时间参与助手读取版本校验，PDF 正文由学习助手按需提取。

Blackboard 活跃课程缺少学期时，只有相同规范课程代码在已有来源中唯一对应本学期，且教务课表或 ELRC 提供该学期证据，才参与本学期自动关联。已明确的历史学期、多个学期候选、无匹配代码、未知/已结束状态均不据此推断；不能单凭 `active` 认定本学期。手动分组优先。聚合课程的 `term_matches` 保留被匹配课程、学期与证据来源 ID，`sources` 中的原始记录保持原样。

通过 `context.api` 读取六个来源的公开快照，维护自身课程关联设置。代码与规范学期一致时自动合并；缺失代码的唯一名称匹配见上文，其他课程保持独立。`GET /snapshot` 返回聚合课程、八类内容、来源状态及读取范围。本学期依次采用教务当前学期、ELRC 学校当前学期；二者都未提供时才按上海日期估计。`POST /sync` 请求已配置账号的来源同步。

`GET /catalog/{collection}` 支持 course_id、current、pending、source、q、offset、limit，limit 最大 500。pending 只适用于作业，要求来源为 Gradescope、Blackboard 或 E 云课堂、明确开放且明确未提交，并排除豁免与待核实状态。`GET /course?course_id=聚合ID` 返回各平台课程、资料、讨论、录播、作业和折叠课表。

`GET/PUT /groups` 读取或完整保存 `{groups:[{id,title,course_ids}]}`；每组 2–20 个已知来源课程，每门课仅属于一个手动组，空数组恢复自动关联。模块不读取其他模块数据库。项目 `check.sh` 执行来源不可用、学期关联、三态待办及手动关联检查。

`POST /context` 接收 `{course_id?:string, context_ids?:string[]}`，返回 `{items,courses,text,context,account_revision,revision}`。这是助手和通知模块使用的公开资料选择接口：默认选择本学期课程及邮件；指定课程时只取该课程资料并排除邮件；显式空 context_ids 得到空资料，未提供则按课程范围选择。每条正文最多 1800 字、最多 400 条、序列化上下文最多 85000 字符；截断计数放在 context 中。items 带 source_revision，revision 结合当前账号及所选资料版本；调用方完成异步 AI 操作后仍需核对 account_revision。未知课程返回 404，失效选择返回 422，读取过程中切换账号返回 409。来源模块缺失按 snapshot 的 issues 降级；本接口只读缓存，不触发同步或 AI。

可选群消息模块通过公开 `/snapshot` 补充已确认的课程公告，缺失或停用不影响六个学校来源。群原文不进入课程聚合；同步按钮不触发聊天采集。
