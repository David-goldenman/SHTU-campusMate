# 界面与模块设计规范

本地工作台使用原生 HTML、CSS 和浏览器 ESM。核心维护导航、模块容器、通用组件与设置；每个业务模块维护自己的界面、事件和资源。前端文件直接由本机服务提供。

## 导航与页面

侧栏分类的顺序由框架统一维护，显示内容随模块开关更新：分类有已启用的界面模块时显示，加载失败的已启用模块保留错误入口，纯后台或 AI 插件在设置中管理。设置始终显示；访问已隐藏的分类时转到第一个可见分类，所有页面模块停用后进入设置。路由使用 URL hash，模块通过 context.navigate(category) 进入分类。

| 分类 | 路由 |
| --- | --- |
| 总览 | #dashboard |
| 邮箱 | #mail |
| 时间表 | #timetable |
| 课程中心 | #courses |
| 作业管理 | #assignments |
| 教务系统 | #eams |
| 通知 | #notifications |
| AI 工具 | #assistant |
| 设置 | #settings |

业务模块在八个业务分类（总览至 AI 工具）中选择挂载位置。业务分类保留一个页面标题和模块挂载区。同一分类的多个界面模块分别显示在独立卡片中，卡片标题显示功能名称，版本和健康状态在设置中管理。分类中的可用模块由启用状态、加载状态和前端入口决定。后台模块在设置的模块列表中管理。

设置按“账号连接、AI 服务、功能模块、本地设置”分组，使用可键盘切换的标签页。登录和 AI 配置由核心设置统一维护。

## 视觉基础

配色采用 [Nord 官方调色盘](https://www.nordtheme.com/)。主内容为明亮的 Snow Storm，216px 固定侧栏采用 Polar Night，Frost 用于强调、选中和键盘焦点。

| 用途 | CSS 变量 | 默认值 |
| --- | --- | --- |
| 页面背景 | --bg | #eceff4 |
| 内容底色 | --paper | #f7f8fa |
| 次级底色 | --surface | #e5e9f0 |
| 正文 | --text | #2e3440 |
| 辅助文字 | --muted | #4c566a |
| 边框 | --border | #b8c4d4 |
| 正文链接与主要按钮 | --link | #42658e |
| 强调 | --accent | #88c0d0 |

正文默认 16px、行高 1.75，长文本使用 1.85。辅助文字使用 13–14px，主要标题为 28–32px。字体优先 Microsoft YaHei UI、Microsoft YaHei，并使用各平台可用的系统无衬线字体。文字依靠明确的前景色与背景色对比表达层级；状态同时提供文字。

页面与卡片间距通常为 20–28px，控件最小高度为 44px。长标题和路径允许换行。模块内部的宽表格由模块自行提供横向滚动区域，保持整个页面宽度适应视口。

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

## 核心设置

端口使用 /api/v1/settings 保存，下次启动生效。模块刷新使用 POST /api/v1/modules/reload；启停使用 PUT /api/v1/modules/模块ID。设置页面按照服务返回的模块元数据展示状态与错误。

账号配置使用共享认证接口。密码表单一次提交完成保存与登录；已有密码时可留空复用，修改账号则必须输入新密码。提供显示／隐藏密码、卡片内进度和失败提示；操作期间禁用该提供方的控件，其他提供方与表单保持当前输入。登录、浏览器验证、设备绑定及进度轮询只更新对应账号卡片。学校邮箱通过独立登录窗口完成验证。IDS 的目标服务使用服务端返回的 targets 选项。密码和 API Key 输入框在打开设置时为空，保存成功后清空输入内容。

数据清除使用原生对话框确认，随后提交 scope 与 confirmation: "CLEAR"。核心在清除前释放当前模块，完成后重新读取模块列表与设置。credentials、modules、all 的范围由设置界面清楚列出。

## 页面验收

界面变更检查桌面和手机实际页面、键盘焦点、长文本换行和页面横向溢出。模块入口变更检查成功挂载、独立错误显示、切页中止请求与 cleanup。真实密码、登录状态、用户快照和测试临时资料分别由用户数据目录与项目 .codex 管理。

启动本地 demo 并启用时间表后，可在 Windows 运行 `node checks/check_web.mjs http://127.0.0.1:16666`。检查使用独立的无头 Edge 与合成 API，覆盖时间表筛选、导航开关、密码登录与验证、设备进度及表单保留；截图和浏览器目录保存在 `.codex/tmp/`。窗口从网络层阻止真实 API 请求，模拟操作只影响该窗口。


## 日常使用布局

首页先显示课程、待办与资料的简短统计，近期作业与日程可展开；学习助手占主要阅读区域，个人学习档案按需打开。聊天记录单独滚动，输入区固定在对话底部；工具进度可展开，阅读上文时停止自动跟随，用“回到最新回复”恢复。流式正文通过共享 Markdown 渲染器显示标题、列表、表格、引用和代码块，表格与代码在自身区域内滚动。最终回答合并同一来源的多处引文，保留编号、页码与原文件入口。源码 HTML 保持转义，图片显示描述，链接通过解析器校验。

主界面突出日期、事项和下一步操作，连接、模块刷新与版本信息集中在设置。模型链接直接进入 `#settings?tab=ai`，设置标签页也可通过 `?tab=accounts/ai/modules/local` 定位。课程中心与 AI 工具按模块清单声明的 `navigation.layout:tabs` 切换子页面，默认打开 ID 与分类相同的主模块；切换仍执行完整卸载。其他分类按 stack 显示。

周时间表每列一天、每行一个时段，事件用类型文字与 Nord Aurora 色条共同标记。今天和明天均有文字标记和列底色。具体地点跟随单次课程，其他信息点击查看；移动端按日排列。表单保留可见标签、提交状态和就近错误，键盘可操作标签页、日期与事项卡片。
