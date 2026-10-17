# PRTS · 学习终端

面向校园学习的明日方舟风格主题。首页将阿米娅值守区、学习功能入口和每日简报放在同一工作台；课程、作业、邮箱、时间表、通知、教务与 AI 页面使用统一的黑白工业面板。设置 → 外观 → **PRTS · 学习终端** 即可启用，选择由主题框架保存在当前浏览器。

## 设计

首页以游戏主界面的层级组织学习入口：时间表为主面板，作业与课程为两个次级面板，邮箱、通知和学习助手组成底部入口。阿米娅立绘叠在罗德岛日间甲板与网格前，使用姓名牌和对白框建立值守感；半透明的指令区让场景与功能面板保持前后关系。台词“博士，您还有许多事情需要处理。现在还不能休息哦。”是人物对白；真实的作业数量、来源状态与截止时间由下方简报展示。

视觉使用石墨黑、冷灰白与青蓝，橙色标识主要面板，作业的紧急与逾期仍有各自的文字状态。宋体标题、紧凑数字、细边框、角标和大面积留白形成终端层级；列表、正文和表单使用项目原有系统字体。课程颜色、已读状态、同步错误与验证提示沿用业务组件的含义。

学习助手可从首页进入完整对话。空白对话有独立的终端欢迎页，长正文、工具进度、引文、历史会话和输入区仍由原组件提供。内部页面采用平直的列表与阅读面板，日历继续使用完整周视图。375px、平板和横屏使用自适应排列与原有遮罩导航；键盘焦点、44px 触屏目标、减少动态效果设置均保留。

## 接口与目录

遵循 [主题契约 v1](../../../docs/UI_THEME.md)，由 `theme.json` 自动发现。`dashboard.js` 在自有容器中通过 `context.defaultView` 组合原概览，`assistant.js` 组合原对话；`index.js` 提供 `assistant.welcome` 展示区域与主题标记，`terminal.css` 以当前主题限定样式。其余模块直接使用原视图和共享语义颜色。

快捷入口根据当前导航与已挂载模块展示；模块停用后相应入口随页面更新。主题使用公开的主题接口与 `context.defaultView`，业务数据、分类、排序、来源校验和活动确认继续由原模块办理。切页和模块停用时由 `context.signal` 结束组合视图、定时器、请求和样式。

## 参考与素材

- [明日方舟官方网站](https://ak.hypergryph.com/#index)：品牌的黑白对比、工业图形与人物展示。
- [腾讯游戏学堂 UI/UX 分析](https://gameinstitute.qq.com/article/10027)：浮动面板、前后层次、字体与阅读信息的关系，作为本主题布局的参考。
- [PRTS 界面主题一览](https://prts.wiki/w/%E7%95%8C%E9%9D%A2%E4%B8%BB%E9%A2%98%E4%B8%80%E8%A7%88)：日间主界面的功能层级与人物对白区域。
- [PRTS Design](https://mooncellwiki.github.io/prts-design/)、[xiao-he-he 网页项目](https://github.com/xiao-he-he/xiao-he-he.github.io)、[明日方舟美术资源系统](https://www.ignoredone.space/index.php/arknights_design/)：网页设计与图形资料参考。
- `assets/amiya.png`：阿米娅初始立绘，来自 [ArknightsAssets 的公开素材镜像](https://github.com/ArknightsAssets/ArknightsAssets2/blob/cn/assets/dyn/arts/characters/char_002_amiya/char_002_amiya_1.png)，原始文件直接本地展示。角色、立绘与游戏台词的权利属于鹰角网络及相应权利人；公开镜像不改变原素材授权。
- `assets/rhodes-deck-left.png`、`assets/rhodes-deck-right.png`：来自同一镜像的[日间甲板场景分层](https://github.com/ArknightsAssets/ArknightsAssets2/tree/cn/assets/dyn/arts/ui/homebackground/wrapper/bg_rhodes_day)，属于游戏美术。
- `assets/terminal-mark.svg`：为本学习终端绘制的塔楼书页标记。主题运行时的字体、图形和立绘均从本机加载。

## 验证

在运行中的工作台执行 `node checks/check_arknights_theme.mjs http://127.0.0.1:16666`，可用末尾地址指定其他本地端口。检查使用独立无头 Edge 和合成接口，覆盖首页信息、六个入口、完整对话与返回、停用助手、重新挂载、主题切换持久化和五种视口，截图与浏览器资料写入项目 `.codex/arknights/`。

内部功能验证复用现有课程工作台、聊天和框架浏览器检查，在 `.codex/` 副本中选择此主题；完整工作区使用 Windows `check.ps1`。合成验证涵盖邮件阅读、偏好与手动分类、课程资料与成绩、通知已读与活动确认、聊天流式输出与历史、时间表、登录设置和资源释放。
