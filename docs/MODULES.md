# 模块开发接口

共享展示 SDK `/assets/campus.js` 的 `submissionLabel(item)` 供作业管理和课程中心显示同一提交状态及缓存提示；它只格式化来源已有字段，不请求来源、不决定待办。状态与依据由来源模块提供，待办规则由业务聚合模块实现。

`applyAccent(element, {accent,tint,ink})` 校验六位十六进制颜色后，通过 CSSOM 设置 `--record-accent/--record-tint/--record-ink`，缺失或非法值移除对应属性。课程中心与时间表共用该展示 helper；共享 SDK 不选择学院、课程或业务配色。

作业管理 `GET /snapshot` 的 `summary` 为全部缓存统计，`summary.by_source[平台]` 为该平台统计；两层均含 `total/unsubmitted/pending/submission_states/needs_review`，不受关键词或分页影响。七种提交状态互斥，`submitted` 只确认提交、评分情况未确认；只有 `needs_grading` 表示待评分，不能用空分数推断。按平台回答时使用对应平台的状态统计。

每项业务功能在自己的 `modules/<id>/` 目录开发，框架通过清单和固定入口加载。主侧栏分类、设置和共享服务由框架统一管理；模块把页面挂到所选分类，将后端接口挂到自己的命名空间。

## 目录和清单

```text
modules/notes/
  module.json
  README.md
  web/
    index.js
    styles.css
  server/
    __init__.py
  harness/
    package.json
    index.js
  checks/
    check_notes.py
```

`module.json` 的全部字段如下：

```json
{"id":"notes","name":"笔记","version":"0.1.0","category":"courses","api_version":1}
```

`name` 是页面标题、模块管理和导航中使用的展示名称，只描述功能，不附成员姓名或个人缩写。

`id` 必须与目录名一致，匹配 `[a-z][a-z0-9_-]{0,47}`；`reload` 由框架保留。`category` 使用同样的 ID 格式，`settings` 由框架保留。业务分类由模块自行声明，无需修改框架白名单。可选 `navigation:{label,icon,description,order,layout}` 决定侧栏文本、图标、描述及顺序（order 为 0–10000；layout 为 `stack`、`tabs` 或 `primary`，默认 `stack`）；相同分类的模块须声明一致内容。旧清单未声明时以分类 ID、▧、空描述、order=100 兼容。冲突时显式声明优先，其后按模块 ID 排序选择第一项；分类按 order、分类 ID 排序。框架设置始终在最后。`version` 由模块负责人维护，`api_version:1` 表示当前框架契约。`web/index.js`、`web/background.js`、`server/__init__.py` 与 `harness/package.json` 至少提供一个。模块可以只提供页面、后端服务或原生 AI 插件；配置能力放在自己的页面、模块 API 或插件 bundle 内。

新增 AI 工具和工作流使用独立模块 ID，提供 `harness/` 原生入口。普通页面与 Python API 按需添加；纯插件的 `frontend_url` 为 `null`，通过共享 `/api/v1/ai/run` 执行。模块列表以 `harness:true` 标识原生入口，调用时选择已就绪模块。基础 AI 助手提供资料选择和任务结果展示，每项具体工具按自己的模块生命周期启停。

带页面的插件由所属页面发起业务任务，基础 AI 助手提供对应分类链接；纯工具插件在“插件任务”中选择。完整例子为首页分类的 [academic-assistant](../modules/academic-assistant/README.md)，同时拥有聊天界面、公开业务 API 与原生工具。其工具通过一次任务有效的令牌调用本模块后端，后端复用 `context.api`；内部运行时配置见 [AI 插件接口](AI.md#原生-harness-插件)。新增业务保持在独立模块内，主框架维护身份、AI 调用和生命周期。

模块列表的 `has_frontend` 表示代码目录提供了页面入口，独立于启停和加载状态；侧栏据此保留已启用页面的加载错误入口。`frontend_url` 仅在页面就绪时提供可导入的地址。

## 前端入口

```javascript
export async function mount(container, context) {
  const removeStyle = context.ui.useStyle(new URL('./styles.css', import.meta.url), context.signal);
  const response = await context.api('/status', {signal: context.signal});
  container.innerHTML = `<p>${context.ui.escape(response.message)}</p>`;
  return () => { removeStyle(); };
}
```

`mount` 可以同步或异步，接收一个独立挂载节点，返回可选的清理函数，清理函数也可以异步。模块初始化失败前自行释放已创建的资源。宿主在切页、刷新和停用时先触发 `context.signal`，再等待清理函数完成。

| 上下文属性 | 用法 |
| --- | --- |
| `context.module` | 当前模块的 `ModuleInfo` |
| `context.focus(active)` | 将当前模块设为本分类的主要阅读区；其他卡片暂时隐藏，false 恢复，卸载时清理 |
| `context.api(path, options)` | 请求 `/api/v1/modules/<id>` 下的接口，自动 JSON 与本地写请求头；可用 `timeoutMs` 调整等待上限 |
| `context.api(path, {onEvent, signal, ...options})` | 流式 NDJSON 接口逐行调用 `onEvent(event)`；自定义取消信号与模块卸载信号共同生效 |
| `context.services.auth.providers()` | 列出共享认证配置状态 |
| `context.services.auth.status(id)` | 查询某认证提供方的本地状态 |
| `context.services.ai.settings()` | 读取共享 AI 启用状态 |
| `context.services.ai.generate(body)` | 调用通用文本处理 |
| `context.services.ai.chat(body)` | 调用通用对话 |
| `context.services.ai.plugins()`、`.run(body)` | 列出原生插件，调用所选插件执行任务 |
| `context.ui` | 公共 UI helper，组件约定见 [设计文档](DESIGN.md) |
| `context.ui.useStyle(url, signal)` | 挂载样式并在中止时移除，返回幂等清理函数；在首次 await 前调用 |
| `context.ui.bindMenus(container, signal)` | 管理 `details[data-action-menu]` 的外部点击、操作后与 Esc 关闭；Esc 返回 summary，动态菜单适用，监听随 signal 清理 |
| `context.theme` | 当前主题、展示区域、主题专属偏好和选择接口，见 [主题契约 v1](UI_THEME.md) |
| `context.defaultView(container)` | 挂载模块原界面并返回其清理函数，供主题组合；业务 API 沿用当前模块 |
| `context.navigate(category)` | 切换框架分类 |
| `context.signal` | 当前挂载的 AbortSignal，用于 fetch 与 DOM 监听器 |

模块相对导入自己的文件；样式以模块根选择器限定，卸载时移除创建的样式节点。公共按钮、表单、面板和对话框复用框架组件。由宿主提供的版本地址导入入口，子资源通过 `import.meta.url` 或相对 import 加载，更新后地址随版本变化。模块内部的深层页面与选择状态由模块维护，公共分类由 `navigate` 切换。

所有前端调用均使用 HTTP 服务。认证状态供前端提示是否需要配置；密码、Cookie、Key 和登录参数由服务端处理。模块页面的账号连接操作引导用户到框架设置。

## 后端入口

```python
from fastapi import APIRouter

def create_router(context):
    router = APIRouter()

    @router.get('/status')
    def status():
        return {'message': context.store.read('message', '已就绪')}

    return router
```

`create_router(context)` 返回 FastAPI `APIRouter`，模块自身使用相对 HTTP 路径。宿主把它挂到 `/api/v1/modules/<id>/`，路由内注册 `/status` 即对应 `/api/v1/modules/notes/status`。模块 OpenAPI 位于自己命名空间下的 `/openapi.json`。注册路由时不增加自己的重复 `/api/v1` 或模块 ID 前缀；`openapi.json` 是模块宿主保留路径。当前模块契约提供 HTTP API，新增通信方式由框架负责人统一接入本地访问校验和生命周期。

服务端代码使用自己 `server/` 包内的相对导入，例如 `from .parser import parse`。后台任务通过可选的同步 `start(context)` 和 `stop(context)` 管理：`start` 在路由创建后调用；`stop` 在刷新、停用、清数据或服务退出时调用。每个入口遵循相同契约，生命周期钩子使用普通函数，后台异步运行由模块自己管理并在 stop 中等待结束。`stop` 需能清理部分初始化状态；停止失败时宿主阻止继续刷新或删除数据，开发者修复清理后重试。

| 上下文属性 | 用法与存储边界 |
| --- | --- |
| `context.id` | 当前模块 ID |
| `context.modules()` | 当前模块和分类的公开元数据，与管理接口结构一致；不返回凭据 |
| `context.runtime.watch(name, worker)` | 登记已有 Thread 或 concurrent.futures.Future 的运行状态，不启动或停止任务；每模块最多 16 个名称，同名替换，名称不含账号或私人内容 |
| `context.store.read(key, default=None)` | 读取本模块非秘密 JSON 状态 |
| `context.store.write(key, value)`、`.delete(key)`、`.clear()` | 管理本模块 SQLite 命名空间 |
| `context.secrets.get(key)`、`.save(key, dict)`、`.delete(key)` | 管理本模块 DPAPI 加密秘密，缺失返回 `{}` |
| `context.data_dir` | 本模块 `.private/modules/<id>/`，存放持久文件 |
| `context.auth` | 共享认证服务，提供已登录 HTTP 客户端 |
| `context.ai` | 共享 AI，提供 `generate`、`chat`、`run` 和安全配置状态 |
| `await context.api(module_id, path="/snapshot", method="GET", body=None, timeout=None)` | 调用其他模块公开 HTTP API，返回 `httpx.Response`；默认等候 20 秒，可用 `timeout`（秒）调整；停用返回 404、并发已满返回 503、等待超时返回 504 |

每个模块的状态和秘密按模块 ID 分开。账号、密码、Cookie、Key、token 一律交给共享认证或 `context.secrets`，普通配置与缓存放在自己的 store，文件放在自己的 data_dir。模块通过公开 HTTP API 读取其他模块提供的数据；需要跨模块聚合时由集成人员确定公开请求/响应，调用方不得直接访问对方的数据库、文件或私有代码。

认证用法见 [AUTH.md](AUTH.md)，AI 用法见 [AI.md](AI.md)。模块的接口、数据格式、使用的认证提供方、清理行为和检查命令写入本模块 `README.md`，便于人员交接。

## 热插拔流程

模块可提供 `web/background.js`，导出与页面相同的 `mount(container, context)`。就绪时 `ModuleInfo.background_url` 返回版本化地址，否则为 null。宿主在独立节点挂载常驻界面，页面切换时保留；模块停用、刷新、清数据和页面退出时中止并清理。后台入口不增加侧栏条目，也不影响 `has_frontend` 对页面入口的定义。首次 await 前使用带 signal 的样式和清理注册；业务提醒、轮询频率和判断均属于模块。

`navigation.layout` 支持 `stack`、`tabs`、`primary`。primary 只挂载分类的聚合页面，优先选择 ID 等于分类 ID 的页面，否则选择首个页面；其余来源模块保持 API 可用，停用主页面后可由仍启用的页面承接。分类内所有模块使用一致声明。

1. 将完整模块目录放入 `modules/`，在设置中选择刷新模块。新发现模块默认启用，启停状态由框架保存。
2. 侧栏显示存在已启用界面模块的分类，启停后立即更新；同分类的最后一个页面停用时隐藏入口。一个分类可同时挂载多个模块，加载错误保留入口并单独显示；纯后台与 AI 插件在设置中管理。设置始终可访问。
3. 更新模块代码后刷新模块。后端逐模块停止并重新导入；忙碌模块保留原实例，停止失败或超时的模块隔离为 error，正常模块继续刷新。响应在原有模块清单外附加 `warnings` 数组。前端获得新的版本地址重新挂载；单个模块启停只卸载该模块的常驻入口。
4. 停用模块后其后端和静态资源停止服务。已有接口请求需先结束，单个模块启停和清数据在执行中返回 409；全局刷新跳过忙碌模块。页面请求用 `context.signal` 取消。
5. 移除模块时先停用，再删除其代码目录并刷新。用户数据按模块 ID 保留；需要清除时在设置中选择模块数据清除，包含已移除模块留下的数据。

后台任务、定时器和长连接由模块自己的 `stop` 释放。模块必须使用框架的生命周期钩子启动和结束这些活动；数据库连接由宿主在停止后关闭。热更新以模块为单位，Python 公共依赖或主框架的改动使用服务重启。

运行状态登记已用于共享 Source 同步、时间表校历更新、校园后台助手、通知检查和学习提醒。在线程 start 或提交 Future 后调用 `context.runtime.watch('简短任务名', worker)`；重复任务使用固定名称，不能按任务 ID 无限添加。框架记录接口时间、HTTP 状态及错误编号，业务成功与数据新鲜度仍由模块 API 表达。状态仅存于当前实例内存，详见 [运行状态响应](API.md#模块管理)。合成上下文可省略 runtime，调用方用 `getattr(context,'runtime',None)` 兼容。

清除模块数据前会自动快照；恢复同时替换所有模块的普通状态和文件，不处理秘密或核心账号状态。快照需要所有模块的 stop 成功后才读取，后台任务必须完成清理才能参与恢复。不得把凭据放入 store/data_dir；备份只遵循这两个公开的非秘密数据边界。使用 `HTTPException(status, '可公开说明')` 报告预期业务错误，未经处理的异常由框架提供通用提示和错误编号。

原生 AI 插件位于 `harness/`，使用标准 npm package.json 与 Cordis 接口，也支持官方 `dsh.bundle.patch`。模块清单响应的 `harness: true` 表示该模块提供原生插件；它与模块共用启停和刷新。`context.ai.run(..., plugins=[模块ID])` 在独立官方运行时中加载所选插件，并在结束时释放。执行期间插件所属模块保持活动请求计数。详见 [AI 与插件文档](AI.md#原生-harness-插件)。

插件工具按声明的 schema 接收模型参数，并通过 `execution.signal` 响应取消；注册和清理由 Cordis effect 管理。Python 模块选择公开 API 中的资料，在线程池调用同步 AI 服务，再校验引用、输出和账号版本。模块 README 记录工具名、所需 Cordis 服务、输入输出、外部访问与写入范围、持久化和检查方式；版本升级随功能分支更新清单、调用方和文档。

模块属于受信任本地代码，运行权限与框架一致。目录分层和注入上下文用于团队分工与状态隔离；安装模块前审核其代码及外部访问行为。

## 校园数据模块

来源可通过 `Source(..., network_target=共享认证目标)` 选择网络失败诊断；SDK 不选择具体业务目标。网络请求失败的 error/partial 快照附带 `network_failure:{id,target,kind,at,host?}`，重试启动或成功时清除；解析、登录和权限失败不携带该标记。标记按账号版本隔离，不保存原始异常或完整 URL。`Remote.network_error` 仅在内存保留最后一次重试仍失败的 RequestError，供 Source 识别局部失败。聚合页转发 `network_failures` 数组。共享 `sourcePanel` 自动显示，其他页面可用 `/assets/sync-network.js` 的 `bindSyncNetwork(host,context,retry?)`，调用返回对象的 `update(failures)`；同一故障去重，切页中止，恢复后清除。它通过 `context.services.auth.explainNetwork(failures)` 调用公开诊断 API；详见 [AUTH.md](AUTH.md)。结构化 HTTP 错误的 `detail.message` 显示为消息，原公开 detail 保存在前端 Error 的 `details`。

公共 `backend.services.campus` 提供 `Source` 同步生命周期、`Remote` 来源请求、课程与时间规范化。来源模块公开 `GET /snapshot` 和 `POST /sync`（202），快照为 `{status,data,updated_at,message?}`。`data` 包含 `courses/assignments/materials/announcements/posts/lessons/timetable/messages` 八个数组、`metadata` 范围对象和 `issues` 提示数组；标识带来源前缀，未知提交状态保持 `null`。全局请求失败保留上次成功快照；来源可在 `issues` 标明局部读取失败。 `Source(..., stale_after=21600)` 默认将超过 6 小时的 ready 快照标为 `cached`，读取时保留内容并复用模块同步队列后台更新；并发读取只排队一次，停用后保留快照并停止排队。错误、部分结果和登录验证状态继续按原状态返回，账号切换仍隔离缓存。日期带时区，页面以 Asia/Shanghai 展示。

时间表分类保持 `timetable` ID 与 `#timetable` 路由。`timetable` 模块的 `/snapshot`、`/sync` 提供教务上课数据；页面使用 `/schedule`、`/schedule/sync` 汇总 Blackboard、Gradescope 和教务考试。聚合只调用各模块公开 API，停用的来源退出时间表，账号变化时丢弃在途结果。数据格式见 [时间表接口](../modules/timetable/README.md)。

来源读取最多重试一次超时、网络中断、429 与 5xx；分页限制 100 页并检查重复链接和目标域名。共享认证的 `account_revision` 在更新账号、导入会话或忘记登录时变化；缓存按该版本隔离。模块停止时取消后续读取并等待当前工作线程结束，再由宿主关闭 Store。`check.sh` 自动运行每个模块 `checks/check_*.py`。

ELRC 与 Piazza 保留原有细粒度接口，同时提供共享快照。它们的 Source 使用 `state_prefix="campus:"`，将全局后台同步进度与原有逐课同步进度分开。共享快照可读取同模块、同账号版本的原有缓存，使已同步的课次和帖子直接进入聚合；调用者仍只依赖公开 API。

`backend.services.campus.files.download` 在一次认证上下文内获取文件，逐跳校验 HTTPS 目标与端口，将内容暂存模块 `context.data_dir/tmp/downloads/`，通过 FileResponse 交付后删除。模块提供固定的服务域名列表与按需解析文件链接的函数，临时签名地址留在后端。

模块可定义 `authorize_write(context, request) -> bool` 接受自己的专用 Bearer 令牌。宿主仍先校验 Host、Origin 与跨站请求；钩子必须精确限制路径和令牌。正常网页写请求使用框架 CSRF。邮件模块仅为专用 Agent 写标签接口启用此能力，密钥由该模块 `context.secrets` 保存。

模块启停与刷新按生命周期串行执行，停止钩子运行时释放注册表读取锁，允许后台任务完成已有的跨模块调用。开始停止前先关闭对应路由入口；正在执行的请求仍按原契约返回 409。

模块的 signal 在切页、停用、刷新和该模块 mount 失败时中止；一个模块加载失败不会中止同页其他模块。计时器、全局监听器等须在首次异步等待前注册 abort 清理。仅在 mount 最后返回 cleanup 无法覆盖提前抛错。

## 故障隔离与等待上限

前端普通读取默认 30 秒，写请求默认 120 秒；AI 调用方显式选择 600 秒，流式请求默认总计 600 秒、连续无事件 240 秒。`timeoutMs` 与 `idleTimeoutMs` 可按公开接口的实际耗时调整。到期中止浏览器请求，保留调用方输入并提示检查结果；不自动重试写入。非 JSON 错误页转换为可读错误，不把原始响应内容显示给用户。

前端入口导入上限 30 秒、mount 上限 35 秒；卸载清理并行执行，每项最多等待 3 秒。失败或超时不会阻止其他页面／后台组件清理，迟到的 mount 返回仍会执行清理。模块必须遵守 abort 信号，避免卸载后修改界面。同步 JavaScript 死循环仍会阻塞浏览器事件循环，超时机制不隔离这种不遵守契约的代码。

后端停止钩子最多等待 5 秒。每个模块只保留一个未完成的停止任务；超时后关闭其公开入口，保留原 Store、Python 包和清理任务，不创建第二个实例。实际清理结束后才释放资源，再次刷新可以恢复该模块。停止钩子抛错时允许修复后重试，因此应保持可重入和幂等。其他模块继续工作。清数据只有全部模块安全停止后才能执行；失败时恢复可用模块并保留数据。

跨模块请求统一在宿主事件循环执行，调用方超时或取消只结束等待。真实请求仍计入所属模块，完成前不能卸载或关闭 Store；每模块最多 8 个未完成的内部请求，避免轮询重复堆积。聚合方按非 200 响应显示来源不可用，其他来源继续汇总。写请求超时不代表服务端未写入，重试前检查结果或使用业务提供的去重标识。

这些边界沿用单进程框架和官方 Harness 子进程，不强行终止任意 Python 线程。不遵守取消约定的任务保持隔离，可能需要重启本地服务；不能把停止等待当成任务已经结束。故障回归见 `checks/check_resilience.py`、`checks/check_frontend.mjs` 和 `checks/check_harness_cancel.py`。

模块之间只能经 `context.api(module_id, path, method="GET", body=None)` 调用公开接口。课程资料选择接口属于课程中心，见 [课程中心](../modules/courses/README.md)。框架可在 modules 目录为空时启动设置页；独立启用允许依赖功能暂时不可用，模块自身生命周期必须正常。


## 可选页面提示音

前端可从 `/assets/sounds.js` 导入 `playSound(kind)`；当前支持 `mail`、`deadline`、`announce`、`assistant`。模块只在已确认的新通知或已完成的结果上调用，不以提示音代替可见状态。可选动态导入等待前须登记卸载清理，返回后复核 `context.signal.aborted`，失败不影响正常界面。

应用在用户键盘／指针交互后调用 `unlock()`；未解锁、暂停、浏览器不支持或用户关闭声音时直接跳过，不排队补播。旋律由本地 WebAudio 低音量合成，不请求外部音频，不提供页面关闭后的系统提醒。`setEnabled(bool)`／`isEnabled()` 保留浏览器偏好接口，当前尚无设置页静音或试听按钮。存储被拒绝仍可加载网页；音符结束及关闭声音时释放节点。`checks/check_sounds.mjs` 使用合成音频节点验证，不播放真实音效。
