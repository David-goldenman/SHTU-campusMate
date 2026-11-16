# ELRC 虚拟社区

归属今日讨论中的「虚拟社区 QJQ」。本模块从 QJQ 的 `elrc.py`、`elrc_content.py` 提取课程发现、学期识别、课次匹配、转写、学校摘要及检索逻辑，挂载在**课程中心**。

## 使用

1. 在框架设置中连接「学校 IDS」，目标选择 `elrc`。
2. 进入课程中心，点击「更新课程目录」，按学校给出的教学学期筛选。
3. 对需要的课程点击「同步资料」。同步完成后按课次查看转写和学校摘要，或搜索原文。
4. 已有缓存可离线读取；换账号前在框架设置中清除模块数据，避免混用旧账号课程。

逐课同步随当前 HTTP 请求完成；课程中心的全局同步则通过共享 Source 后台读取课程与录播目录，停止模块时取消并等待工作线程。两种同步使用独立状态键，互不覆盖进度；均不自动调用 AI。逐课同步期间宿主阻止热卸载，完成后即可启停或刷新。关闭页面只停止前端等待，已被服务接受的同步会继续至完成或报错。成功课次在 24 小时内复用缓存，失败后保留原有正文并标记过期/部分可用。

## 接口

所有路径以 `/api/v1/modules/elrc` 为前缀，写操作使用框架 CSRF 保护。

| 接口 | 用途 |
| --- | --- |
| `GET /snapshot` | 共享校园数据快照；包含原有课程和已缓存课次正文，供课程中心、总览与助手读取 |
| `POST /sync`（202） | 后台刷新来源课程、章节及录播目录 |
| `GET /recording?course_id=...&recording_id=...` | 读取共享录播目录中的课次及流标识 |
| `GET /transcript?stream_id=...` | 按已发现的流读取转写和学校摘要 |
| `GET /playback?lesson_id=...` | 为当前账号目录中已知的录播打开临时播放会话，返回课次列表；缓存课次默认选中对应课堂 |
| `GET /playback/{token}/sources?lesson=...` | 查询指定课次的教师、全景、屏幕画面，只返回本地播放入口 |
| `GET/HEAD /playback/{token}/media/{source_id}` | 按 HTTP Range 读取视频；每次最多 4 MiB，支持进度拖动 |
| `GET /catalog?semester=current` | 本地课程、学期、缓存计数；也支持 `all` 或目录中的学期 ID |
| `POST /discover`，`{"semester":"current"}` | 从学校刷新课程目录 |
| `GET /sync` | 最近一次同步状态及当前课次 |
| `GET /courses/{id}` | 已发布课件目录与课次清单 |
| `POST /courses/{id}/sync`（202），`{"force":false}` | 提交该课程的后台同步，返回初始进度；`force:true` 忽略 24 小时复用窗口 |
| `GET /courses/{id}/lessons/{lesson_id}?offset=0&limit=100&q=` | 分页转写、学校摘要；`limit` 最大 200 |
| `GET /search?q=电场&semester=current&course_id=...&limit=12` | 可引用的本地证据，最多 12 条、每条最多 4000 字 |

检索返回 `items`，每条包含 `source_id`、`text`、课程和学期、`lesson_id`、`source_kind`、原文起止秒数及来源 URL。`source_kind=summary` 明确表示学校 AI 摘要。教育模块只通过上述公开 HTTP 接口读取资料，不访问本模块的文件。

## 数据和边界

- `/snapshot` 网络失败附带 `network_failure`，课程中心自动显示诊断。`/discover` 网络失败返回 HTTP 502 与 `{detail:{message,network_failure}}`。逐课同步通过 `GET /sync` 提供状态、当前课次、错误说明和 `network_failure`；原生页面就地显示进度与诊断。切页后继续后台同步，返回时恢复进度；模块停止时取消并等待任务结束。成功同步清除旧状态，已缓存内容保持可读。标记与诊断协议见 [AUTH.md](../../docs/AUTH.md)。
- 学校请求通过 `context.auth.authenticated_client("ids", target="elrc")`；不复制 QJQ 的独立登录、凭据或 Cookie 文件。
- 缓存仅位于本模块 `context.data_dir`，进度使用 `context.store`。模块不保存账号秘密。
- 按学校的 `detail.courseId` 和学期关联录播，避免同名课程串课；时间轴保持原项目的 100 纳秒转换（除以 10,000,000）。
- 课件显示目录并引导打开学校课程页。录播可在课程中心播放，仅访问学校已授权的教学社区地址；视频分段经过本地后台，不整段落盘，学校凭据和上游播放地址不发送到页面。
- 播放会话只存在于内存，按账号版本隔离，闲置 30 分钟后过期，最多保留 8 个；每个会话最多保留 48 个近期画面入口。模块停止时清理会话，换号后旧入口失效。视频内容不进入业务缓存，不持久保存观看历史。
- 不允许任意视频 URL；画面只能来自已知录播的学校查询结果，跳转仍限制在教学社区 HTTPS 地址。来源不支持分段、返回登录页或无权限时显示错误，并保留原站入口。
- 微信适配器、聊天归档、原独立桌面安装器和私人运行数据未迁入。

## 播放器参考

课次到媒体地址的接口顺序、画面分类及切换时保留播放状态，参考 [TechPie 的 ELRC client](https://github.com/HeZeBang/TechPie-flutter/blob/ff73ca0d922221895d4f8396969f658671696ee6/lib/services/elrc_client.dart) 与 [播放器](https://github.com/HeZeBang/TechPie-flutter/blob/ff73ca0d922221895d4f8396969f658671696ee6/lib/pages/elrc_player_page.dart)，参考提交 `ff73ca0d922221895d4f8396969f658671696ee6`。本项目按现有 Python 服务、账号隔离与浏览器原生视频控件实现，没有引入 Flutter/WebView 运行时或 TechPie 的登录服务。

`python modules/elrc/checks/check_playback.py` 使用合成学校响应，覆盖已知录播校验、课次匹配、画面查询、Range、换号、过期、错误与清理。真实学校播放还受当前账号权限、学校服务与网络状态影响。

## 验证

在项目 uv 环境运行 `python modules/education/checks/check_modules.py`。集成检查使用合成学校响应，覆盖目录发现、学期隔离、课次同步、分页、时间轴、刷新失败保留缓存，以及模块启停。真实学校账户的连接有效性需在设置中单独确认；本次迁移没有使用私人课程缓存或实际登录。
