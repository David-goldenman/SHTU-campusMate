# Windows 已有环境启动器

默认双击 `run.cmd` 使用 `run.ps1`，由 uv 准备项目运行环境并打开工作台。已有 Python 3.12+ 环境且依赖齐全的用户，也可使用 `run-local.ps1` 启动后台服务。两种方式共用 `.private/` 中的账号、设置和模块数据，运行前应停止当前实例。

```powershell
.\run-local.ps1 --python 'C:\path\to\python.exe' --check
.\run-local.ps1 --python 'C:\path\to\python.exe' --port 16666
.\run-local.ps1 --python 'C:\path\to\python.exe' --no-browser
.\run-local.ps1 --python 'C:\path\to\python.exe' --stop
```

启动器按顺序读取 `--python`、环境变量 `CAMPUS_PYTHON`、根目录 `python-path.txt`、项目已有的 `.private/runtime/windows/venv/Scripts/python.exe` 与 PATH 中的 `python.exe`。配置文件只写一行解释器完整路径，已加入 Git 忽略规则。设置 `CAMPUS_PYTHON` 或创建 `python-path.txt` 后，双击 `run.cmd` 即使用已有环境启动器；移除相应选择后，双击入口继续使用 uv。

已有环境启动器检查 `pyproject.toml` 声明的依赖、版本与固定 Git 依赖来源，由用户在选定环境中准备依赖。运行时不会安装软件，也不修改系统执行策略。Windows 时区数据由 `tzdata` 提供。

服务就绪后在系统浏览器打开本地地址；关闭网页后后台继续运行。双击 `stop.cmd` 可停止该启动器在本目录创建的服务，也可使用上面的 `--stop`。停止前核对进程创建时间和程序位置，通过实例停止信号正常退出；端口被其他程序占用时报告错误。`run.ps1` 启动的实例仍在其启动窗口中按 Ctrl+C 停止。

后台进程记录与停止信号保存在 `.private/runtime/launcher/`，日志在 `.private/runtime/logs/`，临时文件在 `.private/runtime/tmp/`。这些目录由程序创建并被 Git 忽略。开发检查使用独立合成目录，完整检查入口继续使用 `check.ps1` / `check.sh`。

Windows 与 WSL 启动器在 `.private/runtime/cache/python/` 保存框架和启动依赖的 Python 字节码，后续启动复用缓存；首次生成缓存仍需解析源码。业务模块加载前继续关闭字节码写入，确保同一秒内修改模块代码后刷新也能生效。缓存不写入源码目录，不包含账号或业务数据。

PDF 文字解析和校历图片渲染引擎在首次读取或更新对应资料时加载，打开工作台无需等待这些文档组件。

界面设计、主题和业务 API 继续遵循 [设计规范](DESIGN.md)、[主题契约](UI_THEME.md) 和 [模块接口](MODULES.md)。
