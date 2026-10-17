# PRTS · 学习终端

面向校园学习的明日方舟风格主题。首页将阿米娅值守区、学习功能入口和每日简报放在同一工作台；课程、作业、邮箱、时间表、通知、教务与 AI 页面使用统一的黑白工业面板。设置 → 外观 → **PRTS · 学习终端** 即可启用，选择由主题框架保存在当前浏览器。

## 设计

首页以整幅罗德岛日间甲板承载人物和悬浮面板：左侧展示阿米娅、身份标记、对白及账号与外观入口，右侧按错落的层级组织学习功能。时间表面板展示近期安排、时刻与地点，作业面板展示待完成数量和最近截止，课程面板展示本学期课程与资料数量；邮箱、通知和学习助手组成底部入口。台词“博士，您还有许多事情需要处理。现在还不能休息哦。”是人物对白。下方每日简报提供完整的待办、安排、统计、来源与同步操作。

视觉使用石墨黑、冷灰白与青蓝，橙色标识主要面板，作业的紧急与逾期仍有各自的文字状态。宋体标题、紧凑数字、细边框、角标和大面积留白形成终端层级；列表、正文和表单使用项目原有系统字体。课程颜色、已读状态、同步错误与验证提示沿用业务组件的含义。

学习助手可从首页进入完整对话。空白对话有独立的终端欢迎页，长正文、工具进度、引文、历史会话和输入区仍由原组件提供。内部页面采用平直的列表与阅读面板，日历继续使用完整周视图。375px、平板和横屏使用自适应排列与原有遮罩导航；键盘焦点、44px 触屏目标、减少动态效果设置均保留。

顶部状态栏将通知图标、文字与未读数量排在同一行。通知组件明确使用零内边距，沿状态栏预留区域对齐；新通知摘要从栏下展开。完整聊天仍显示状态栏，手机保留图标与未读数量。

## 接口与目录

遵循 [主题契约 v1](../../../docs/UI_THEME.md)，由 `theme.json` 自动发现。`dashboard.js` 在自有容器中通过 `context.defaultView` 组合原概览，`assistant.js` 组合原对话；`index.js` 提供 `assistant.welcome` 展示区域与主题标记，`terminal.css` 以当前主题限定样式。其余模块直接使用原视图和共享语义颜色。

快捷入口根据当前导航与已挂载模块展示；模块停用后相应入口随页面更新。主题使用公开的主题接口与 `context.defaultView`，业务数据、分类、排序、来源校验和活动确认继续由原模块办理。切页和模块停用时由 `context.signal` 结束组合视图、定时器、请求和样式。

面板摘要镜像同一已挂载概览的展示结果，使用局部 `MutationObserver` 跟随统计、日程与截止刷新。原组件负责账号检查、有效事项筛选和同步；观察器在切页、停用和清理时断开。调整原概览的相关 DOM 时须同步面板选择器与主题浏览器检查。

## 参考与素材

- [明日方舟官方网站](https://ak.hypergryph.com/#index)：品牌的黑白对比、工业图形与人物展示。
- [腾讯游戏学堂 UI/UX 分析](https://gameinstitute.qq.com/article/10027)：浮动面板、前后层次、字体与阅读信息的关系，作为本主题布局的参考。
- [PRTS 界面主题一览](https://prts.wiki/w/%E7%95%8C%E9%9D%A2%E4%B8%BB%E9%A2%98%E4%B8%80%E8%A7%88)：日间主界面的功能层级与人物对白区域。
- [PRTS Design](https://mooncellwiki.github.io/prts-design/)、[xiao-he-he 网页项目](https://github.com/xiao-he-he/xiao-he-he.github.io)、[明日方舟美术资源系统](https://www.ignoredone.space/index.php/arknights_design/)：网页设计与图形资料参考。
- `assets/amiya.png`：阿米娅初始立绘，来自 [ArknightsAssets 的公开素材镜像](https://github.com/ArknightsAssets/ArknightsAssets2/blob/cn/assets/dyn/arts/characters/char_002_amiya/char_002_amiya_1.png)，原始文件直接本地展示。角色、立绘与游戏台词的权利属于鹰角网络及相应权利人；公开镜像不改变原素材授权。
- `assets/rhodes-deck-left.png`、`assets/rhodes-deck-right.png`：来自同一镜像的[日间甲板场景分层](https://github.com/ArknightsAssets/ArknightsAssets2/tree/cn/assets/dyn/arts/ui/homebackground/wrapper/bg_rhodes_day)，属于游戏美术。
- `assets/terminal-mark.svg`：为本学习终端绘制的塔楼书页标记。主题运行时的字体、图形和立绘均从本机加载。

## 验证

在运行中的工作台执行 `node checks/check_arknights_theme.mjs http://127.0.0.1:16666`，可用末尾地址指定其他本地端口。检查使用独立无头 Edge 和合成接口，覆盖首页摘要与刷新、无数据提示、六个入口、通知徽标和展开位置、完整对话与返回、停用助手、重新挂载、主题切换持久化和五种视口，截图与浏览器资料写入项目 `.codex/arknights/`。

内部功能验证复用现有课程工作台、聊天和框架浏览器检查，在 `.codex/` 副本中选择此主题；完整工作区使用 Windows `check.ps1`。合成验证涵盖邮件阅读、偏好与手动分类、课程资料与成绩、通知已读与活动确认、聊天流式输出与历史、时间表、登录设置和资源释放。
