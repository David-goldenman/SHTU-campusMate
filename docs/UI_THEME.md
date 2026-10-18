# UI 主题维护与协作

## 主题契约 v1

设置 → 外观提供 `default`（当前 Nord 界面）、`observatory`（观星台）和 `star-notes`（星夜手记）。首次使用选择 `default`；之后按当前浏览器的 `campus.appearance.v1` 保存用户选择，服务重启和页面刷新继续使用。切换主题保存后重新打开当前页面，以统一卸载页面、后台组件与样式。原有艺术主题及人物偏好继续读取；主题暂时缺失时显示 Default，并保留原选择供重新安装后恢复。

`GET /api/v1/themes` 自动发现 `web/themes/<id>/theme.json`，返回 `{api_version:1,default:"default",items,errors}`。添加主题只需提交自己的目录和清单；清单错误单独列出，其他主题继续使用。资源路径相对清单目录解析，必须指向 `web/themes/` 内的本地文件。

```json
{
  "id": "sample",
  "name": "示例主题",
  "description": "面向阅读的布局",
  "api_version": 1,
  "styles": ["styles.css"],
  "preview": "preview.webp",
  "entry": "index.js",
  "views": {"mail": "mail.js"},
  "backgrounds": {}
}
```

只有 `id` 和 `name` 必填，`id` 与目录一致；当前接口版本为 1。`styles` 是有顺序的 CSS 列表；`preview` 是设置页预览。`entry` 可导出 `renderSlot(name, props)`，返回展示用 HTML；未实现的区域返回 `undefined`，使用模块原界面。各模块声明可替换区域，当前学习助手区域见下表。主题可导出 `icon` 和 `themeColor(id)` 设置标记与浏览器颜色。

开场白默认隐藏。主题入口可主动导出 `export const openingLines = true`，启用顶部及聊天区原有短句；只有布尔值 `true` 生效。HTML 初始使用 `data-opening-lines="hidden"`，加载主题后由框架根据实际入口导出设置为 `enabled` 或 `hidden`，避免主题初始化时闪字。未导出此选项的 Default、PRTS、自定义及未来主题保持隐藏；主题缺失或加载失败回退时使用回退主题的选择。此选项属于入口导出，不增加清单字段。启用后沿用原桌面、聚焦及窄屏位置规则，不会同时强制显示两处短句。

| 插槽与参数 | 展示范围 |
| --- | --- |
| `assistant.welcome` | 进入对话后的空记录欢迎区 |
| `assistant.home({presets})` | 首页紧凑欢迎区，接收模块提供的常用问题列表 |
| `assistant.footer({topic})` | 聊天输入区下方的中英双语短句；未实现时使用空字符串作为 fallback |

插槽仍由学习助手模块声明并决定出现的场景，主题只负责展示。`topic` 为 `general / grades / deadlines / timetable / documents`，由模块在本机根据用户明确输入的文字分类；不从真实成绩或后台数据猜测话题。主题未实现的区域使用调用方指定的 fallback，不能替换模块的业务判断。

`views` 以模块 ID 指定完整界面入口，`settings` 代表全局设置。`backgrounds` 用于常驻组件。入口统一导出 `mount(container, context)`，与原模块共用 API、模块启停及账号版本；只有可用模块才会加载对应视图。未指定的页面使用原界面。主题可以改变信息布局、组件结构、字体、色彩和交互组织，通用 UI helper 作为可选工具使用。

| 注入接口 | 使用方式 |
| --- | --- |
| `context.api(path, options)` | 当前模块的公开业务 API；设置视图使用框架 API。请求自动带框架令牌与卸载信号 |
| `context.services.auth / ai` | 文档化的共享认证状态和 AI 接口，凭据保留在共享服务 |
| `context.ui` | `escape`、`dialog`、`toast`、`safeAction`、`useStyle`、`bindMenus` 等公共组件；详见 [模块接口](MODULES.md) |
| `context.navigate(category)` | 使用现有导航分类和路由 |
| `context.focus(active)` | 请求内容区使用完整工作区 |
| `context.defaultView(container)` | 挂载当前模块原界面，返回其清理函数，适合组合原有功能 |
| `context.theme.id / list() / select(id)` | 当前主题、安装清单、保存并切换主题 |
| `context.theme.preferences() / savePreferences(value)` | 读取副本、保存当前主题专属的展示偏好 |
| `context.theme.renderSlot(name, props, fallback)` | 模块声明的可替换展示区域 |
| `context.signal` | 切页、模块停用或刷新时结束组件资源 |

业务信息的定义、查询、分类、通知决策和写入校验由模块公开 API 负责。主题决定如何显示这些信息、如何安排用户操作；主题对同一动作使用相同请求和确认含义。例如活动加入仍调用参加接口，主题不能把默认选中等同于用户同意。数据缺失、验证要求、失败及部分结果需要保持可识别，使用已有接口字段表达。

组件在首次 `await` 前注册 signal 清理，使用 `context.ui.useStyle(url, context.signal)` 管理自己的样式。`mount` 可返回清理函数；组合 `defaultView` 时将其清理函数返回或纳入自身清理。监听、定时器、请求和后台显示随卸载结束。动态文字使用 `context.ui.escape` 或 `textContent`；主题本身是本地受信任代码，CSS 建议按 `html[data-theme="sample"]` 限定，组件内部类名由主题自行组织。

新主题 PR 保留其原有视觉设计，在自身目录实现这些接口，复用业务后端。评审核对功能操作、账号切换、已停用模块、重新打开后的选择、键盘焦点与窄屏显示；布局可以充分变化。修改接口时同步本文件、调用方和检查，不把业务规则复制到主题中。

## 样式与交互分工

Nord 精调主题位于 `web/themes/nord-refined.css`，由 `web/index.html` 的样式链接和 `data-ui-theme="nord-refined"` 启用。语义颜色、字体角色、间距、控件密度和浮层层次集中维护；公共组件基础样式位于 `web/styles.css`。模块通过 `context.ui.useStyle` 管理自己的布局与清理，业务状态与数据通过现有 API 取得。设计依据与页面组织见 [设计规范](DESIGN.md)。

| 位置 | 负责内容 |
| --- | --- |
| `web/app.js` | 分类布局、页面焦点、跳至主内容、模块启停与清理 |
| `web/shared.js` | 通用对话框、提示、操作状态、样式与菜单生命周期 |
| `web/campus.js` | 来源状态折叠区、同步入口、记录摘要及公共展示 |
| `web/settings.js` | 账号单列展开、登录方式、设备绑定与设置草稿 |
| `modules/dashboard/web/` | 截止与今明日日程、统计与来源折叠区 |
| `modules/academic-assistant/web/` | 聊天阅读区、明确的历史入口、输入与会话操作 |
| `modules/mail/web/` | 分类文件夹、紧凑列表、完整阅读区与日／周总结 |
| `modules/notifications/web/` | 通知摘要、已读操作、活动确认与整理设置 |
| `modules/assignments/web/` | 状态／时间筛选、作业行、排序与详情弹窗 |
| `modules/courses/web/`、`modules/timetable/web/` | 课程内容与每周日程，长内容进入详情 |
| `modules/campus-agent/web/` | 顶部通知入口、提醒及资源清理 |

## 视觉规则

以下为 Default 的视觉规则。主题可以替换布局和组件形态，同时保留可访问操作、必要状态及相同业务含义。必要滚动区域提供细圆角滚动条，课程卡片和来源说明通过完整页面或详情组织。鼠标滚轮、键盘与触屏滚动保持可用；实现依据 [MDN 滚动条说明](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/::-webkit-scrollbar)，高对比度模式使用系统颜色。

页面背景、白色内容区、次级分区和浮层分别使用 `--bg`、`--paper`、`--surface-low/--surface`、`--surface-raised`。浮层使用 `--outline` 与 `--popup-shadow` 保持清楚的边界。文字、链接与选中容器使用 `--text`、`--muted`、`--link`、`--primary-container`，状态使用 Nord Aurora 并提供文字。普通文字对比至少 4.5:1，选中、悬停与键盘焦点分别核对。

工作区正文 14px，长正文 16px；辅助信息 12–13px。桌面常规按钮高 36px，模型与模块设置按钮高 32px；触屏目标至少 44px。页面间距 24–28px，分区间距 20–24px，同一条目内部 8–16px。密度随内容类型调整，列表、正文、日历与表单各自有阅读结构。

每页保留一个主标题。常用入口使用可见文字，例如“历史对话”和“新对话”；次要操作进入菜单。同步正常时只显示状态入口，来源异常显示文字及提示数量；完整依据、时间和网络诊断保留在折叠区。详情中的返回、取消与关闭位置保持一致，关闭后把焦点交还相关入口。

操作菜单使用原生 `details[data-action-menu]`，调用 `context.ui.bindMenus(container, context.signal)`。监听支持动态生成的菜单，点击外部或选择操作时关闭，Esc 关闭并聚焦 summary。正文折叠区使用普通 details，由用户控制；表单弹窗使用现有原生 dialog。监听、定时器与样式都随模块 signal 释放。

## 页面与窄屏

首页顶部显示学习助手入口，下方默认展示待办与截止、今明日安排。进入、新建或选择对话后调用 `context.focus(true)`，输入区保留在对话底部。“历史对话”打开搜索与进行中／归档列表；窄屏保留文字入口，标题和操作分行，抽屉通过遮罩与暂时不可交互的对话区分开，点击遮罩或 Esc 可返回。顶部通知铃铛与对话操作留出空间。

邮箱以文件夹和列表作为默认视图，点开后主区域用于正文；桌面邮件一行显示发件人、主题、摘要、分类与日期。较窄屏幕优先保留发件人、主题和日期，分类仍可通过文件夹筛选。正文、分类摘要和原文依据分区显示；加载或失败时也能返回。

通知摘要有明确的逐条边界，展开后查看完整内容和参加操作。已读是单独操作，打开详情保留当前阅读状态。作业使用状态与时间筛选，行内保留截止、提交状态和原站入口，题干与下载在详情弹窗。排序同时支持拖动、键盘和上下移按钮。

每周时间表默认可见，四周作业总览展开查看。课程卡片使用简短信息、有限行数和详情入口；单节课程保留最小可读高度。宽表格在自己的容器滚动。850px 以下沿用遮罩导航；375px 与横屏下页面不横向溢出。

## 调整与同步

团队更新后检查模块结构与主题选择器，并保留最新功能。模块分类通过清单声明，同一分类的导航定义保持一致；通知使用 tabs，课程中心使用 primary。数据 API、持久化及账号隔离由相应服务和模块维护。

移除 HTML 的 `data-ui-theme` 属性可对照基础外观。修改 DOM 或公共 UI helper 时同步更新调用方、模块说明及合成界面检查；主题不得遮住失败状态或必需操作。

## 验证

启动本机 demo 后运行：

```powershell
node.exe checks/check_web.mjs http://127.0.0.1:16666
node.exe checks/check_ui_theme.mjs http://127.0.0.1:16666
node.exe checks/check_campus_workspace.mjs http://127.0.0.1:16666
node.exe modules/academic-assistant/checks/check_web.mjs http://127.0.0.1:16666
```

四项浏览器检查覆盖登录与设备验证、设置草稿、首页待办与筛选、作业排序及详情、长课程与单节课、通知已读及活动确认、邮件阅读与分类、菜单关闭和焦点返回、聊天历史与 Markdown 流式输出。检查使用隔离浏览器与合成响应，截图写入项目开发目录。实际缓存页面另检查桌面、窄屏与控制台；账户外部连接和付费模型验证按用户授权单独办理。

公共框架和业务回归使用 `check.ps1` 或 `check.sh`。界面进入集成评审前核对当前提交、最新主线、接口说明及实际变更。
