# 模块开发接口

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
  checks/
    check_notes.py
```

`module.json` 的全部字段如下：

```json
{"id":"notes","name":"笔记","version":"0.1.0","category":"courses","api_version":1}
```

`id` 必须与目录名一致，匹配 `[a-z][a-z0-9_-]{0,47}`；`reload` 由框架保留。`category` 可为 `dashboard`、`mail`、`timetable`、`courses`、`assignments`、`notifications` 或 `assistant`。`version` 由模块负责人维护，`api_version:1` 表示当前框架契约。`web/index.js` 与 `server/__init__.py` 至少提供一个。模块可以只提供页面或后端服务；配置能力放在自己的页面或模块 API 内。

## 前端入口

```javascript
export async function mount(container, context) {
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = new URL('./styles.css', import.meta.url);
  document.head.append(style);
  const response = await context.api('/status', {signal: context.signal});
  container.innerHTML = `<p>${context.ui.escape(response.message)}</p>`;
  return () => { style.remove(); };
}
```

`mount` 可以同步或异步，接收一个独立挂载节点，返回可选的清理函数，清理函数也可以异步。模块初始化失败前自行释放已创建的资源。宿主在切页、刷新和停用时先触发 `context.signal`，再等待清理函数完成。

| 上下文属性 | 用法 |
| --- | --- |
| `context.module` | 当前模块的 `ModuleInfo` |
| `context.api(path, options)` | 请求 `/api/v1/modules/<id>` 下的接口，自动 JSON 与本地写请求头 |
| `context.services.auth.providers()` | 列出共享认证配置状态 |
| `context.services.auth.status(id)` | 查询某认证提供方的本地状态 |
| `context.services.ai.settings()` | 读取共享 AI 启用状态 |
| `context.services.ai.generate(body)` | 调用通用文本处理 |
| `context.services.ai.chat(body)` | 调用通用对话 |
| `context.ui` | 公共 UI helper，组件约定见 [设计文档](DESIGN.md) |
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
| `context.store.read(key, default=None)` | 读取本模块非秘密 JSON 状态 |
| `context.store.write(key, value)`、`.delete(key)`、`.clear()` | 管理本模块 SQLite 命名空间 |
| `context.secrets.get(key)`、`.save(key, dict)`、`.delete(key)` | 管理本模块 DPAPI 加密秘密，缺失返回 `{}` |
| `context.data_dir` | 本模块 `.private/modules/<id>/`，存放持久文件 |
| `context.auth` | 共享认证服务，提供已登录 HTTP 客户端 |
| `context.ai` | 共享 AI，提供 `generate`、`chat` 和安全配置状态 |
| `await context.api(module_id, path="/snapshot", method="GET", body=None)` | 调用其他模块公开 HTTP API，返回 `httpx.Response`；停用或未安装返回 404，跨模块写操作按公开接口协作 |

每个模块的状态和秘密按模块 ID 分开。账号、密码、Cookie、Key、token 一律交给共享认证或 `context.secrets`，普通配置与缓存放在自己的 store，文件放在自己的 data_dir。模块通过公开 HTTP API 读取其他模块提供的数据；需要跨模块聚合时由集成人员确定公开请求/响应，调用方不得直接访问对方的数据库、文件或私有代码。

认证用法见 [AUTH.md](AUTH.md)，AI 用法见 [AI.md](AI.md)。模块的接口、数据格式、使用的认证提供方、清理行为和检查命令写入本模块 `README.md`，便于人员交接。

## 热插拔流程

1. 将完整模块目录放入 `modules/`，在设置中选择刷新模块。新发现模块默认启用，启停状态由框架保存。
2. 分类页面挂载该分类中已启用且就绪的前端模块。一个分类可同时挂载多个模块，加载错误单独显示。
3. 更新模块代码后刷新模块。后端先停止并释放，再重新导入；前端获得新的版本地址重新挂载。刷新会释放全部模块，启停一个模块只切换该模块。
4. 停用模块后其后端和静态资源停止服务。已有接口请求需先结束，执行中请求会让热切换返回 409；页面发出的请求用 `context.signal` 取消。
5. 移除模块时先停用，再删除其代码目录并刷新。用户数据按模块 ID 保留；需要清除时在设置中选择模块数据清除，包含已移除模块留下的数据。

后台任务、定时器和长连接由模块自己的 `stop` 释放。模块必须使用框架的生命周期钩子启动和结束这些活动；数据库连接由宿主在停止后关闭。热更新以模块为单位，Python 公共依赖或主框架的改动使用服务重启。

模块属于受信任本地代码，运行权限与框架一致。目录分层和注入上下文用于团队分工与状态隔离；安装模块前审核其代码及外部访问行为。

## 校园数据模块

公共 `backend.services.campus` 提供 `Source` 同步生命周期、`Remote` 来源请求、课程与时间规范化。来源模块公开 `GET /snapshot` 和 `POST /sync`（202），快照为 `{status,data,updated_at,message?}`。`data` 包含 `courses/assignments/materials/announcements/posts/lessons/timetable/messages` 八个数组、`metadata` 范围对象和 `issues` 提示数组；标识带来源前缀，未知提交状态保持 `null`。全局请求失败保留上次成功快照；来源可在 `issues` 标明局部读取失败。日期带时区，页面以 Asia/Shanghai 展示。

来源读取最多重试一次超时、网络中断、429 与 5xx；分页限制 100 页并检查重复链接和目标域名。共享认证的 `account_revision` 在更新账号、导入会话或忘记登录时变化；缓存按该版本隔离。模块停止时取消后续读取并等待当前工作线程结束，再由宿主关闭 Store。`check.sh` 自动运行每个模块 `checks/check_*.py`。

`backend.services.campus.files.download` 在一次认证上下文内获取文件，逐跳校验 HTTPS 目标与端口，将内容暂存 `.codex/tmp/<module_id>/`，通过 FileResponse 交付后删除。模块提供固定的服务域名列表与按需解析文件链接的函数，临时签名地址留在后端。

模块可定义 `authorize_write(context, request) -> bool` 接受自己的专用 Bearer 令牌。宿主仍先校验 Host、Origin 与跨站请求；钩子必须精确限制路径和令牌。正常网页写请求使用框架 CSRF。邮件模块仅为专用 Agent 写标签接口启用此能力，密钥由该模块 `context.secrets` 保存。

模块启停与刷新按生命周期串行执行，停止钩子运行时释放注册表读取锁，允许后台任务完成已有的跨模块调用。开始停止前先关闭对应路由入口；正在执行的请求仍按原契约返回 409。
