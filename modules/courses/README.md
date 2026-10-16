# 课程中心

通过 `context.api` 读取六个来源的公开快照，维护自身课程关联设置。代码与规范学期一致时自动合并；其他课程保持独立。`GET /snapshot` 返回聚合课程、八类内容、来源状态及读取范围。本学期依次采用教务当前学期、ELRC 学校当前学期；二者都未提供时才按上海日期估计。`POST /sync` 请求已配置账号的来源同步。

`GET /catalog/{collection}` 支持 course_id、current、pending、source、q、offset、limit，limit 最大 500。pending 只适用于作业，要求来源为 Gradescope 或 Blackboard、明确开放且明确未提交；未知状态保持独立。`GET /course?course_id=聚合ID` 返回各平台课程、资料、讨论、录播、作业和折叠课表。

`GET/PUT /groups` 读取或完整保存 `{groups:[{id,title,course_ids}]}`；每组 2–20 个已知来源课程，每门课仅属于一个手动组，空数组恢复自动关联。模块不读取其他模块数据库。项目 `check.sh` 执行来源不可用、学期关联、三态待办及手动关联检查。
