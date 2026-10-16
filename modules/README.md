此目录中的每个子目录是一项独立业务模块，目录名称与 `module.json` 的 `id` 相同。模块按需加入，在设置中刷新后即可发现、启用或停用。模块开发格式见 [模块接口](../docs/MODULES.md)，目录职责和协作规则见 [团队开发约定](../docs/DEVELOPMENT.md)。

来源模块为 timetable、mail、gradescope、blackboard、piazza、elrc，提供 `/snapshot` 与 `/sync`，维护独立账号版本的缓存。courses 通过公开 HTTP API 聚合来源，assignments、dashboard、assistant、notifications 组合课程目录与共享服务。各模块按职责维护说明、入口和检查。

deadlines 提供原生 Harness 截止时间工具。新增 AI 工具使用独立模块 ID，在 `harness/` 中维护标准 npm 插件包，通过模块管理启停与刷新；调用方使用共享 `context.ai.run` 执行所选插件。纯插件模块以原生入口运行，按实际需要添加页面与 Python API。
