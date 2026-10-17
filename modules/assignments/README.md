# 作业管理

提交情况由来源证据决定，新增 `submission_status` 区分未提交、草稿、已提交、待评分、已评分、豁免和待核实。`submitted` 继续表示原站是否提交，本地 `local_status=done` 不改变它。豁免、未知状态、待评分和已评分不会进入待办；草稿仍需正式提交，在本学期且来源开放时保留为待办。

快照为每条作业提供 `needs_review`、`source_status`、`source_updated_at` 和 `source_stale`。读取失败保留上次结果并明确显示缓存，未知和过期缓存集中出现在“待核实”；已知的缓存待办数量保留，不把网络失败解释为作业已完成。详情显示判定依据和检查时间，原站明确提供的提交时间与截止时间分别展示。

`summary.submission_states` 统计全部缓存的七种状态，`summary.needs_review` 为全部缓存需核实的记录数；原有 `total/unsubmitted/pending/by_source` 保持。`unsubmitted` 包括明确未提交和草稿，不含豁免与未知；所有统计与关键词或分页无关。

依赖课程中心公开 API。`GET /snapshot` 汇总 Gradescope 与 Blackboard 作业，返回按发布时间倒序的列表与按截止时间排序的 pending；pending 仅包含本学期、来源明确允许处理且明确未提交的项目。预告、关闭、已提交与未知状态分别保留；过期且来源仍开放的作业继续显示待办。

`summary` 为当前账号全部缓存作业统计，包含 `total`（记录总数）、`unsubmitted`（未提交总数）、`pending`（本学期待办数）和 `by_source`（各来源的同名统计）。统计不受前端搜索、课程筛选或 AI 分页影响，页面筛选后的待办集合单独计算。截止时间缺失或已过不会单独排除待办；开放状态、当前学期及提交状态仍分别判断。首页和 AI 使用同一待办集合及统计。

`POST /sync` 通过课程中心更新已配置来源。`GET /detail?assignment_id=规范ID` 实时读取 Gradescope 详情或返回 Blackboard 已缓存题目资料。页面可按学期、课程、关键词查看，资料下载使用所属来源模块的公开地址。模块不读取其他 Store。项目 `check.sh` 验证三态提交、历史课程与过期仍开放的情况。
