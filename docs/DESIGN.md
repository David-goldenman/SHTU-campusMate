# 界面与模块设计规范

作品对外名称统一为 **campusMate**，用于浏览器标题、侧栏品牌、启动提示和接口文档标题。默认主题的主图标采用 [CampusMate 校园品牌视觉指南](BRAND.md) 中戴学士帽、手持地图的机器人，保留原图的深蓝、蓝紫、薄荷绿与黄色；浏览器图标采用同一素材。产品介绍与宣传使用配套海报，默认界面的组件配色继续遵循 Nord。其他主题保留各自标识与展示语言，PRTS 保留 Personal Learning Terminal。主题名称独立显示在品牌下方。内部包名与健康检查标识继续使用 `campus-framework`，兼容已有启动器与本地数据。

本地工作台使用原生 HTML、CSS 和浏览器 ESM。核心维护导航、模块容器、通用组件与设置；每个业务模块维护自己的界面、事件和资源。前端文件直接由本机服务提供。

## 设计依据与信息层级

默认界面采用 Material 3 的信息组织与交互原则，配色使用 Nord。设计依据包括 [自适应页面结构](https://m3.material.io/foundations/layout/canonical-examples/overview)、[列表](https://m3.material.io/components/lists/guidelines)、[按钮层级](https://m3.material.io/components/buttons/guidelines)、[卡片边界](https://m3.material.io/components/cards/guidelines)、[字体角色](https://m3.material.io/styles/typography/applying-type) 和 [表面色角色](https://m3.material.io/styles/color/the-color-system)。列表与详情按当前任务切换；相关内容通过分区、留白和分隔线归组，卡片承载独立对象。低频操作放入菜单，常用入口提供可见文字。UI/UX Pro Max 的可访问性与桌面密度规则用于核对焦点、目标尺寸、对比度和窄屏行为。

| 使用场景 | 页面组织 | 信息优先级 |
| --- | --- | --- |
| 首页 | 待办与今明日安排；独立聊天区域 | 截止、课程安排先显示，课程统计与同步记录展开查看 |
| 邮箱 | 分类文件夹 + 单行列表，打开邮件后使用主阅读区 | 发件人、主题、摘要、日期；全文与分类依据分开 |
| 通知 | 学习通知／Piazza 分页，通知逐条展开 | 未读点与标题、简短预览；原文和参加操作在详情内 |
| 作业 | 状态筛选 + 时间筛选 + 紧凑作业行 | 课程、题目、截止、提交状态；题干与文件在弹窗内 |
| 账号连接 | 单列服务列表，按服务展开 | 服务名和连接状态；登录方法与设备绑定分层展开 |
| 课程与时间表 | 课程列表／内容、每周网格／事项详情 | 当前课程和日程；平台链接、完整说明按需查看 |

日常内容、系统状态、解释依据与配置操作使用不同层级。正常同步收进“数据状态”；错误、验证要求和来源提示数量保持可见。每页保留一个主标题；模块内容使用自己的上下文操作。通知与邮件的已读／分类是不同概念，不能用多个彩色徽章重复表达同一状态。

## 导航与页面

侧栏分类的顺序由框架统一维护，显示内容随模块开关更新：分类有已启用的界面模块时显示，加载失败的已启用模块保留错误入口，纯后台或 AI 插件在设置中管理。设置始终显示；访问已隐藏的分类时转到第一个可见分类，所有页面模块停用后进入设置。路由使用 URL hash，模块通过 context.navigate(category) 进入分类。

| 分类 | 路由 |
| --- | --- |
| 首页 | #dashboard |
| 邮箱 | #mail |
| 时间表 | #timetable |
| 课程中心 | #courses |
| 作业管理 | #assignments |
| 教务系统 | #eams |
| 通知 | #notifications |
| AI 工具 | #assistant |
| 设置 | #settings |

业务模块在八个业务分类（首页至 AI 工具）中选择挂载位置。分类保留一个页面标题，按照模块清单声明的 stack、tabs 或 primary 布局显示内容。单一主页面的模块标题提供给辅助技术，视觉上由页面主标题标识；加载失败时显示模块名称及错误。版本和健康状态在设置中管理。分类中的可用模块由启用状态、加载状态和前端入口决定，后台模块在设置的模块列表中管理。

设置按“外观、账号连接、网络检测、AI 服务、功能模块、本地设置”分组，使用可键盘切换的标签页。登录和 AI 配置由核心设置统一维护；网络检测显示入口连通性、检测时间、诊断依据和处理建议，将确认的现象与推测原因分开标注。

模型与功能模块使用紧凑设置列表：名称和状态靠左，编辑按钮或开关靠右。桌面按钮高 32px，输入高 40px；触屏操作目标至少 44px。模型配置在原生对话框中编辑，支持 Esc、取消与关闭后清空密钥草稿；模块运行详情按需展开，加载失败和最近请求失败在折叠时仍有文字提示。账号服务使用整行展开，不按不同长度的登录表单并排拉高卡片。

## 主题覆写

Nord 精调作为兼容布局基础：`web/index.html` 引入 `web/themes/nord-refined.css`，HTML 的 `data-ui-theme="nord-refined"` 限定覆写范围。颜色、圆角、间距、导航和卡片外观集中在这个文件；公共组件与模块原有样式继续由对应目录维护。修改外观优先调整主题；调整交互或接口时同步修改所属脚本与检查，避免在主题中隐藏失败状态或业务信息。协作范围与验证步骤见 [UI 主题维护](UI_THEME.md)。

## 视觉基础

配色采用 [Nord 官方调色盘](https://www.nordtheme.com/)。主内容为明亮的 Snow Storm，208px 固定侧栏采用 Polar Night，Frost 用于强调、选中和键盘焦点。

| 用途 | CSS 变量 | 颜色来源 |
| --- | --- | --- |
| 页面背景 | --bg | Nord6 与白色混合 |
| 内容底色 | --paper | 白色 |
| 次级底色 | --surface-low / --surface | Nord6 与白色混合／Nord6 |
| 菜单与弹窗 | --surface-raised | Nord6，配合 --outline 与 --popup-shadow |
| 正文 | --text | Nord0 |
| 辅助文字 | --muted | Nord3 |
| 分隔线／浮层边界 | --border / --outline | Nord4 混合白色／Nord3 |
| 正文链接与主要按钮 | --link | Nord10 与 Nord0 混合 |
| 强调与选中容器 | --accent / --primary-container | Nord8／Nord8 与 Nord6 混合 |

工作区正文为 14px、行高 1.6–1.7，列表标题为 14–15px，辅助信息为 12–13px；页面、分区、对象标题分别约 26、20、16px。邮件与聊天长正文使用 16px、行高 1.85–1.9。字体优先 Microsoft YaHei UI、Microsoft YaHei，并使用各平台可用的系统无衬线字体。文字依靠明确的前景色与背景色对比表达层级，普通文字对比至少 4.5:1，状态同时提供文字。

页面与分区间距为 20–28px，相关行内部使用 8–16px；桌面常规按钮高 36px，输入高 40px，触屏操作目标至少 44px。邮件桌面行约 48px，作业行约 84–110px。截断的摘要可进入详情查看全文；宽表格在自己的区域滚动，页面宽度适应视口。

菜单、输入和弹窗使用稳定的表面色与边界。菜单的底色与白色内容区分开，浮层使用阴影，悬停和键盘焦点清晰可见。操作菜单支持点击外部、选择操作和 Esc 关闭；Esc 返回菜单触发控件。普通内容折叠区继续由用户控制展开状态。

850px 及以下，侧栏改为遮罩导航，主内容使用完整屏幕宽度。导航打开时，背景工作区暂时不可交互，Esc 和遮罩按钮可关闭导航。540px 及以下，双列表单和设置区域改为单列。所有交互控件保留可见的键盘焦点，并遵循系统减少动画偏好。

### 如何修改

框架负责人在 web/styles.css 的 :root 统一调整 --font、基础 font 声明和语义颜色变量，在 h1/h2 规则中调整标题字号。模块引用 var(--text)、var(--link) 和 --nord* 变量，在自己的根容器中调整布局；全局字体和主题由框架集中维护。

| Nord 变量组 | 用途 |
| --- | --- |
| --nord0 至 --nord3 | Polar Night：深色侧栏、正文和辅助文字 |
| --nord4 至 --nord6 | Snow Storm：浅色内容、次级底色与层次 |
| --nord7 至 --nord10 | Frost：强调、选中与焦点 |
| --nord11 至 --nord15 | Aurora：错误、提醒和状态区分 |

Aurora 状态同时提供文字。浅色背景上的链接和按钮优先使用深色语义变量 --link，并核对文字对比。

## 模块入口和生命周期

模块的可选界面入口为 web/index.js。后端返回完整 frontend_url，例如：

    /module-assets/example/REVISION/web/index.js?v=REVISION

核心原样导入该入口。版本包含在路径中，因此相对 JavaScript 导入和样式资源也属于同一版本。模块导出 mount(container, context)，支持异步函数；返回值为 undefined 或 cleanup 函数。cleanup 支持异步函数。

~~~js
export async function mount(container, context) {
  const stylesheet = document.createElement('link');
  stylesheet.rel = 'stylesheet';
  stylesheet.href = new URL('./style.css', import.meta.url);
  document.head.append(stylesheet);

  const heading = document.createElement('h3');
  heading.textContent = context.module.name;
  container.append(heading);

  return () => {
    stylesheet.remove();
    container.replaceChildren();
  };
}
~~~

切页、模块刷新和启停时，核心先中止当前页面的 signal，再等待全部 cleanup 完成，随后挂载下一批模块。入口仍在导入或异步挂载时切页，过期实例不会继续占用当前页面；已经完成的 cleanup 会被执行。一个模块的导入或挂载错误显示在自己的卡片中。

模块把网络请求、事件监听、定时器和样式资源纳入自己的生命周期。事件可使用 addEventListener 的 signal 选项；定时器及样式在 cleanup 中释放。

## 挂载上下文

| 字段 | 用途 |
| --- | --- |
| context.module | 当前模块的元数据副本 |
| context.signal | 当前页面的 AbortSignal |
| context.api(path, options) | 当前模块业务接口 |
| context.ui | 通用界面函数 |
| context.navigate(category) | 进入固定分类 |
| context.services.auth | 共享认证状态 |
| context.services.ai | 共享 AI 服务 |

context.api('/items') 对应 /api/v1/modules/当前模块ID/items。查询参数可以直接放在相对路径中。调用自动附带 X-Framework-Token 和页面 signal；JSON 对象 body 会自动序列化，字符串 body 按原样发送。模块接口路径必须位于自己的命名空间。

~~~js
const items = await context.api('/items');
await context.api('/preferences', {
  method: 'PUT',
  body: { compact: true },
});
~~~

共享服务只暴露固定方法：

| 方法 | 对应核心接口 |
| --- | --- |
| auth.providers() | GET /api/v1/auth/providers |
| auth.status(id) | GET /api/v1/auth/提供方ID/status |
| ai.settings() | GET /api/v1/ai/settings |
| ai.generate(body) | POST /api/v1/ai/generate |
| ai.chat(body) | POST /api/v1/ai/chat |

共享账号、登录验证和 API Key 由设置页办理。模块通过共享状态和服务使用这些能力。

## 通用组件

web/shared.js 由核心维护。模块通过 context.ui 使用组件，通过 context.api 和 context.services 发起请求。

| 函数 | 约定 |
| --- | --- |
| escape(value) | 在模板中把文本转换为 HTML 安全字符串 |
| toast(message) | 显示简短操作结果 |
| dialog(title, content) | 打开原生 dialog；content 为文本或 DOM 节点；返回对话框元素 |
| confirmDialog(title, message, label) | 原生确认框，返回 Promise<boolean> |
| safeAction(control, action) | 绑定操作，管理禁用状态并显示错误 |
| empty(title, description, action) | 生成空状态模板；action 为调用方维护的可信模板 |
| useStyle(url, signal) | 挂载模块样式，在卸载时移除 |
| bindMenus(container, signal) | 为容器内 `details[data-action-menu]` 提供点击外部、操作后和 Esc 关闭；支持动态菜单，监听随 signal 释放 |

dialog 的文本使用 textContent 渲染；需要表单时由调用方构建 DOM 节点。远端文本用 textContent 或 escape 处理。模块遇到需要显示的来源错误时，保留明确的错误状态和操作提示。

CSS 的 .button、.button-primary、.button-secondary、.button-danger、.text-button、.panel、.field-hint 和 .checkbox-label 可用于模块中的通用控件。模块样式作用在自己的根容器内，例如：

~~~html
<section class="panel example-panel">
  <form class="example-form">
    <label>显示名称
      <input name="display_name" autocomplete="off" required>
    </label>
    <p class="field-hint">填写在这个模块中显示的名称。</p>
    <div class="form-actions">
      <button class="button button-primary" type="submit">保存设置</button>
      <button class="button button-secondary" type="reset">重置输入</button>
    </div>
  </form>
</section>
~~~

~~~css
[data-module-id="example"] .example-form {
  display: grid;
  gap: 18px;
  padding: 24px;
}
~~~

~~~css
[data-module-id="example"] .example-list {
  display: grid;
  gap: 16px;
  color: var(--text);
}
~~~

模块的根容器由核心设置 data-module-id。模块自定义选择器使用自己的前缀，页面样式归各自模块维护。修改核心导航、通用组件和视觉变量时，由框架维护者协调调用方。

`/assets/deadlines.js` 提供首页与作业页共用的日期展示：`deadlineInfo(value, now?)` 返回北京时间的日期、时刻、剩余时间与时间紧迫度，`deadlineMarkup(value, escape, {now?, emphasize?})` 使用公共 `.deadline-stamp` 样式生成标记。组件只处理时间展示，不决定事项是否仍需处理；调用方仅对有效待办强调紧急度，已提交等记录使用 `emphasize:false`。未知日期或只提供日期不猜测时刻。日期和剩余时间同时显示，颜色只作为辅助。

## 核心设置

端口使用 /api/v1/settings 保存，下次启动生效。模块刷新使用 POST /api/v1/modules/reload；启停使用 PUT /api/v1/modules/模块ID。设置页面按照服务返回的模块元数据展示状态与错误。

账号配置使用共享认证接口。密码表单一次提交完成保存与登录；已有密码时可留空复用，修改账号则必须输入新密码。提供显示／隐藏密码、卡片内进度和失败提示；操作期间禁用该提供方的控件，其他提供方与表单保持当前输入。登录、浏览器验证、设备绑定及进度轮询只更新对应账号卡片。学校邮箱通过独立登录窗口完成验证。IDS 的目标服务使用服务端返回的 targets 选项。密码和 API Key 输入框在打开设置时为空，保存成功后清空输入内容。

数据清除使用原生对话框确认，随后提交 scope 与 confirmation: "CLEAR"。核心在清除前释放当前模块，完成后重新读取模块列表与设置。credentials、modules、all 的范围由设置界面清楚列出。

## 页面验收

界面变更检查桌面和手机实际页面、键盘焦点、长文本换行和页面横向溢出。模块入口变更检查成功挂载、独立错误显示、切页中止请求与 cleanup。真实密码、登录状态、用户快照和测试临时资料分别由用户数据目录与项目 .codex 管理。

启动本地 demo 并启用时间表后，可在 Windows 运行 `node checks/check_web.mjs http://127.0.0.1:16666`。检查使用独立的无头 Edge 与合成 API，覆盖时间表筛选、导航开关、密码登录与验证、设备进度及表单保留；截图和浏览器目录保存在 `.codex/tmp/`。窗口从网络层阻止真实 API 请求，模拟操作只影响该窗口。


## 日常使用布局

首页提供紧凑的学习助手入口，默认展开待办与截止和今日／明日日程。24 小时内截止、逾期仍可处理及待完成总数可直接跳转筛选；未来截止与历史逾期分区，具体日期、时刻和剩余时间保持醒目，状态同时用文字和颜色表达。课程统计、资料、来源与通知在次级折叠区，个人学习档案按需打开。聊天记录单独滚动，输入区固定在对话底部；工具进度可展开，阅读上文时停止自动跟随，用“回到最新回复”恢复。流式正文通过共享 Markdown 渲染器显示标题、列表、表格、引用和代码块，表格与代码在自身区域内滚动。最终回答合并同一来源的多处引文，保留编号、页码与原文件入口。源码 HTML 保持转义，图片显示描述，链接通过解析器校验。

主动进入对话后收起概览，按视口扩大对话；“查看今日待办”可恢复。重新进入首页默认显示待办，聊天内容和生成状态继续保留。历史面板使用进行中／已归档筛选，当前对话保留选中状态，归档后只读，恢复后继续；删除需要确认。输入草稿随页面内的对话切换保留。

邮箱默认显示分类文件夹与紧凑单行列表，点击邮件后主区域完整显示正文；返回恢复对应邮件行的焦点，加载和失败时也可返回。窄屏顺序阅读。正文保留段落间距、列表、表格和语义格式，分类依据与正文分开；筛选使用有文字及计数的按钮，完整偏好在独立表单编辑，手动分类优先。课程页面先选择本学期课程，再按内容类型切换，已关联平台显示为原站链接。

通知使用有清楚边界的摘要行，未读点和标题粗细表示阅读状态，行尾信封按钮可标记已读／未读。展开后显示完整 Markdown、来源与提醒依据，打开详情不自动标为已读。后台与自动整理配置集中在“整理设置”弹窗。活动建议显示时间、地点、原文依据及参加操作，确认后链接到时间表。常驻通知铃铛位于顶部右侧，保持独立生命周期，新资料提醒可关闭。

主界面突出日期、事项和下一步操作，连接、模块刷新与版本信息集中在设置。模型链接直接进入 `#settings?tab=ai`，设置标签页也可通过 `?tab=accounts/ai/modules/local` 定位。课程中心使用 `navigation.layout:primary` 挂载课程聚合页，各平台作为课程内的资料来源；AI 工具与通知使用 tabs 切换独立子页面。其他分类按清单布局显示，切换执行完整卸载。

周时间表默认展开，每列一天、每行一个时段，四周作业总览按需展开。今天和明天均有文字标记和列底色。课程卡片显示课程名、钟点和地点，课名最多两行，单节课一行；完整名称、院系与课程调整点击查看。每节高 76px，卡片内部不滚动。移动端按日排列。表单保留可见标签、提交状态和就近错误，键盘可操作标签页、日期与事项卡片。

## 开场白

页面顶部展示一条本地中文开场白。桌面首页在学习助手标题下显示；校园概览、设置等页面及窄屏使用全局顶部栏，两处互斥。

文案池和页面内选取逻辑位于 web/opening-lines.js，通用样式位于 web/opening-lines.css。每次打开或刷新页面时重新随机选一句，并避开该标签页上次显示的文案；同一次页面打开期间切页保持稳定。会话存储只记录上次文案，存储不可用时仍可随机显示，但无法排除上次页面的选择。不轮播、不增加请求，也不替代真实状态提示。


## 蓝白艺术主题

首次使用选择 Default · Nord，可在设置的“外观”中选择“观星台”和“星夜手记”，之后保留用户选择。`data-theme` 标识当前主题，艺术主题通过自己的样式和展示区域提供插画与布局。两套艺术主题使用深色文字、浅色阅读区、清楚的焦点和原有状态语义；模块可由主题提供独立视图，功能数据和动作遵循 [主题契约](UI_THEME.md)。

新版首页保留待办首屏；艺术出现在学习助手空白对话的紧凑主图与外观设置预览。首页输入后、已有消息时和低于 520px 的短屏窗口收起主图；正常聊天区没有纹理或人物。两组男女插画仅在外观设置中展示，各主题独立记住男版、女版或隐藏偏好。

共享实现位于 `web/themes/appearance.js`、`appearance.css` 和各主题清单；艺术区域由主题的 `art.js`、`art-welcome.css` 与 `art-workspace.css` 管理。人物选择、主题与减少动效设置保存在当前浏览器，主题切换保存后重新打开当前页面。手动减少动态效果和系统 `prefers-reduced-motion` 都能停止装饰运动。

完整实现、资产来源与验证记录见 ART_THEMES.md。


蓝白主题的校园轮播与侧栏细节仅由 observatory／star-notes 的主题清单加载。页尾只显示图片，默认 20 秒，支持位置开关、手动切换和暂停；离屏、后台、悬停、焦点或减少动态效果时停表。偏好保存在 options[主题ID]，兼容迁移旧版根级字段，不影响 Default、PRTS 和自定义主题。详见 [艺术主题](ART_THEMES.md)。
