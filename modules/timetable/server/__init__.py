import asyncio
from datetime import date, datetime
from pydantic import Field, model_validator

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from backend.services.campus import Source, semester, timestamp
from backend.services.campus.assignments import filter_issues, historical
from backend.services.campus.data import digest
from backend.services.campus.analysis import account_revision
from backend.services.campus.source import snapshots
from .reader import fetch
from .calendar import Event, MISSING_WEEK_ONE, SemesterSettings, ZONE, calendar
from .commands import Command, adjustments_key, event_record, execute
from .homework import homework_window, overview_weeks
from .ical import COURSE_FILENAME, HOMEWORK_FILENAME, build_course_calendar, build_homework_calendar
from .school_calendar import SchoolCalendar, term_key

SCHEDULE_SOURCES = {"blackboard": "Blackboard", "gradescope": "Gradescope", "ecourse": "E 云课堂", "eams": "教务系统"}
_source = None
_calendar = None


class ImportedEvent(Event):
    origin_id: str = Field(min_length=1, max_length=300)
    account_revision: str = Field(min_length=1, max_length=100)


class UpdatedEvent(Event):
    @model_validator(mode='before')
    @classmethod
    def ignore_saved_metadata(cls, value):
        # Existing clients PUT the full GET record; these fields are server-owned.
        return {key: item for key, item in value.items() if key not in {'id', 'source', 'revision', 'at', 'origin_id', 'start_time'}} if isinstance(value, dict) else value


def create_router(context):
    global _source, _calendar

    def read_schedule(remote, previous):
        def term_starts():
            year = datetime.now(ZONE).year
            return {key: value for start in (year - 1, year)
                    for key, value in context.store.read('school-calendar:' + str(start), {}).get('terms', {}).items()}

        data = fetch(remote, previous, term_starts=term_starts())
        if school.due(data['metadata']):
            try:
                school.refresh(data['metadata'])
            except HTTPException:
                pass  # A calendar failure leaves course synchronization usable.
            else:
                # The first successful calendar read may refine a month-based
                # fallback around the start of spring or summer teaching.
                starts = term_starts()
                today = datetime.now(ZONE).date()
                begun = {key: value['week_one'] for key, value in starts.items()
                         if value.get('week_one') and value['week_one'] <= today.isoformat()}
                if begun and max(begun, key=begun.get) != term_key(data['metadata']):
                    data = fetch(remote, previous, term_starts=starts)
        return data

    source = _source = Source(context, "ids", ["eams.shanghaitech.edu.cn"], read_schedule, target="timetable", network_target="timetable")
    school = _calendar = SchoolCalendar(context, source)
    router = source.router()

    def settings_key():
        metadata = source.snapshot()['data']['metadata']
        return 'semester:' + source.owner() + ':' + metadata.get('semester_id', metadata.get('semester', ''))

    def local_events():
        return context.store.read('events:' + source.owner(), [])

    @router.get('/calendar-settings')
    def settings():
        metadata = source.snapshot()['data']['metadata']
        official = school.saved(metadata)
        automatic = official.get('terms', {}).get(term_key(metadata), {})
        manual = context.store.read(settings_key(), {})
        week_one = manual.get('week_one') or automatic.get('week_one')
        origin = 'manual' if manual.get('week_one') else 'school' if automatic.get('week_one') else None
        return {**automatic, **manual, 'week_one': week_one, 'source': origin,
                'url': official.get('url'), 'pdf_url': official.get('pdf_url'), 'checked_at': official.get('checked_at'), 'error': official.get('error')}

    @router.put('/calendar-settings')
    def save_settings(body: SemesterSettings):
        context.store.write(settings_key(), body.model_dump(mode='json'))
        return settings()

    @router.delete('/calendar-settings')
    def restore_settings():
        context.store.delete(settings_key())
        return settings()

    @router.post('/calendar/refresh')
    async def refresh_calendar():
        await run_in_threadpool(school.refresh, source.snapshot()['data']['metadata'])
        return settings()

    @router.get('/calendar/image')
    def calendar_image(page: int = 1):
        if not 1 <= page <= 4:
            raise HTTPException(422, '校历图片页码应为 1 至 4。')
        path = school.image(source.snapshot()['data']['metadata'], page)
        return FileResponse(path, media_type='image/png')

    @router.get('/events')
    def events():
        return {'items': local_events()}

    @router.get('/capabilities')
    def capabilities():
        return {'available': True, 'event_types': Event.model_json_schema()['properties']['event_type']['enum'],
                'actions': ['create', 'update', 'delete', 'leave', 'cancel', 'move', 'restore'], 'scopes': ['once', 'following'],
                'timing': ['带时区的钟点', '日期与起止节次'], 'conflicts': '检查同节次及已知时间段重叠，缺少钟点时明确提示', 'local_only': True}

    @router.post('/events', status_code=201)
    def add_event(body: Event):
        item = event_record(body)
        with source.lock:
            context.store.write('events:' + source.owner(), [*local_events(), item])
        return item

    @router.post('/events/import')
    def import_event(body: ImportedEvent):
        identity = 'local:import:' + digest(body.origin_id)
        with source.lock:
            owner = source.owner()
            key = 'events:' + owner
            if body.account_revision != account_revision(context):
                raise HTTPException(409, '账号已更新，请重新确认安排。')
            items = context.store.read(key, [])
            existing = next((item for item in items if item['id'] == identity), None)
            if existing:
                return {**existing, 'existing': True}
            item = {**event_record(body, identity), 'origin_id': body.origin_id}
            item.pop('account_revision', None)
            if owner != source.owner():
                raise HTTPException(409, '账号已更新，请重新确认安排。')
            context.store.write(key, [*items, item])
        return item

    @router.put('/events/{event_id}')
    def update_event(event_id: str, body: UpdatedEvent):
        with source.lock:
            owner = source.owner()
            items = context.store.read('events:' + owner, [])
            item = next((item for item in items if item['id'] == event_id), None)
            if item is None:
                raise HTTPException(404, '未找到这条安排。')
            item.update(**event_record(body, item['id']))
            if body.event_type != 'exam' or not body.starts_at:
                item.pop('start_time', None)
            context.store.write('events:' + owner, items)
        return item

    @router.delete('/events/{event_id}')
    def delete_event(event_id: str):
        with source.lock:
            owner = source.owner()
            items = context.store.read('events:' + owner, [])
            if not any(item['id'] == event_id for item in items):
                raise HTTPException(404, '未找到这条安排。')
            context.store.write('events:' + owner, [item for item in items if item['id'] != event_id])
        return {'deleted': True}

    @router.post('/commands')
    async def command(body: Command):
        combined = await schedule()
        return execute(context, source, settings, body, combined['data'])

    @router.get('/changes')
    def changes():
        return {'items': [item['result'] for item in context.store.read('calendar-commands:' + source.owner(), [])][-50:]}

    @router.get("/schedule")
    async def schedule(week_start: date | None = None):
        owner = account_revision(context)
        values, unavailable = await snapshots(context, SCHEDULE_SOURCES)
        appearance_response = await context.api("courses", "/appearance")
        appearance = appearance_response.json() if appearance_response.status_code == 200 else {}
        course_styles = {member: item for item in appearance.get("courses", []) for member in item["course_ids"]}
        values = {"timetable": source.snapshot(), **values}
        metadata = values["timetable"]["data"]["metadata"]
        dates = settings()
        current = semester(metadata.get("semester"))
        events, issues = local_events(), []
        if not dates['week_one'] and values['timetable']['data']['timetable']:
            issues.append(MISSING_WEEK_ONE)
        for item in dates.get('closures', []):
            events.append({'id': 'calendar:' + item['date'], 'title': item['title'], 'source': 'calendar', 'event_type': 'calendar',
                           'at': item['date'] + 'T00:00:00+08:00', 'date': item['date'], 'all_day': True, 'url': dates.get('url')})
        if dates.get('error'):
            issues.append(dates['error'])
        for name, value in values.items():
            data = value["data"]
            label = SCHEDULE_SOURCES.get(name, "教务课表")
            visible = filter_issues(data["issues"], data["assignments"], data["courses"], current, dates["week_one"])
            issues.extend(label + "：" + str(issue) for issue in visible)
            if value.get("message"):
                issues.append(label + "：" + value["message"])
            courses = {item["id"]: item for item in data["courses"]}
            for item in data["assignments"]:
                course = courses.get(item.get("course_id"), {})
                if historical(item, course, current, dates["week_one"]):
                    continue
                at = timestamp(item.get("due_at"))
                if not at:
                    continue
                events.append({**item, "at": at, "event_type": "exam" if name == "eams" else "deadline", "course_title": course.get("title", "")})
        if unavailable:
            issues.append("以下来源未启用或暂时不可用：" + "、".join(SCHEDULE_SOURCES[name] for name in unavailable))
        events.sort(key=lambda item: (datetime.fromisoformat(item.get('at') or item['date'] + 'T00:00:00+08:00').timestamp(), item.get('period_start') or 0, item['id']))
        syncing = any(value.get("status") == "syncing" for value in values.values())
        updated = max((value["updated_at"] for value in values.values() if value.get("updated_at")), default=None)
        if owner != account_revision(context):
            raise HTTPException(409, "账号已切换，请重新读取时间表。")
        data = {**values['timetable']['data'], 'events': events, 'issues': issues}
        data['timetable'] = [{**item, **{key: course_styles[item['course_id']][key] for key in ('department', 'appearance')}}
                             if item.get('course_id') in course_styles else item for item in data['timetable']]
        adjustments = context.store.read(adjustments_key(source), [])
        missing = {item['lesson_id'] for item in adjustments} - {item['id'] for item in data['timetable']}
        if missing:
            issues.append(str(len(missing)) + ' 项课程调整暂时无法匹配最新教务课表，原调整记录仍保留。')
        plan = calendar(data, week_start or datetime.now(ZONE).date(), dates['week_one'], adjustments)
        reminders = homework_window(values, start=dates['week_one'])
        return {"status": "syncing" if syncing else "partial" if issues and updated else "ready" if updated else "not_connected",
                "network_failures": [value["network_failure"] for value in values.values() if value.get("network_failure")],
                "updated_at": updated, "data": data, 'account_revision': owner, 'adjustments': adjustments,
                'calendar': {**plan, 'week_one_source': dates['source']}, 'school_calendar': school.view(metadata),
                'homework': reminders, 'palette': appearance.get('palette', []),
                'overview': overview_weeks(data, reminders, dates['week_one'], adjustments),
                "sources": {name: {"status": value.get("status"), "updated_at": value.get("updated_at")} for name, value in values.items()}}

    def calendar_response(content, filename):
        return Response(content, media_type='text/calendar; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="' + filename + '"',
                                 'Cache-Control': 'no-store'})

    @router.get('/calendar/export/homework.ics')
    async def export_homework_calendar():
        return calendar_response(build_homework_calendar(await schedule()), HOMEWORK_FILENAME)

    @router.get('/calendar/export/courses.ics')
    async def export_course_calendar():
        return calendar_response(build_course_calendar(await schedule()), COURSE_FILENAME)

    @router.post("/schedule/sync", status_code=202)
    async def sync_schedule():
        own = source.sync()
        results = await asyncio.gather(*(context.api(name, "/sync", method="POST") for name in SCHEDULE_SOURCES))
        return {"sources": {"timetable": own, **{name: result.json() if result.status_code == 202 else {"status": "unavailable"} for name, result in zip(SCHEDULE_SOURCES, results)}}}

    return router


def start(context):
    metadata = _source.snapshot()['data']['metadata']
    if term_key(metadata) and context.auth.get_status('ids')['identity_verified'] and _calendar.due(metadata):
        def update():
            try:
                _calendar.refresh(metadata)
            except HTTPException:
                pass
        pending = _source.executor.submit(update)
        if getattr(context, 'runtime', None):
            context.runtime.watch('校历更新', pending)


def stop(context):
    if _source is not None:
        _source.close()
