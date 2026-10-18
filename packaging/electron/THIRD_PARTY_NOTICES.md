# CampusMate 第三方资源说明

CampusMate 的校园业务设计与模块协作由 AAA罗德岛工程部完成。Agent 运行时与原生插件机制采用 DeepSeek Harness。所有第三方组件保留原作者的权利与许可，安装包包含对应随包许可证。

## 代码与运行时

- Electron：MIT 及其随附的 Chromium 等第三方声明，见程序目录 LICENSE.electron.txt 和 LICENSES.chromium.html。
- Python：PSF 及其随附声明，见 resources/runtime/python/LICENSE.txt。
- Node.js：MIT 及其随附第三方许可，见 resources/runtime/node/LICENSE。
- pnpm 11.22.0：MIT 及其随附许可，见 resources/runtime/pnpm。
- DeepSeek Harness SDK 0.1.5rc1 与官方运行时：MIT，来源 https://github.com/deepseek-ai/deepseek-harness ，相关运行时依赖继续适用上游各自许可。
- shanghaitech-ids-passkey：MIT，Copyright (c) 2026 vvbbnn00，固定来源提交 7c4df62716ceb3d94452d22f3d07f19ff1b8db8b，来源 https://github.com/vvbbnn00/shanghaitech-ids-passkey 。
- FastAPI、Beautiful Soup、filelock：MIT；Uvicorn、HTTPX、pypdf、zstandard：BSD-3-Clause；cryptography：Apache-2.0 或 BSD-3-Clause；Pillow：MIT-CMU；defusedxml：PSFL；tzdata：Apache-2.0 及底层数据声明；pypdfium2：BSD-3-Clause、Apache-2.0 及 PDFium 底层依赖声明。完整版本见随包 uv.lock，许可证保存在 Python site-packages 的对应 dist-info 目录。
- markdown-it 15.0.3：MIT，原许可位于 resources/backend/web/vendor/markdown-it/LICENSE。
- Font Awesome Free 6.7.2 的 person-running.svg：CC BY 4.0，Copyright Fonticons, Inc.，原许可与署名位于 resources/backend/web/vendor/fontawesome。
- 微信只读适配中的 Cipher 结构与 WCDB 常量片段：改编自 TANGandXUE/wcdb-key-tool，MIT，Copyright (c) 2025 CloudDreamAI / TANGandXUE，原许可位于群消息模块 server/native/WCDB_LICENSE.txt。

## 地图与外部服务

OpenStreetMap 衍生底图与步行路网：© OpenStreetMap contributors，ODbL 1.0，https://www.openstreetmap.org/copyright 。地图保留可见署名，相关数据库与学校建筑资料分别保存。离线坐标转换使用 coordtransform 2.1.2（MIT），https://github.com/wandergis/coordtransform 。

学校官方地图、公开网页及课程平台内容保留原来源与原权利归属。公开可访问不等于开放再分发授权。学校账号、微信、QQ 与模型服务由用户依各自服务要求连接；应用不附带个人账号、模型 Key、聊天记录或课程私有缓存。

## 视觉参考和图像

PRTS 主题参考游戏明日方舟的视觉语言；Hermes Agent 官网 https://hermes-agent.nousresearch.com/ 用于蓝白艺术主题的视觉参考。Nord 配色项目采用 MIT，通用组件组织参照项目记录的 Material 3 规范。

PRTS 中阿米娅立绘、日间甲板场景和人物对白的权利属于鹰角网络及相关权利人。素材下载路径为 ArknightsAssets 公开镜像，具体来源见主题 README；镜像不改变原始素材的授权，现有材料未附专项授权证明。

项目品牌、艺术主图及校园照片的生成式处理按团队提供的设计输入与素材记录完成；原始照片保留供图来源。提示词、来源索引和相关说明保存在 web/brand/ 与 web/themes/assets/。主题代码与第三方美术的权利分别归属。

