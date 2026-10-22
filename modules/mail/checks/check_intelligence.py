import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import HTTPException
import httpx
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('mail')
models = sys.modules[package.__name__ + '.intelligence']
reader = sys.modules[package.__name__ + '.reader']
assert models.contains('IC', 'IC design') and not models.contains('IC','Scientific academic economic')
assert '<p>第一段<br/>下一行</p><p>第二段</p>' == reader.presentation('第一段\n下一行\n\n第二段')['body_html']
prefs = models.Preferences(shape='required', courses=['CS100']).model_dump()
assert models.preliminary({'title':'政治思想讲座','body_text':'欢迎参加'},prefs)['topic'] != 'shape'
assert models.preliminary({'title':'活动通知','body_text':'本次活动计入形策考勤。'},prefs)['protected']
for body in ('本次活动不计入形策考勤。', '本次活动无法计入形策考勤。', '是否计入形策考勤尚待确认。',
             '本次活动拟计入形策考勤。', '本次活动计入形策考勤的说法不实。', '本次活动计入形策考勤？',
             '本次活动计入形策考勤。更正：本次活动不计入形策考勤。', '形策考勤活动介绍。'):
    assert not models.preliminary({'title':'活动通知','body_text':body},prefs)['protected'], body
assert not models.preliminary({'title':'本次活动计入形策考勤','body_text':'认定情况请等待后续通知。'},prefs)['protected'], 'The title alone is not recognition evidence'
for body in ('本次活动可计入形策考勤。', '本次讲座纳入《形势与政策》课程学时。'):
    assert models.preliminary({'title':'活动通知','body_text':body},prefs)['protected'], body
for body in ('本次讲座计入形策考勤，不需要提前报名。', '不需要提前报名，本次讲座计入形策考勤。',
             '本次讲座计入形策考勤，请勿迟到。'):
    result = models.preliminary({'title':'讲座通知','body_text':body}, {**prefs, 'interests': {'research':'hide'}})
    assert result['protected'] and result['bucket'] == 'focus' and result['topic'] == 'shape', body
for body in ('如果完成签到，本次讲座计入形策考勤。', '本次讲座计入形策考勤，尚待确认。',
             '本次讲座计入形策考勤，尚需确认。', '本次讲座计入形策考勤，也许。',
             '本次讲座计入形策考勤，最终以教务通知为准。', '本次讲座计入形策考勤，但该说法不实。',
             '不需要提前报名，本次讲座不计入形策考勤。'):
    assert not models.preliminary({'title':'讲座通知','body_text':body},prefs)['protected'], body
assert not models.preliminary({'title':'活动通知','body_text':'本次活动计入形策考勤。'},{**prefs,'shape':'done'})['protected']
assert models.preliminary({'title':'CS100 作业截止','body_text':''},prefs)['bucket'] == 'focus'
for year in (1, 2):
    value = models.Preferences(year=year).model_dump()
    assert models.preliminary({'title':'形策活动','body_text':'本次活动计入形策考勤。'},value)['bucket'] == 'focus'
    assert models.preliminary({'title':'形策活动','body_text':'本次活动计入形策考勤。'},{**value,'shape':'done'})['bucket'] == 'digest'
assert models.preliminary({'title':'大一心理健康活动','body_text':''},models.Preferences(year=1).model_dump())['bucket'] == 'focus'
assert models.preliminary({'title':'心理活动通知','body_text':''},models.Preferences(year=2).model_dump())['bucket'] == 'digest'
for title in ('CS100 作业发布', 'CS100 实验材料已上传', 'CS100 预习课件'):
    assert models.preliminary({'title':title,'body_text':''},prefs)['bucket'] == 'focus', title
with sandbox('mail') as context:
    package.create_router(context)
    source, intelligence = package._source, package._intelligence
    item = {'id':'mail:sample','title':'合成讲座','source':'mail','source_id':'sample','body_text':'2030年10月18日 14:00 开始讲座，地点：教学楼。','received_at':'2030-10-16T09:00:00+08:00','sender':'合成发件人','url':'https://example.edu'}
    context.store.write('snapshot',{'owner':source.owner(),'data':validate_bundle({'messages':[item]}),'updated_at':None})
    prepared = intelligence.prepared(item['id'])
    decision = dict(bucket='recommend', topic='research',category='科研讲座',summary='合成摘要',reason='原文说明',evidence=[{'source':'title','quote':item['title']}])
    submit = lambda value, fingerprint=prepared['fingerprint']: intelligence.submit(models.Submission(message_id=item['id'],fingerprint=fingerprint,decision=value))
    saved = submit(decision)
    assert intelligence.records()[0]['classification']['by'] == 'agent'
    try:
        submit({**decision,'evidence':[{'source':'body_text','quote':'并不存在的原文'}]})
        raise AssertionError('Fabricated evidence')
    except HTTPException as error:
        assert error.status_code == 422
    context.store.write('labels',{'owner':source.owner(),'value':{item['id']:{'label':'我的分类','bucket':'focus','by':'manual'}}})
    assert intelligence.records()[0]['classification']['category'] == '我的分类'
    context.store.write(intelligence.key('preferences'),models.Preferences(requirements='完整保留用户的自然语言筛选要求').model_dump())
    try:
        submit(decision)
        raise AssertionError('Stale preference result')
    except HTTPException as error:
        assert error.status_code == 409
    async def study_api(module, path='/snapshot', **kwargs):
        if module == 'academic-assistant':
            now = datetime.now(models.ZoneInfo('Asia/Shanghai'))
            return httpx.Response(200,json={'profile':{'major':'合成专业','cohort_year':now.year - (now.month < 9)}})
        return httpx.Response(200,json={'items':[{'title':'信号与系统','code':'EE100'}]})
    context.api = study_api
    asyncio.run(intelligence.refresh_context())
    effective = intelligence.effective_preferences()
    assert effective['year'] == 1 and effective['major'] == '合成专业' and '信号与系统' in effective['courses']
    assert intelligence.preferences()['year'] is None and intelligence.preferences()['courses'] == [], 'Linked context must not overwrite manual preferences'
    assert models.preliminary({'title':'信号与系统实验材料发布','body_text':''},effective)['bucket'] == 'focus'
    batch = [item, *[{**item, 'id': f'mail:batch-{index}', 'source_id': f'batch-{index}', 'title': f'CS100 作业通知 {index}'} for index in range(99)]]
    context.store.write('snapshot', {'owner': source.owner(), 'data': validate_bundle({'messages': batch}), 'updated_at': None})
    expected = {row['id']: intelligence.prepared(row['id']) for row in batch}
    with patch.object(source, 'snapshot', wraps=source.snapshot) as snapshots, \
         patch.object(intelligence, 'effective_preferences', wraps=intelligence.effective_preferences) as preferences, \
         patch.object(context.ai, 'settings', wraps=context.ai.settings) as settings:
        records = intelligence.records()
        assert snapshots.call_count == preferences.call_count == settings.call_count == 1, 'A mailbox batch must read shared inputs once, not once per message'
    for row in records:
        assert row['classification']['input_revision'] == expected[row['id']]['fingerprint']
        if row['id'] != item['id']:
            assert row['classification'] == {**expected[row['id']]['preliminary'], 'input_revision': expected[row['id']]['fingerprint'], 'review_pending': True, 'event_window': None}
    assert records[0]['classification']['category'] == '我的分类', 'Batching must preserve manual priority'
    with patch.object(context.ai, 'settings', return_value={'provider': 'openai', 'model': 'changed', 'base_url': 'https://example.test'}):
        assert all(row['classification']['input_revision'] != expected[row['id']]['fingerprint'] for row in intelligence.records()), 'New batches must use current AI settings'
    def change_account():
        context.auth.revision = 'changed-during-batch'
        return {'model': 'synthetic'}
    with patch.object(context.ai, 'settings', side_effect=change_account):
        try:
            intelligence.records()
            raise AssertionError('An account change during a batch must reject its result')
        except HTTPException as error:
            assert error.status_code == 409
    context.auth.revision = 'other-account'
    assert intelligence.effective_preferences()['courses'] == [], 'Linked study context is account-scoped'
    assert intelligence.preferences()['requirements'] == '' and intelligence.records() == []
    package.stop(context)
print('mail intelligence: literal matching, completion requirements, paragraphs, exact evidence, stale reviews, manual priority and account isolation passed')
