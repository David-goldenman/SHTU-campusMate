# Piazza · WYT

## 校园数据集成

保留课程自动发现、本学期匹配、关注选择、20 条分页采集、附件、重要性规则与已读状态。新增 `GET /snapshot` 向课程中心发布已关注课程的缓存正文；`POST /sync`（202）后台刷新已加入课程及各课程最近 50 条讨论；`GET /post?course_id=...&post_id=...` 读取该近期目录中的正文与回复。后台任务在 `stop(context)` 中取消并结束。已更新帖子的旧正文会失效，重新读取后再提供完整文字。

共享快照按账号版本隔离，旧采集缓存首次接入时绑定当前账号版本；换账号仍应先清除旧模块数据，避免旧页面混用缓存。来源课程通过已实测的 `user.status` / `networks` 发现，`active` 状态不作为本学期依据。

归属今日讨论中的「piazza WYT」。依据 `QQ-Piazza-采集程序-分享版-20261015.zip` 中 `message-hub/source_api.py`、`connectors.py`、`storage.py` 的 Piazza 部分接入，挂载在**通知**。

## 使用

1. 在统一设置中连接 Piazza 账号。
2. 点击「自动发现我的课程」，读取本人加入的课程及 Piazza 标注学期；勾选需要的课程，再保存关注范围。也可在「手动管理关注课程」中填写课程 ID 与名称。
3. 点击「采集最新帖子」读取最近 20 条，再按需「继续采集下一页」。失败时按钮变为重试未完成页。
4. 在本地按重要程度或关键词筛选，展开帖子及回复、打开原站/原附件、标为已读。缓存可离线阅读。

## 接口

前缀为 `/api/v1/modules/piazza`；所有写接口沿用框架 CSRF 保护。

| 接口 | 用途 |
| --- | --- |
| `GET /courses` | 关注课程及最近采集状态 |
| `GET /catalog` | 上次发现的已加入课程、学期匹配结果、参考学校学期及检测时间 |
| `POST /discover`，`{"current_semester":{"id":"2026-2027-1","name":"2026-2027学年秋季"}}` | 从 `user.status` 自动发现课程；可省略学校学期，此时标为学期待确认 |
| `PUT /courses`，`{"courses":[{"id":"...","name":"..."}]}` | 设置最多 30 门课程 |
| `POST /courses/{id}/sync`，`{"offset":0}` | 采集该课程 20 条帖子；失败帖子不覆盖旧缓存，不推进失败页 |
| `GET /posts?course_id=...&offset=0&limit=20&level=all&q=` | 分页离线缓存；`level` 为 all/high/medium/normal |
| `PUT /courses/{id}/posts/{post_id}/read`，`{"read":true}` | 设置已读状态 |

采集返回 `status`、`saved`、`failed_ids`、`next_offset`、`checked_at`。`next_offset=null` 表示本轮没有下一页；存在失败时指向本页以便重试。帖子保留标题、正文和回复、原始创建/更新时间、附件链接、重要程度及理由。无法识别的时间保留空值，不补成当前时间。

## 自动发现与学期判断

`POST /discover` 仅缓存课程目录，不更改已关注课程，也不开始采集。返回的每门课程包含 `id`、`name`、`code`、`term`、`school`、`platform_status`、`semester_state` 和判断理由；服务端只提取这些课程字段，不保存或返回原始账号响应中的个人资料、sid 或配置。

界面通过 ELRC 的公开 `GET /api/v1/modules/elrc/catalog` 取得学校确认的当前学期，目录更新超过 24 小时则不作为当前学期依据。`Fall 2026` 对应 `2026-2027学年秋季`；同一学年春季、夏季使用后一公历年。只有可解析的平台学期与学校学期一致时标记 `current`，其他明确学期为 `other`；没有学校参照、平台未标注或 `Other` 等无法匹配的学期为 `unknown`。`active/inactive` 和课程创建日期不参与判断。

结果注明检测时间；学校切换学期后先在课程中心更新目录，再重新发现 Piazza 课程。没有关注课程时默认勾选已确认的本学期课程，用户点击保存后生效；已有关注范围会保留，未在自动目录中出现的手动课程也会保留。

## 与原分享程序的差异

- 使用 `context.auth.authenticated_client("piazza")`；不迁入自带登录、Cookie 存储、QQ/OneBot、Webhook、QQ 文件归档或本机 AI 客户端。
- 使用 Piazza 只读 `user.status`、`network.get_my_feed`、`content.get` 调用；重要程度是可解释的候选规则，不调用 AI。
- 用模块 `context.store` 保存关注范围和帖子。相同帖子重复采集会覆盖更新并去重；正文不变时保留已读状态。切换账号前通过框架设置清除模块数据。
- 本阶段采用用户触发的分页采集，没有轮询后台进程；停止/刷新由宿主等待当前请求结束，不遗留线程、浏览器或客户端。
- 附件提供经过 HTTPS 协议检查的原始链接，不自动下载、不转发 Cookie 给附件站。帖子按纯文本展示。
- 远端列表按更新时间变化，分页期间更新的帖子可能重复或移动，因此不承诺完整历史；每次可从最新页重新核对。
- 移除关注课程只隐藏该课程，缓存保留至框架清除模块数据。

## 验证

运行 `python modules/piazza/checks/check_discovery.py` 和 `python modules/education/checks/check_modules.py`。合成数据检查覆盖课程自动发现、学期匹配（包含跨年春季、旧学期 active、无法识别的学期）、输出字段筛选、发现失败保留目录、关注范围不变，以及原有帖子采集与模块启停。

2026-10-16 已在用户授权下完成真实登录态导入、课程发现、学校学期匹配、所选课程帖子采集及缓存分页检查。私人登录态、课程列表、帖子和验证记录只存放在本机忽略目录，未提交到仓库。
