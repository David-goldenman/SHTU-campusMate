# 教务课程表

分类为课程表，使用共享 IDS 的 `timetable` 目标。`GET /snapshot` 返回课程与 `timetable` 活动；`POST /sync` 启动同步。活动包含星期 1–7、起止节次、教学周数组、教师、教室和课程 ID；页面可按教学周筛选。学期、每天节数与周次范围从原站读取。跨年周次遵循 EAMS 活动位串规则。

同步经过共享认证与有界重试，解析缺少学期、课程映射或节次时保留缓存并显示错误。`stop(context)` 取消后续请求并等待同步退出。运行 `bash ./check.sh`，或在项目 uv 环境运行 `python modules/timetable/checks/check_timetable.py`；检查使用合成页面。
