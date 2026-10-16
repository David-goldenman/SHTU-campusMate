# 作业管理

依赖课程中心公开 API。`GET /snapshot` 汇总 Gradescope 与 Blackboard 作业，返回按发布时间倒序的列表与按截止时间排序的 pending；pending 仅包含本学期、来源明确允许处理且明确未提交的项目。预告、关闭、已提交与未知状态分别保留；过期且来源仍开放的作业继续显示待办。

`POST /sync` 通过课程中心更新已配置来源。`GET /detail?assignment_id=规范ID` 实时读取 Gradescope 详情或返回 Blackboard 已缓存题目资料。页面可按学期、课程、关键词查看，资料下载使用所属来源模块的公开地址。模块不读取其他 Store。项目 `check.sh` 验证三态提交、历史课程与过期仍开放的情况。
