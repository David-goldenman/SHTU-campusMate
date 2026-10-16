# Piazza · WYT

归属今日讨论中的「piazza WYT」。依据 `QQ-Piazza-采集程序-分享版-20261015.zip` 中 `message-hub/source_api.py`、`connectors.py`、`storage.py` 的 Piazza 部分接入，挂载在**通知**。

## 使用

1. 在统一设置中连接 Piazza 账号。
2. 展开「管理关注课程」，每行填写「课程 ID 课程名称」。课程 ID 来自本人可访问的 Piazza 课程网址。
3. 点击「采集最新帖子」读取最近 20 条，再按需「继续采集下一页」。失败时按钮变为重试未完成页。
4. 在本地按重要程度或关键词筛选，展开帖子及回复、打开原站/原附件、标为已读。缓存可离线阅读。

## 接口

前缀为 `/api/v1/modules/piazza`；所有写接口沿用框架 CSRF 保护。

| 接口 | 用途 |
| --- | --- |
| `GET /courses` | 关注课程及最近采集状态 |
| `PUT /courses`，`{"courses":[{"id":"...","name":"..."}]}` | 设置最多 30 门课程 |
| `POST /courses/{id}/sync`，`{"offset":0}` | 采集该课程 20 条帖子；失败帖子不覆盖旧缓存，不推进失败页 |
| `GET /posts?course_id=...&offset=0&limit=20&level=all&q=` | 分页离线缓存；`level` 为 all/high/medium/normal |
| `PUT /courses/{id}/posts/{post_id}/read`，`{"read":true}` | 设置已读状态 |

采集返回 `status`、`saved`、`failed_ids`、`next_offset`、`checked_at`。`next_offset=null` 表示本轮没有下一页；存在失败时指向本页以便重试。帖子保留标题、正文和回复、原始创建/更新时间、附件链接、重要程度及理由。无法识别的时间保留空值，不补成当前时间。

## 与原分享程序的差异

- 使用 `context.auth.authenticated_client("piazza")`；不迁入自带登录、Cookie 存储、QQ/OneBot、Webhook、QQ 文件归档或本机 AI 客户端。
- 保留 Piazza 只读 `network.get_my_feed`、`content.get` 调用与解析逻辑；重要程度是可解释的候选规则，不调用 AI。
- 用模块 `context.store` 保存关注范围和帖子。相同帖子重复采集会覆盖更新并去重；正文不变时保留已读状态。切换账号前通过框架设置清除模块数据。
- 本阶段采用用户触发的分页采集，没有轮询后台进程；停止/刷新由宿主等待当前请求结束，不遗留线程、浏览器或客户端。
- 附件提供经过 HTTPS 协议检查的原始链接，不自动下载、不转发 Cookie 给附件站。帖子按纯文本展示。
- 远端列表按更新时间变化，分页期间更新的帖子可能重复或移动，因此不承诺完整历史；每次可从最新页重新核对。
- 移除关注课程只隐藏该课程，缓存保留至框架清除模块数据。

## 验证

运行 `python modules/education/checks/check_modules.py`。检查使用合成 Piazza 响应，覆盖正文/回复、安全链接、候选规则、去重与已读、失败页重试、登录失效保留缓存及热启停。本次迁移没有调用真实 Piazza 或导入私人帖子。
