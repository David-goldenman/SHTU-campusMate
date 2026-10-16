# ELRC 虚拟社区 · QJQ

归属今日讨论中的「虚拟社区 QJQ」。本模块从 QJQ 的 `elrc.py`、`elrc_content.py` 提取课程发现、学期识别、课次匹配、转写、学校摘要及检索逻辑，挂载在**课程中心**。

## 使用

1. 在框架设置中连接「学校 IDS」，目标选择 `elrc`。
2. 进入课程中心，点击「更新课程目录」，按学校给出的教学学期筛选。
3. 对需要的课程点击「同步资料」。同步完成后按课次查看转写和学校摘要，或搜索原文。
4. 已有缓存可离线读取；换账号前在框架设置中清除模块数据，避免混用旧账号课程。

每次同步一门课，随当前 HTTP 请求完成；没有独立后台线程、定时采集或自动 AI 调用。同步期间宿主阻止热卸载，完成后即可启停或刷新。关闭页面只停止前端等待，已被服务接受的同步会继续至完成或报错。成功课次在 24 小时内复用缓存，失败后保留原有正文并标记过期/部分可用。

## 接口

所有路径以 `/api/v1/modules/elrc` 为前缀，写操作使用框架 CSRF 保护。

| 接口 | 用途 |
| --- | --- |
| `GET /catalog?semester=current` | 本地课程、学期、缓存计数；也支持 `all` 或目录中的学期 ID |
| `POST /discover`，`{"semester":"current"}` | 从学校刷新课程目录 |
| `GET /sync` | 最近一次同步状态及当前课次 |
| `GET /courses/{id}` | 已发布课件目录与课次清单 |
| `POST /courses/{id}/sync`，`{"force":false}` | 同步该课程；`force:true` 忽略 24 小时复用窗口 |
| `GET /courses/{id}/lessons/{lesson_id}?offset=0&limit=100&q=` | 分页转写、学校摘要；`limit` 最大 200 |
| `GET /search?q=电场&semester=current&course_id=...&limit=12` | 可引用的本地证据，最多 12 条、每条最多 4000 字 |

检索返回 `items`，每条包含 `source_id`、`text`、课程和学期、`lesson_id`、`source_kind`、原文起止秒数及来源 URL。`source_kind=summary` 明确表示学校 AI 摘要。教育模块只通过上述公开 HTTP 接口读取资料，不访问本模块的文件。

## 数据和边界

- 学校请求通过 `context.auth.authenticated_client("ids", target="elrc")`；不复制 QJQ 的独立登录、凭据或 Cookie 文件。
- 缓存仅位于本模块 `context.data_dir`，进度使用 `context.store`。模块不保存账号秘密。
- 按学校的 `detail.courseId` 和学期关联录播，避免同名课程串课；时间轴保持原项目的 100 纳秒转换（除以 10,000,000）。
- 课件显示目录并引导打开学校课程页，不下载视频或绕过学校访问权限。
- 微信适配器、聊天归档、原独立桌面安装器和私人运行数据未迁入。

## 验证

在项目 uv 环境运行 `python modules/education/checks/check_modules.py`。集成检查使用合成学校响应，覆盖目录发现、学期隔离、课次同步、分页、时间轴、刷新失败保留缓存，以及模块启停。真实学校账户的连接有效性需在设置中单独确认；本次迁移没有使用私人课程缓存或实际登录。
