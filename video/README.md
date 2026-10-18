# campusMate · 校园工作台

Remotion 产品介绍视频，1920×1080、60 fps，时长约 5 分 47 秒。默认 Nord 主线，中文屏幕文案与指定背景音乐，展示实际前端操作、重点运镜、AI 协作、手机网页与团队制作名单。章节之间以 2.4 秒的线条、功能标题和界面展开衔接，关键结果保留稳定阅读时间。

[观看最新成片](output/校园工作台.mp4) · [播放器与历史版本切换](player.html) · [分镜预览](output/分镜预览.jpg)。历史 MP4 按制作顺序保存在 `versions/`；`versions/index.json` 记录编号、文件名和校验值。

## 修改入口

| 内容 | 文件 |
| --- | --- |
| 大纲、章节、时长、文案、品牌、团队及成员顺序 | `src/film.json` |
| 操作、输入、点击、滚动、聚焦与回到全景的时间 | `src/operations.json` |
| 实际 DOM 测得的取景区域 | `src/framing.json`，录制时生成 |
| Remotion 编排、过场、镜头、手机与团队版式 | `src/Film.tsx`、`src/film.css` |
| 微信 / QQ 来源窗口还原及虚构群聊 | `src/ChatSources.tsx`、`production/group-chats.json` |
| 复习与选课的示例对话 | `production/dialogues.json` |
| 真实通知、作业、已存日程对话及来源 | `production/source-data.json`、`production/sources.md` |
| PDF 页码核验与通用培养方案 | `production/material-evidence.json`、`production/curriculum.json` |
| 演示接口、群消息与新增能力 | `scripts/replay-fixture.mjs`、`scripts/features.mjs` |
| 浏览器操作、录制、编码 | `scripts/replay.mjs`、`scripts/record.mjs`、`scripts/encode.mjs` |
| 大纲、完整脚本及制作步骤 | `production/storyboard.md`、`production/screenplay.md`、`production/workflow.md` |
| 章节过渡、阅读停留与鼠标运动规则 | `production/motion.md` |
| 成片归档和播放器版本列表 | `scripts/archive.mjs` |
| 素材及成片验证 | `scripts/check.mjs`、`scripts/verify.mjs` |

## 运行

使用 Windows Node、Edge 和 FFmpeg。依赖、浏览器资料、源帧、隔离服务和其他中间数据均在项目 `.codex/video/`；`video/node_modules` 是对应依赖目录的 junction。首次安装从项目根目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File video/scripts/setup.ps1`，随后在 `video/` 执行：

```powershell
npm run studio
npm run check
npm run stills
npm run render
npm run verify
```

Studio 地址为 `http://localhost:17680`。录制器使用 17666 端口的隔离 demo，该服务运行实际项目前端，使用 `.codex/video/demo-data/` 空数据目录；启动脚本为 `.codex/video/demo.py`。需要更新真实通知来源时，单独使用取材脚本读取个人 demo 已有缓存。

只改包装、片尾或标题时可直接检查并渲染。修改分镜时长后先执行 `npm run music` 更新配乐选段，具体衔接点保存在 `scripts/music.mjs`。修改操作、回答、数据或相关产品界面后，先重新录制受影响片段：

```powershell
node scripts/record.mjs mail timetable map groups mobile settings
npm run check
npm run stills
npm run render
npm run verify
```

录制器读取模块和主题元数据，业务请求全部由隔离浏览器中的演示接口处理，未知接口立即报错。桌面源素材为 2760×1350，手机源素材为 860×1720，均为 60 fps。取景从真实 DOM 测量，时间轴驱动缩放与高亮；地图使用实际路网计算的路线几何。源码指纹在每段前后核对，最终检查会拒绝相关界面源码已变化的素材。`src/operations.json` 的 `modules` 声明片段访问的页面模块；共享界面和常驻组件同时参与核对。改变片段访问的页面时，一并更新这项声明。后台和主分支更新后重新启动隔离服务。

渲染前自动保留当前成片，验证通过后归档新成片；同一内容不会重复编号。`player.html` 的下拉框可以直接选择历史版本，无需覆盖最新文件。整个 `video/` 由根目录 `.gitignore` 忽略。

真实资料、演示状态与验证范围见 `production/brief.md` 和 `production/validation.md`。课程群与日程操作只写演示内存；手机为响应式网页视口录制，实机及会场设备另行验收。

第三版的界面采集基线及导出期间的远程功能更新见 `production/integration.md`，可按其中的场景索引继续扩充素材。

