import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import HTTPException
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
assert not models.preliminary({'title':'活动通知','body_text':'本次活动计入形策考勤。'},{**prefs,'shape':'done'})['protected']
assert models.preliminary({'title':'CS100 作业截止','body_text':''},prefs)['bucket'] == 'focus'
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
    context.auth.revision = 'other-account'
    assert intelligence.preferences()['requirements'] == '' and intelligence.records() == []
    package.stop(context)
print('mail intelligence: literal matching, completion requirements, paragraphs, exact evidence, stale reviews, manual priority and account isolation passed')
