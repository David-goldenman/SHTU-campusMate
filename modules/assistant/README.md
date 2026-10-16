# 校园 AI 助手

使用共享 AI 服务与课程中心公开 API。`GET /context?course_id=...` 查看当前可用资料；默认本学期课程与校园邮件，指定课程时排除其他课程及校园邮件。资料最多 400 条、上下文最多 85000 字符，每项正文最多 1800 字符，返回 included、total、truncated 和 text_available。文件资料提供标题、描述与下载入口，按当前缓存文字参与分析。

`POST /generate {task,prompt,course_id?,context_ids?}` 支持 summarize、classify、report，分类仅返回建议。`POST /chat {message,course_id?,context_ids?}` 保存连续对话；GET/DELETE 同一路径按 course_id 读取或清除历史。context_ids 省略使用该范围，空数组表示不发送资料。空范围直接说明资料不足。模型引用必须属于实际选择，引用 URL 从缓存生成，格式错误或越界引用返回 502 并保留已有历史。

每个范围最多保留 60 条消息，最近 6 条各最多 1500 字符参与后续请求。历史按共享账号版本隔离，账号变更期间生成的结果不落盘。共享 AI 配置、密钥与外部请求仍由框架维护。项目 `check.sh` 使用合成模型结果验证引用、历史、空选择与账号变化。
