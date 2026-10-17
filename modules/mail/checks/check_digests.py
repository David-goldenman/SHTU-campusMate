"""Local folders, Beijing day/week ranges and summaries use synthetic mail only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.services.campus.data import validate_bundle
from checks.module_support import load, sandbox

package = load('mail')
reader = sys.modules[package.__name__ + '.reader']
body = reader.presentation('<p align="right" style="font-weight:bold;font-size:18pt;color:red;background:url(https://tracker.example)">段落</p><font color="red">提醒</font>')
assert all(value in body['body_html'] for value in ('mail-align-right','mail-bold','mail-font-large','mail-important'))
assert 'style=' not in body['body_html'] and 'tracker.example' not in body['body_html']

with sandbox('mail') as context:
    app = FastAPI()
    app.include_router(package.create_router(context))
    source = package._source
    messages = [{'id':'mail:'+str(index),'source':'mail','source_id':str(index),'title':'合成通知 '+str(index),
                 'sender':'合成发件人','received_at':value,'unread':index % 2 == 0,'url':'https://example.edu/mail','body_text':''}
                for index, value in enumerate(['2026-10-17T00:10:00+08:00','2026-10-16T16:30:00Z',
                                               '2026-10-12T09:00:00+08:00','2026-10-11T09:00:00+08:00',None])]
    context.store.write('snapshot',{'owner':source.owner(),'data':validate_bundle({'messages':messages,'metadata':{'total':200,'limit':100}}),'updated_at':None})
    try:
        with TestClient(app) as client:
            folders = client.get('/folders').json()
            assert folders['folders'][0]['count'] == 5 and folders['folders'][1]['count'] == 3
            day = client.get('/digests?period=day&anchor=2026-10-17').json()
            assert len(day['entries']) == 2 and day['coverage']['inbox_total'] == 200
            week = client.get('/digests?period=week&anchor=2026-10-17').json()
            assert week['start'] == '2026-10-12' and week['end'] == '2026-10-18' and len(week['entries']) == 3
            assert client.get('/digests?period=month').status_code == 422
            assert client.get('/digests?anchor=not-a-date').status_code == 422
            assert client.post('/digests',json={'anchor':'2020-01-01'}).status_code == 400
            context.ai.result = {'content':{'overview':'本期校园通知。','highlights':[{'message_id':'mail:0','summary':'查看通知原文。'}]},'model':'synthetic'}
            report = client.post('/digests',json={'period':'day','anchor':'2026-10-17'})
            assert report.status_code == 200 and report.json()['report']['model'] == 'synthetic'
            assert client.get('/digests?anchor=2026-10-17').json()['report']
            context.ai.result['content']['highlights'][0]['message_id'] = 'mail:outside'
            assert client.post('/digests',json={'anchor':'2026-10-17'}).status_code == 502
            client.post('/labels',json={'message_id':'mail:0','label':'手动重点','bucket':'focus'})
            assert client.get('/digests?anchor=2026-10-17').json()['report'] is None
            context.auth.revision = 'another-account'
            isolated = client.get('/digests?anchor=2026-10-17').json()
            assert isolated['entries'] == [] and isolated['report'] is None
    finally:
        package.stop(context)
print('PASS: semantic mail formatting, smart folders, Beijing period boundaries, summary citations, invalidation and account separation')
