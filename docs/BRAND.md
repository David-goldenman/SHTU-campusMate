# CampusMate 主品牌与宣传素材

主品牌以用户提供的《CampusMate校园品牌视觉指南.png》为准：友好的学士帽机器人、校园地图、蓝紫色定位标记，以及深蓝、蓝紫、浅蓝、薄荷绿和黄色配色。原图保存在项目内，后续设计可直接以它为参照。

| 素材 | 用途 | 尺寸 |
| --- | --- | --- |
| [主应用图标](../web/brand/campusmate-app-icon.png) | 默认主题侧栏、初始页面、浏览器图标及主屏幕图标 | 1254 × 1254，PNG，保留透明圆角 |
| [宣传海报](../web/brand/campusmate-promo.png) | 项目介绍、演示材料与宣传图片 | 1254 × 1254，PNG |
| [原始品牌视觉指南](../web/brand/campusmate-visual-guide.png) | 字标、图形与配色参照 | 1536 × 1024，PNG，原文件直接复制 |

主应用图标从指南右侧的应用图标整理而来；宣传海报按左侧主画面制作，保留 CampusMate 字标、英文标语和五项功能说明。两项独立素材使用内置 image_gen 按原图生成，并非对原图像素的无损裁切；[生成提示词](../web/brand/prompts.json) 随素材保存。原始指南不作改写，仍是视觉依据。

产品文字名称沿用当前的 `campusMate`，图中文字保留原设计的 `CampusMate`。标语为 “This page graduated without telling anyone.”。宣传图中的 Courses、Timetable、Campus Info、Deadlines、Ask Anything 分别对应课程、时间表、校园信息、截止提醒和问答。使用时按比例缩放，保留字标与功能说明的可读性，不把指南中的标注文字当成应用界面。

## 接入与主题边界

- `web/index.html` 和 Default 主题入口使用同一主应用图标；README 展示宣传海报。页面分享元数据指向配套宣传图。
- 观星台、星夜手记与 PRTS 等主题继续使用各自的 `icon` / `favicon` 约定，不覆盖它们的图片、布局、调色板和展示语言。
- 主品牌素材集中放在 `web/brand/`，与主题自己的资源分开。默认界面的组件色彩仍遵循 Nord，品牌图中的颜色不替换功能状态色。
- 本地工作台的分享元数据使用相对资源路径，不对外发布服务。需要用于公开网站时，再由发布方配置公开域名与可访问的宣传图地址。

运行 `node checks/check_appearance.mjs` 可核对默认主题主标识及其他主题独立标识；完整项目检查仍使用 `check.ps1` / `check.sh`。
