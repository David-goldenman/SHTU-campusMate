import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.services.campus.analysis import account_revision
from backend.services.campus.data import digest
from .documents import extract
from .models import Profile


def profile_owner(context):
    return digest(context.auth.get_status("ids")["account_revision"])


def read_profile(context):
    owner = profile_owner(context)
    return {"profile": context.store.read("profile:" + owner, Profile().model_dump()), "academic": context.store.read("academic:" + owner, {})}


class Task:
    def __init__(self, context, message):
        self.context, self.message = context, message
        self.owner, self.school_owner = account_revision(context), profile_owner(context)
        self.references, self.activity, self.navigation = {}, [], None
        self.answer = None

    def check(self):
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
            result.append(self.source(item['id'], item.get('title', item['id']), text, item.get('url', ''), record_id=item['id'], download_url=item.get('download_url')))
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
            summary = {'profile': value['profile'], 'academic': {key: academic[key] for key in ('gpa', 'plan_title', 'updated_at') if key in academic}, 'courses_count': len(academic.get('courses', []))}
            return {"items": [self.source('study:profile', '我的学习档案', json.dumps(summary, ensure_ascii=False))]}
        if area == 'assignments':
            value = await self.api('assignments')
            items = value['pending'] if body.pending else value['data']['assignments']
        elif area == 'courses':
            value = await self.api('courses')
            items = value['data']['courses']
        elif area == 'timetable':
            value = await self.api('timetable', '/schedule')
            items = value['data']['timetable'] + value['data']['events']
        elif area in {'grades', 'degree_plan'}:
            value = await self.api('eams')
            data = value['data']
            if area == 'grades':
                items = data['courses']
                self.academic(courses=items, gpa=data['metadata'].get('gpa', {}))
                items = [{'id': 'eams:gpa', 'title': '历史成绩与绩点汇总', 'gpa': data['metadata'].get('gpa', {}), 'url': 'https://eams.shanghaitech.edu.cn/eams/teach/grade/course/person!historyCourseGrade.action?projectType=MAJOR'}, *items]
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
        return {**self.rows(items, body), 'issues': value.get('data', {}).get('issues', []), 'updated_at': value.get('updated_at'), 'status': value.get('status')}

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
        filename = directory / (digest([item['id'], item.get('download_url'), revision]) + '.json')
        if filename.exists():
            document = json.loads(filename.read_text(encoding='utf-8'))
        else:
            response = await self.context.api(source, url.path[len(prefix):] + '?' + url.query)
            self.check()
            if response.status_code != 200:
                raise HTTPException(409, '题目文件下载失败，请检查来源连接或在原站确认访问权限。')
            document = await run_in_threadpool(extract, response.content, response.headers.get('content-type', ''), item['title'])
            self.check()
            filename.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        pages = [(index + 1, text) for index, text in enumerate(document['pages']) if index + 1 >= body.page]
        if body.q:
            terms = body.q.casefold().split()
            pages = sorted(((page, text) for page, text in pages if any(term in text.casefold() for term in terms)), key=lambda row: (-sum(row[1].casefold().count(term) for term in terms), row[0]))
        records = []
        for page, text in pages[:body.limit]:
            if not text:
                continue
            position = min((text.casefold().find(term) for term in body.q.casefold().split() if term in text.casefold()), default=0)
            excerpt = text[max(0, position - 500):max(0, position - 500) + 6000]
            records.append(self.source(item['id'] + ':page:' + str(page), item['title'], excerpt, item.get('url', ''), page=page, kind=document['kind'], record_id=item['id'], download_url=item['download_url']))
        return {'kind': document['kind'], 'pages_total': len(document['pages']), 'matching_pages': len(pages), 'items': records}

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
        if not any(step['name'] != 'finish' for step in self.activity) and not body.insufficient_context:
            raise HTTPException(422, '请先用学习工具核对本次资料；无需资料时只提出澄清问题，并设置 insufficient_context=true。')
        self.answer = {'text': body.text, 'citations': citations, 'insufficient_context': body.insufficient_context}
        return {'accepted': True, 'citations_count': len(citations)}
