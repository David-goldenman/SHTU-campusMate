# 仓库与 demo 更新记录

## 第三版素材基线

第三版使用本地 `main` 的实际前端，在独立服务中按 346.5 秒时间轴录制。采集提交为 `4ef240a` 与 `314be90`，两者界面源码一致；实际源码摘要与提交保存在各段记录中。每段同时记录鼠标运动与点击误差，章节使用 2.4 秒的功能标题过渡。制作规则见 `motion.md`，实际分镜与操作时间见 `storyboard.md`、`screenplay.md`。历史版本仅归档 MP4，由 `player.html` 切换。

### 导出期间的远程更新与取材位置

第三版完成后读取的 `origin/main` 为 `3bffbea`，相对采集基线新增以下内容。第三版画面对应上述采集版本；这些新增交互的取材入口按场景保存，供后续扩充使用。

| 项目功能 | 远程文件 | 对应视频段落 |
| --- | --- | --- |
| 当天行程、正在进行／下一站、相邻安排步行测算及智能标注 | `modules/campus-map/README.md`、`modules/campus-map/web/journey.js`、`modules/campus-map/web/journey-view.js`、`modules/campus-map/web/index.js` | `map`、`mobile` |
| 安排详情中的编辑、删除与地图入口；删除确认 | `modules/timetable/README.md`、`modules/timetable/web/index.js`、`modules/timetable/web/planner.js` | `timetable`、`schedule` |
| 课程与近四周作业分别导出日历 | `modules/timetable/server/ical.py`、`modules/timetable/web/index.js` | `timetable` |
| 首页双语文案扩充 | `web/themes/campus-copy.js` | `hub`、`schedule`、`study`、`advising`、`themes` |

共享 `web/shared.js` 同时更新弹窗节点的创建方式。补录时应在新版本前端上再次检查鼠标所在显示层、弹窗关闭后坐标及模块取景；具体接口以该版本模块文档为准。

## 第二版素材基线

第二版读取另一会话已完成的远程整合，素材基于 `main` 的 `8b7d91413145e783929fc5933afacb1cefe2932b`。该提交的 GitHub `CI required` 已完成且成功，包含近四周课表与作业截止导出到苹果日历，以及微信主实例检测修复。

本版结合当前项目增加校园地图与步行路线、四周截止总览、录播入口与课程筛选、课程群消息整理及原文核对、确认与撤销、邮箱专用密码连接，以及手机响应式日程和地图展示。统一学校登录、模型供应商与模块设置也使用当前界面。产品名称与图标遵循项目 `docs/BRAND.md`。

采集服务在 `http://127.0.0.1:17666` 启动当前项目，数据、运行记录和浏览器资料保存在 `.codex/video/`。业务请求使用独立演示资料重放；对话、日程操作、群消息确认与撤销在演示浏览器中执行。桌面素材为 2760×1350，手机素材为 860×1720，统一输出 1920×1080、60 fps。每段录制保存实际提交与界面源码摘要。主体采集于 `65d07fc`；后续 `8b7d914` 的界面修改限定在群消息模块，该段重新录制。验证器根据片段声明的页面模块、共享界面和常驻组件核对改动，只有相关源码未变化的素材才可复用，原始采集提交继续保留。

第二版分镜为 217 秒。第一版成片保存在 `versions/01-校园工作台.mp4`；后续成片经媒体检查后按顺序归档，`player.html` 可切换版本。分镜、屏幕操作和镜头位置分别保存在 `src/film.json`、`src/operations.json` 和 `src/framing.json`。课程群来源窗口通过 `src/ChatSources.tsx` 还原，虚构消息在 `production/group-chats.json` 统一管理，并与工作台原文引用一致。

## 第一版仓库与 demo 记录

本地 main 与远程 main 为 `a7cb852fe93e10a5e57fdff0b27cf1573b4c8b68`，包含 PR #46「增加可配置的资料识图与本地 OCR」。远程开放 PR 数量为 0。该 main 的 GitHub `CI required` 已成功。

PR #46 在本次检查期间由有写权限的仓库成员 `wEn-EE` 合并，GitHub 记录的时间为 2026-10-18 03:08:37（Asia/Shanghai）。本次也通过 `flowing-wind` 账号检查了 PR 的代码、调用方、边界、文档和合成回归，并提交了审核。审核整合分支的提交为 `6d3158095cdc92bf5fe1c9cf6399115395b8c105`，已推送至原 `codex/document-vision` 分支；其代码树与最终 main 一致。合并操作与本次核验并行发生，最终以 GitHub 的实际合并记录为准。

GitHub 可见的批准记录提交于 03:10:42（Asia/Shanghai），晚于上述合并时间。因此该次合并的记录存在「审核晚于合并」的流程偏差；本记录保留实际时间，最终 main 的 CI 与本地验证结果分别核对。

本地在最终 main 上执行完整 `check.ps1`，结果为：48 项 Python 检查、4 项 JavaScript 检查、Windows 启动器和 63 项 JavaScript 语法检查通过。日志位于 `.codex/video/check-main.log`，退出码为 0。

demo 通过项目现有的保留设置重启脚本更新，地址为 `http://127.0.0.1:16666`。启动后的 bootstrap 返回 17 个模块，校园后台助手恢复原有开启状态。验证和采集使用独立合成数据；用户已有账号、课程与持久结果由原应用继续管理。

根目录 `.gitignore` 增加 `video/`，视频工程保留在本地。Git 跟踪范围中的本次本地修改为这条忽略规则。
