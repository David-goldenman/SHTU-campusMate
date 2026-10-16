此目录中的每个子目录是一项独立业务模块，目录名称与 `module.json` 的 `id` 相同。模块按需加入，在设置中刷新后即可发现、启用或停用。模块开发格式见 [模块接口](../docs/MODULES.md)，目录职责和协作规则见 [团队开发约定](../docs/DEVELOPMENT.md)。

来源模块为 timetable、mail、gradescope、blackboard、piazza、elrc，提供 `/snapshot` 与 `/sync`，维护独立账号版本的缓存。courses 通过公开 HTTP API 聚合来源，assignments、dashboard、assistant、notifications 组合课程目录与共享服务。每个目录包含自己的说明、前后端和离线检查。
