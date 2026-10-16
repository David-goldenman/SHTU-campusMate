import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from checks.campus_fixtures import PDF, fixture_app

PROJECT = Path(__file__).resolve().parents[1]


async def check(directory):
    app = fixture_app(directory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:18666') as client:
            bootstrap = (await client.get('/api/v1/bootstrap')).json()
            assert len(bootstrap['modules']) == 11 and all(item['status'] == 'ready' for item in bootstrap['modules'])
            client.headers['X-Framework-Token'] = bootstrap['csrf_token']
            for module in bootstrap['modules']:
                assert (await client.get(module['frontend_url'])).status_code == 200
                assert (await client.get('/api/v1/modules/' + module['id'] + '/openapi.json')).status_code == 200
            assert (await client.get('/api/v1/modules/notifications/snapshot')).json()['items'] == []
            courses = (await client.get('/api/v1/modules/courses/snapshot')).json()
            assert len(courses['data']['courses']) == 1 and len(courses['data']['courses'][0]['sources']) == 5
            assert len((await client.get('/api/v1/modules/assignments/snapshot')).json()['pending']) == 2
            assert (await client.get('/api/v1/modules/dashboard/snapshot')).json()['stats']['courses'] == 1
            body = await client.get('/api/v1/modules/mail/message',params={'message_id':'mail:m1'})
            assert body.status_code == 200 and '<script' not in body.text and 'tracking.example' not in body.text
            assert (await client.post('/api/v1/modules/mail/classify')).status_code == 200
            assert (await client.post('/api/v1/modules/mail/labels',json={'message_id':'mail:m1','label':'我的分类'})).status_code == 200
            assert (await client.post('/api/v1/modules/mail/ai-classify',json={'message_ids':['mail:m1','mail:m2']})).status_code == 200
            assert (await client.get('/api/v1/modules/mail/labels')).json()['labels']['mail:m1']['by'] == 'manual'
            token = (await client.post('/api/v1/modules/mail/agent/token')).json()['token']
            csrf = client.headers.pop('X-Framework-Token')
            bearer = {'Authorization':'Bearer ' + token}
            assert (await client.get('/api/v1/modules/mail/agent/pending',headers=bearer)).status_code == 200
            assert (await client.post('/api/v1/modules/mail/labels',headers=bearer,json={'message_id':'mail:m1','label':'Agent'})).status_code == 409
            assert (await client.post('/api/v1/modules/gradescope/sync',headers=bearer)).status_code == 403
            assert (await client.post('/api/v1/modules/mail/labels',headers={**bearer,'Origin':'https://foreign.example'},json={'message_id':'mail:m2','label':'Agent'})).status_code == 403
            client.headers['X-Framework-Token'] = csrf
            post = await client.get('/api/v1/modules/piazza/post',params={'course_id':'pc1','post_id':'p1'})
            assert post.status_code == 200 and post.json()['replies']
            recording = await client.get('/api/v1/modules/elrc/recording',params={'course_id':'rc1','recording_id':'video1'})
            assert recording.status_code == 200 and len(recording.json()['lessons'][0]['streams']) == 1
            transcript = await client.get('/api/v1/modules/elrc/transcript?stream_id=stream1')
            assert transcript.status_code == 200 and transcript.json()['transcript'][0]['start'] == 1
            file = await client.get('/api/v1/modules/gradescope/file?course_id=1001&assignment_id=2101')
            assert file.status_code == 200 and file.content == PDF
            material = next(item for item in courses['data']['materials'] if item['source'] == 'blackboard' and item.get('download_url'))
            file = await client.get(material['download_url'])
            assert file.status_code == 200 and file.content == PDF
            answer = await client.post('/api/v1/modules/assistant/chat',json={'message':'本周课程有哪些需要注意的事项？'})
            assert answer.status_code == 200 and answer.json()['citations']
            notices = await client.post('/api/v1/modules/notifications/generate')
            assert notices.status_code == 200 and len(notices.json()['items']) == 1
            notice_id = notices.json()['items'][0]['id']
            assert (await client.put('/api/v1/modules/notifications/' + notice_id + '/read',json={'read':True})).status_code == 200
            assert (await client.post('/api/v1/modules/notifications/generate')).json()['unchanged']
            assert (await client.put('/api/v1/modules/notifications/settings',json={'auto_generate':True})).status_code == 200
            assert (await client.put('/api/v1/modules/notifications',json={'enabled':False})).status_code == 200
            assert (await client.get('/api/v1/modules/notifications/snapshot')).status_code == 404
            assert (await client.put('/api/v1/modules/notifications',json={'enabled':True})).status_code == 200
            assert (await client.put('/api/v1/modules/piazza',json={'enabled':False})).status_code == 200
            assert 'piazza' in (await client.get('/api/v1/modules/courses/snapshot')).json()['unavailable']
            assert (await client.put('/api/v1/modules/piazza',json={'enabled':True})).status_code == 200
            refreshed = await client.post('/api/v1/modules/reload')
            assert refreshed.status_code == 200 and all(item['status'] == 'ready' for item in refreshed.json()['modules'])
            assert (await client.put('/api/v1/auth/coremail/credentials',json={'username':'second-synthetic@example.edu','password':'synthetic'})).status_code == 200
            assert (await client.get('/api/v1/modules/mail/snapshot')).json()['data']['messages'] == []
            assert (await client.get('/api/v1/modules/mail/agent/pending',headers=bearer)).status_code == 401
            assert (await client.get('/api/v1/modules/assistant/chat')).json()['messages'] == []
    print('integration: 11 modules, six synthetic source APIs, course joins, protected writes, details, downloads, AI, background toggling, reload and account isolation passed')


if __name__ == '__main__':
    temporary = PROJECT / '.codex' / 'tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='integration-',dir=temporary) as directory:
        asyncio.run(check(Path(directory)))
