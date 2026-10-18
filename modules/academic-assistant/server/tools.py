import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.services.campus.analysis import account_revision
from backend.services.campus.data import digest
from .documents import extract
from .reader import Reader, cached_json, save_json
from .models import Profile
from .workspace import WorkCommand, Workspace


def profile_owner(context):
    return digest(context.auth.get_account_revision("ids"))


def read_profile(context):
    owner = profile_owner(context)
    saved = context.store.read('academic:' + owner, {})
    academic = {key: saved[key] for key in ('plan_title', 'study_plan', 'updated_at') if key in saved}
    return {"profile": context.store.read("profile:" + owner, Profile().model_dump()), "academic": academic}


class Task:
    def __init__(self, context, message, workspace=None, reader=None):
        self.context, self.message = context, message
        self.owner, self.school_owner = account_revision(context), profile_owner(context)
        self.references, self.activity, self.navigation = {}, [], None
        self.answer = None
        self.schedule_records, self.calendar_requests, self.calendar_results, self.changes = {}, {}, {}, []
        self.work = workspace or Workspace(context)
        self.work_records, self.assignment_records = {}, {}
        self.emit = lambda event: None
        self.reader = reader or Reader(context)
        self.cancel_event = None
        self.finished = False

    def check(self):
        if self.finished or self.cancel_event is not None and self.cancel_event.is_set():
            raise HTTPException(409, '本次资料读取已停止。')
        if account_revision(self.context) != self.owner:
            raise HTTPException(409, "账号已切换，请重新发送问题。")

    async def api(self, module, path="/snapshot"):
        self.check()
        response = await self.context.api(module, path)
        self.check()
        if response.status_code != 200:
            raise HTTPException(409, "请在设置启用并连接 " + module + "，同步资料后重试。")
        return response.json()

    def source(self, source_id, title, text, url="", **fields):
        value = {"source_id": source_id, "title": title, "text": text[:6000], "url": url, **fields}
        self.references[source_id] = value
        return value

    def rows(self, items, body):
        if body.course_id:
            items = [item for item in items if body.course_id in {item.get('id'), item.get('course_id'), item.get('group_id')}]
        if body.q:
            items = [item for item in items if body.q.casefold() in json.dumps(item, ensure_ascii=False).casefold()]
        result = []
        for item in items[body.offset:body.offset + body.limit]:
            text = '\n'.join(key + ': ' + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) for key, value in item.items())
            result.append(self.source(item['id'], item.get('title', item['id']), text, item.get('url', ''), record_id=item['id'], download_url=item.get('download_url'), proposal_id=item.get('proposal_id')))
        return {"items": result, "total": len(items), "offset": body.offset, "next_offset": body.offset + len(result)}

    def academic(self, **values):
        self.check()
        saved = self.context.store.read("academic:" + self.school_owner, {})
        self.context.store.write("academic:" + self.school_owner, {**saved, **values, "updated_at": datetime.now(timezone.utc).isoformat()})

    async def query(self, body):
        area = body.area
        if area == 'profile':
            value = read_profile(self.context)
            academic = value['academic']
            summary = {'profile': value['profile'], 'academic': {key: academic[key] for key in ('plan_title', 'updated_at') if key in academic}}
            return {"items": [self.source('study:profile', '我的学习档案', json.dumps(summary, ensure_ascii=False))]}
        if area == 'assignments':
            value = await self.api('assignments')
            items = value['pending'] if body.pending else value['data']['assignments']
            local = {row['assignment_id']: row for row in self.work.snapshot()['items'] if row['kind'] == 'assignment'}
            items = [{**row, 'local_status': local.get(row['id'], {}).get('status', 'todo'), 'local_revision': local.get(row['id'], {}).get('revision', '')} for row in items]
        elif area == 'workspace':
            value = self.work.snapshot()
            items = value['items']
        elif area == 'courses':
            value = await self.api('courses')
            items = value['data']['courses']
        elif area == 'timetable':
            path = '/schedule' + ('?week_start=' + body.week_start.isoformat() if body.week_start else '')
            value = await self.api('timetable', path)
            classes = [item for day in value['calendar']['days'] for item in day['events'] if item['event_type'] == 'class']
            items = classes + value['data']['events']
        elif area in {'course_history', 'degree_plan'}:
            value = await self.api('eams')
            data = value['data']
            if area == 'course_history':
                items = data['courses']
            else:
                plan = data['metadata'].get('study_plan', {})
                if not plan:
                    raise HTTPException(409, '请先在教务系统同步本专业培养方案。')
                self.academic(plan_title=plan.get('title', ''), study_plan=plan)
                items = [{'id': 'eams:plan:requirements', 'title': plan.get('title', '培养方案要求'), 'requirements': plan.get('requirements', []), 'notes': plan.get('notes', []), 'url': 'https://eams.shanghaitech.edu.cn/eams/myPlan.action'}]
                items += [{'id': 'eams:plan:' + digest([group['path'], course['code']]), **course, 'path': group['path'], 'url': 'https://eams.shanghaitech.edu.cn/eams/myPlan.action'} for group in plan.get('groups', []) for course in group['courses']]
        elif area == 'notifications':
            value = await self.api('notifications')
            items = value['items']
        else:
            value = await self.api('mail')
            items = value['data']['messages']
        result = self.rows(items, body)
        if area == 'assignments' and value.get('summary') is not None:
            sources = value.get('data', {}).get('metadata', {}).get('source_metadata', {})
            summary = {**value['summary'], 'sources': {name: {key: sources[name].get(key) for key in ('status', 'updated_at')}
                       for name in ('blackboard', 'gradescope', 'ecourse') if name in sources}}
            result['summary'] = self.source('study:assignment-summary', '当前账号全部缓存作业统计', json.dumps(summary, ensure_ascii=False))
        visible = {row['record_id'] for row in result['items']}
        if area in {'workspace', 'assignments'}:
            records = self.work_records if area == 'workspace' else self.assignment_records
            records.update({item['id']: dict(item) for item in items if item['id'] in visible})
        if area == 'timetable':
            visible = {row['record_id'] for row in result['items']}
            self.schedule_records.update({item['id']: dict(item) for item in items if item['id'] in visible})
            result.update(week_start=value['calendar']['week_start'], week_one=value['calendar'].get('week_one'),
                          week_one_source=value['calendar'].get('week_one_source'), teaching_week=value['calendar'].get('teaching_week'),
                          periods=value['calendar'].get('periods', []), conflicts=value['calendar'].get('conflicts'))
        return {**result, 'issues': value.get('data', {}).get('issues', []), 'updated_at': value.get('updated_at'), 'status': value.get('status')}

    async def capabilities(self, body):
        self.check()
        response = await self.context.api('timetable', '/capabilities')
        self.check()
        calendar = response.json() if response.status_code == 200 else {'available': False, 'message': '时间表模块未就绪，请在设置启用。'}
        value = {'general': ['知识讲解', '题目分析', '代码与写作辅助', '学习与复习规划'],
                 'workspace': ['本地作业进度（不代表原站提交）', '一次性提醒（运行时检查并发送通知中心）', '学习计划的保存、编辑和完成状态'],
                 'read': ['课程、作业、时间表', '课件、录播和讨论', '邮件和通知', '培养方案和历史修读记录'], 'calendar': calendar,
                 'scope': '写操作作用于本地工作台；学校端报名、请假审批、作业提交与选课仍由原系统办理。'}
        return {'items': [self.source('study:capabilities', '当前助手能力', json.dumps(value, ensure_ascii=False))]}

    def intent(self, quote, verbs):
        if quote.strip() != self.message.strip():
            raise HTTPException(422, '请完整引用本次消息，不得截取局部文字作为授权。')
        uncertain = re.search(r'如果|假如|假设|要是|考虑|是否支持|能否支持|能不能支持|怎么|怎样|如何|会不会|是否应该|什么意思|翻译|转述|原文|他说|她说|只(?:想)?(?:了解|分析|解释|总结)', self.message)
        negative = re.search(r'(?:不要|不用|不必|不需要|不想|不|别|勿|暂不|先不)[^，,。；;\n]{0,12}(?:' + verbs + ')', self.message)
        if uncertain or negative or not re.search(verbs, self.message):
            raise HTTPException(422, '尚无明确的本次修改指令，请先澄清操作。')

    def named(self, record):
        def compact(value):
            return re.sub(r'[\s《》“”「」\"\']+', '', value).casefold()
        return any(len(str(record.get(key, '')).strip()) >= 2 and compact(str(record[key])) in compact(self.message) for key in ('title', 'course_title'))

    async def work_edit(self, body):
        self.check()
        verbs = {'create': '新增|添加|创建|安排|保存|记下|提醒我|设置|制定', 'update': '修改|调整|改到|改为|改成|完成|取消|恢复|标记|推迟',
                 'delete': '删除|移除|清除', 'set_assignment': '标记|完成|做完|开始|进行中|待办|恢复|进度|取消'}
        self.intent(body.quote, verbs[body.action])
        status = body.item.get('status')
        status_words = {'done': '完成|做完', 'in_progress': '开始|进行中|在做', 'cancelled': '取消|不再', 'todo': '待办|未完成|恢复|重新'}
        if status in status_words and not (body.action == 'create' and status == 'todo') and not re.search(status_words[status], self.message):
            raise HTTPException(422, '目标状态与本次消息不一致，请明确要标记的进度。')
        records = self.assignment_records if body.action == 'set_assignment' else self.work_records
        record = records.get(body.record_id)
        if body.action != 'create' and record is None:
            raise HTTPException(422, '修改前请先查询 assignments 或 workspace，并使用本次读取的 ID。')
        deictic = body.action != 'create' and len(records) == 1 and re.search(r'(?:这|该)(?:个|条|份|项)?(?:作业|提醒|计划|事务)', self.message)
        if not self.named(body.item if body.action == 'create' else record) and not deictic:
            raise HTTPException(422, '请在本次消息中明确要操作的作业、提醒或计划名称。')
        signature = 'work:' + json.dumps(body.model_dump(exclude={'quote'}), ensure_ascii=False, sort_keys=True)
        if signature in self.calendar_results:
            return self.calendar_results[signature]
        request_id = self.calendar_requests.setdefault(signature, uuid4().hex)
        payload = WorkCommand(action=body.action, request_id=request_id, account_revision=self.owner, record_id=body.record_id,
                              expected_revision=record.get('local_revision' if body.action == 'set_assignment' else 'revision', '') if record else None, item=body.item)
        value = await self.work.command(payload)
        self.check()
        self.changes.append(value)
        self.emit({'type': 'change', 'change': value})
        result = {'items': [self.source('work-change:' + request_id, '学习事务修改回执', json.dumps(value, ensure_ascii=False))], 'change': value}
        self.calendar_results[signature] = result
        return result

    async def schedule_edit(self, body):
        self.check()
        if body.quote.strip() != self.message.strip():
            raise HTTPException(422, '请完整引用用户本次消息，不得截取局部文字作为操作授权。')
        action = body.adjustment.get('action') if body.action == 'adjust_class' else body.action
        verbs = {'create': '新增|添加|创建|安排|加入|排上|补上', 'update': '修改|调整|改到|改为|改成|改一下|挪到|换到',
                 'delete': '删除|移除|取消', 'leave': '请假', 'cancel': '取消|停课', 'move': '调课|调整|改到|改为|改成|挪到|换到|修改', 'restore': '恢复|撤销'}
        verb = verbs.get(action, r'(?!)')
        message = self.message
        self.intent(body.quote, verb)
        record = self.schedule_records.get(body.record_id)
        if body.action != 'create' and record is None:
            raise HTTPException(422, '修改前请查询时间表，并使用本次实际读取的记录 ID。')
        def compact(value):
            return re.sub(r'[\s《》“”「」"\']+', '', value).casefold()
        target = body.event if body.action == 'create' else record
        anchors = [str(target.get(key, '')).strip() for key in ('title', 'course_title')]
        named = any(len(anchor) >= 2 and compact(anchor) in compact(message) for anchor in anchors)
        unique_reference = body.action != 'create' and len(self.schedule_records) == 1 and re.search(r'(?:这|该)(?:个|场|门|节|次|项)?(?:课|安排|考试|活动|日程|quiz)', message, re.I)
        if not named and not unique_reference:
            raise HTTPException(422, '操作目标不明确，请在本次消息中说明课程或安排的名称。')
        if body.action == 'adjust_class':
            if record.get('event_type') != 'class' or not record.get('lesson_id') or not record.get('original_date'):
                raise HTTPException(422, '请选择教务课程的具体一次上课记录。')
            if body.adjustment.get('scope') == 'following' and not re.search(r'以后|今后|之后|后续|每周|本学期|所有|从.+起', message):
                raise HTTPException(422, '连续调整需要用户明确说明从本次起、后续或每周的范围。')
        elif body.action != 'create' and record.get('source') != 'local':
            raise HTTPException(422, '该来源记录不能直接编辑；教务课程请用课程调整。')
        signature = json.dumps(body.model_dump(exclude={'quote'}), ensure_ascii=False, sort_keys=True)
        if signature in self.calendar_results:
            return self.calendar_results[signature]
        request_id = self.calendar_requests.setdefault(signature, uuid4().hex)
        payload = {'action': body.action, 'account_revision': self.owner, 'request_id': request_id, 'record_id': body.record_id,
                   'expected_revision': record.get('revision', '') if record else None, 'event': body.event}
        if body.action == 'adjust_class':
            payload['adjustment'] = {**body.adjustment, 'lesson_id': record['lesson_id'], 'on_date': record['original_date']}
        elif body.adjustment:
            raise HTTPException(422, '个人安排操作不接受课程调整参数。')
        response = await self.context.api('timetable', '/commands', method='POST', body=payload)
        self.check()
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.json().get('detail', '时间表修改未完成。'))
        value = response.json()
        if not value.get('applied'):
            raise HTTPException(502, '时间表没有返回成功回执，请查询实际结果。')
        self.changes.append(value)
        self.emit({'type': 'change', 'change': value})
        summary = {key: value[key] for key in ('applied', 'action', 'before', 'after', 'affected_count', 'week_start', 'conflicts', 'checked_weeks', 'local_only')}
        result = {'items': [self.source('calendar-change:' + request_id, '时间表修改回执', json.dumps(summary, ensure_ascii=False))], 'change': value}
        self.calendar_results[signature] = result
        return result

    async def attend(self, body):
        self.check()
        # A model-selected excerpt cannot remove the user's negation or condition.
        message = self.message.strip()
        affirmative = r'我(?:决定|想|要|会|打算|确认)?(?:去)?参加|参加这|(?:把|将).{0,60}(?:加入|添加).{0,10}(?:时间表|日程)'
        consents = [part for part in re.split(r'[，,。；;\n]', body.quote) for _ in re.finditer(affirmative, part)]
        uncertain = re.search(r'(?:不|没|未|别|勿)[^，,。；;\n]{0,12}(?:参加|加入|添加|确认|决定)|不要|不用|不必|取消|考虑|如果|假如|假设|要是|的话|是否|能否|怎么|怎样|如何|什么|吗|[?？“”「」"\']', message)
        if body.quote not in self.message or len(consents) != 1 or uncertain:
            raise HTTPException(422, '需要用户本次明确表达参加或加入日程的意愿。')
        proposals = {source['proposal_id'] for source in self.references.values() if source.get('proposal_id')}
        if body.proposal_id not in proposals:
            raise HTTPException(422, '请先查询带有这条活动建议的通知。')
        quoted = re.sub(r'\s+', '', consents[0])
        def matches_target(target):
            # Bind the title to the consent verb, not another mention in the same clause.
            return re.search(r'参加《?' + target + r'》?(?=$|[！!]|并|和|以及)|(?:把|将)《?' + target + r'》?(?:加入|添加)(?:到|至)?(?:我的)?(?:时间表|日程)', quoted)
        named = {source['proposal_id'] for source in self.references.values()
                 if source.get('proposal_id') and source.get('title', '').strip() and matches_target(re.escape(re.sub(r'\s+', '', source['title'])))}
        deictic = matches_target(r'(?:这|该)(?:个|场|项|次)?(?:活动|讲座|报告|会议|安排)')
        if named != {body.proposal_id} and (named or len(proposals) != 1 or not deictic):
            raise HTTPException(422, '请明确说出要参加的活动标题，或在对应通知中点击参加。')
        response = await self.context.api('campus-agent', '/proposals/' + body.proposal_id + '/accept', method='POST')
        self.check()
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.json().get('detail', '日程暂时无法更新。'))
        value = response.json()
        return {'items': [self.source('attendance:' + body.proposal_id, '已加入时间表', json.dumps(value, ensure_ascii=False))]}

    async def search(self, body):
        if body.collection == 'lessons' and body.q:
            params = {'q': body.q, 'semester': 'all', 'limit': min(body.limit, 12)}
            if body.course_id:
                course = (await self.api('courses', '/course?' + urlencode({'course_id': body.course_id})))['course']
                source = next((item for item in course['sources'] if item['source'] == 'elrc'), None)
                if source is None:
                    return {'items': [], 'issues': ['这门课程尚未发现教学社区的转写来源。']}
                params['course_id'] = source['source_id']
            value = await self.api('elrc', '/search?' + urlencode(params))
            return {'items': [self.source(item['source_id'], item.get('lesson_label', '录播原文'), item['text'], item.get('url', ''), start_seconds=item.get('start_seconds'), end_seconds=item.get('end_seconds')) for item in value['items']]}
        params = {'q': body.q, 'offset': body.offset, 'limit': body.limit}
        if body.course_id:
            params['course_id'] = body.course_id
        value = await self.api('courses', '/catalog/' + body.collection + '?' + urlencode(params))
        result = self.rows(value['items'], body.model_copy(update={'q': '', 'course_id': '', 'offset': 0}))
        return {**result, 'total': value['total'], 'offset': body.offset, 'next_offset': body.offset + len(result['items']), 'issues': value.get('issues', [])}

    async def document(self, body):
        value = await self.api('courses')
        data = value['data']
        item = next((item for item in data['materials'] if item['id'] == body.record_id), None)
        if item is None:
            assignment = next((item for item in data['assignments'] if item['id'] == body.record_id), None)
            if assignment is None:
                raise HTTPException(404, '资料不在当前账号的课程缓存中，请先检索课程资料或作业。')
            detail = await self.api('assignments', '/detail?' + urlencode({'assignment_id': assignment['id']}))
            item = next((item for item in detail.get('materials', []) if item.get('download_url')), None)
            if item is None:
                text = detail['assignment'].get('body_text', '')
                if not text:
                    raise HTTPException(404, '该作业当前未提供可读取的题目文件或正文，请在原站确认。')
                return {'kind': 'assignment', 'items': [self.source(assignment['id'] + ':body', assignment['title'], text, assignment.get('url', ''))]}
        source = item['source']
        url = urlsplit(item.get('download_url') or '')
        prefix = '/api/v1/modules/' + source
        if url.scheme or url.netloc or url.path != prefix + '/file' or source not in {'blackboard', 'gradescope'}:
            raise HTTPException(422, '该资料当前没有支持的下载接口，请通过原站查看。')
        revision = data['metadata'].get('source_metadata', {}).get(source, {}).get('updated_at')
        directory = self.context.data_dir / 'documents' / self.owner
        directory.mkdir(parents=True, exist_ok=True)
        identity = digest(['reader-v1', item['id'], item.get('download_url')])
        filename = directory / (identity + '.source')
        metadata = directory / (identity + '.metadata.json')
        saved_metadata = cached_json(metadata)
        if not filename.exists() or not saved_metadata or saved_metadata.get('revision') != revision:
            response = await self.context.api(source, url.path[len(prefix):] + '?' + url.query)
            self.check()
            if response.status_code != 200:
                raise HTTPException(409, '题目文件下载失败，请检查来源连接或在原站确认访问权限。')
            if not response.content or len(response.content) > 30 * 1024 * 1024:
                raise HTTPException(422, '资料应为非空且至多 30 MB 的文件。')
            pending = filename.with_suffix('.download')
            pending.write_bytes(response.content)
            self.check()
            pending.replace(filename)
            for suffix in ('.native.json', '.pages.json'):
                (directory / (identity + suffix)).unlink(missing_ok=True)
            save_json(metadata, {'media_type': response.headers.get('content-type', ''), 'revision': revision}, self.check)
        document = await run_in_threadpool(self.reader.read, filename, directory / (identity + '.native.json'),
                                           directory / (identity + '.pages.json'), body,
                                           media_type=json.loads(metadata.read_text(encoding='utf-8'))['media_type'], title=item['title'], check=self.check)
        self.check()
        latest = await self.api('courses')
        if latest['data']['metadata'].get('source_metadata', {}).get(source, {}).get('updated_at') != revision:
            raise HTTPException(409, '读取期间课程资料已更新，请重新读取当前版本。')
        records = []
        for page in document.pop('pages'):
            for field in ('text', 'description'):
                text = page[field]
                if not text:
                    continue
                position = min((text.casefold().find(term) for term in body.q.casefold().split() if term in text.casefold()), default=0)
                excerpt = text[max(0, position - 500):max(0, position - 500) + 6000]
                identity = item['id'] + ':page:' + str(page['page']) + (':description' if field == 'description' else '')
                records.append(self.source(identity, item['title'], excerpt, item.get('url', ''), page=page['page'],
                    kind=document['kind'], record_id=item['id'], download_url=item['download_url'], read_method=page['method'],
                    evidence_type='model_interpretation' if field == 'description' else 'recognized_text' if page['method'] != 'text' else 'original_text',
                    warnings=page['warnings'], uncertain=page['uncertain']))
            document['warnings'].extend(page['warnings'])
        document['warnings'] = list(dict.fromkeys(document['warnings']))
        return {**document, 'matching_pages': len({row['page'] for row in records}), 'items': records}

    async def course_search(self, body):
        if body.syllabus_id is not None:
            value = await self.api('eams', '/course-info?' + urlencode({'syllabus_id': body.syllabus_id}))
            return {'items': [self.source('eams:syllabus:' + str(body.syllabus_id), value['title'], value['text'], value['url'])], 'scope': 'course_syllabus'}
        if not body.q.strip():
            raise HTTPException(422, '请提供课程名称、课程代码或教学大纲 ID。')
        value = await self.api('eams', '/course-search?' + urlencode({'q': body.q, 'page': body.page}))
        rows = []
        for item in value['items']:
            rows.append(self.source(item['id'], item['title'], json.dumps(item, ensure_ascii=False), item['url'], syllabus_id=item.get('syllabus_id')))
        return {**value, 'items': rows}

    async def remember(self, body):
        values = body.profile.model_dump(exclude_unset=True)
        if body.quote not in self.message or not values:
            raise HTTPException(422, '档案更新需要引用用户本次消息中的原文。')
        for value in values.values():
            text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
            if value is None or not text or text not in body.quote:
                raise HTTPException(422, '仅能记录本次消息中明确提供的专业、年级或学习偏好。')
        if not self.context.auth.get_status('ids')['identity_verified']:
            raise HTTPException(409, '请先连接 IDS，再保存个人学习档案。')
        self.check()
        saved = self.context.store.read('profile:' + self.school_owner, Profile().model_dump())
        saved.update(values)
        self.context.store.write('profile:' + self.school_owner, saved)
        return {'profile': saved, 'source': '用户本次消息'}

    async def navigate(self, body):
        self.navigation = body.category
        return {'category': body.category, 'status': '回答完成后打开该工作台页面'}

    async def finish(self, body):
        citations = []
        for citation in body.citations:
            source = self.references.get(citation.source_id)
            if source is None or not citation.quote.strip():
                raise HTTPException(422, '引用 ID 必须来自本次工具结果，quote 需要实际原文。')
            start, end = None, 0
            for line in citation.quote.splitlines():
                if not line.strip():
                    continue
                match = re.search(r'\s+'.join(re.escape(word) for word in line.split()), source['text'][end:])
                if match is None:
                    raise HTTPException(422, '引用与原文不一致：请从该来源 text 中直接复制一段短句，不改写或调整字段顺序。')
                if start is None:
                    start = end + match.start()
                end += match.end()
            citations.append({**{key: value for key, value in source.items() if key != 'text'}, 'quote': source['text'][start:end]})
        if self.references and not body.insufficient_context and not citations:
            raise HTTPException(422, '请引用本次实际读取的资料，再提交回答。')
        if not any(step['name'] != 'finish' for step in self.activity) and not body.insufficient_context and body.basis != 'general':
            raise HTTPException(422, '请先用学习工具核对本次资料；无需资料时只提出澄清问题，并设置 insufficient_context=true。')
        self.answer = {'text': body.text, 'citations': citations, 'insufficient_context': body.insufficient_context}
        return {'accepted': True, 'citations_count': len(citations)}
