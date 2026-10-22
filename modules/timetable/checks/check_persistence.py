"""Stable timetables reuse storage; explicit updates and semester rollover still work."""
import asyncio
import copy
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import httpx
from checks.module_support import load, sandbox
from backend.services.campus.data import validate_bundle
from backend.services.campus.analysis import account_revision

module = load('timetable')
persistence = sys.modules[module.__name__ + '.persistence']
year, season = persistence.expected_semester(datetime.now(persistence.ZONE).date()).split('-')
label = {'fall': '秋季', 'spring': '春季', 'summer': '夏季'}[season]
metadata = {'semester': f'{year}-{int(year)+1}学年{label}', 'semester_id': 'fixture'}
term = persistence.semester(metadata['semester'])
data = validate_bundle({'metadata': metadata, 'courses': [
    {'id': 'timetable:c', 'source': 'timetable', 'code': 'EE130', 'term': term, 'title': '电磁学'}]})


async def check():
    with sandbox('timetable') as context:
        reads, peers = [], []

        def fetch(remote, previous):
            reads.append(True)
            return copy.deepcopy(data)

        def create():
            return persistence.SavedTimetable(context, 'ids', ['example.edu'], fetch)

        source = create()
        try:
            old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            context.store.write('snapshot', {'owner': source.owner(), 'data': data, 'updated_at': old_time})
            context.store.write('sync', {'owner': source.owner(), 'status': 'ready'})
            for _ in range(10):
                assert source.snapshot()['status'] == 'ready'
                assert source.sync()['reused']
            assert reads == [], 'Elapsed hours, page reads and aggregate sync never reread a saved semester'
            assert not source._is_stale({'updated_at': old_time, 'data': {'metadata': {'semester': '旧格式学期'}}}), 'Unknown legacy terms do not justify automatic replacement'
            source.close()
            source = create()
            assert source.sync()['reused'] and reads == [], 'Restart restores the persisted semester'

            async def api(name, path='/snapshot', **kwargs):
                peers.append((name, path, kwargs))
                return httpx.Response(200, json={'status': 'ready', 'updated_at': old_time, 'data': validate_bundle({
                    'courses': [{'id': name + ':c', 'source': name, 'code': 'EE130', 'term': term}]})})

            context.api = api
            saved = source.snapshot()
            reviews = await asyncio.gather(*(persistence.verify_saved(context, source, saved) for _ in range(5)))
            assert all(review == reviews[0] for review in reviews)
            assert reviews[0]['status'] == 'verified' and reviews[0]['confirmed'] == 1
            assert reviews[0]['courses'][0]['sources'] == ['elrc', 'ecourse']
            assert len(peers) == 2 and all(options == {'reuse_key': account_revision(context)} for _, _, options in peers), 'One passive comparison, no remote sync commands'
            source.close()
            source = create()
            assert (await persistence.verify_saved(context, source, source.snapshot())) == reviews[0]
            assert len(peers) == 2, 'The comparison survives reload too'

            assert source.sync(force=True)['queued']
            source.future.result(timeout=5)
            assert len(reads) == 1
            assert source.sync()['reused']
            await persistence.verify_saved(context, source, source.snapshot())
            assert len(peers) == 4, 'An explicitly updated timetable gets a new comparison'

            context.store.write('snapshot', {'owner': source.owner(), 'updated_at': old_time,
                                            'data': validate_bundle({'metadata': {'semester': f'{int(year)-1}-{year}学年{label}'}})})
            source.snapshot()
            source.future.result(timeout=5)
            assert len(reads) == 2 and not source._is_stale(context.store.read('snapshot'))

            async def mismatch(name, path='/snapshot', **kwargs):
                return httpx.Response(200, json={'status': 'ready', 'data': validate_bundle({'courses': [
                    {'id': name + ':wrong', 'source': name, 'code': 'EE130P', 'term': term},
                    {'id': name + ':old', 'source': name, 'code': 'EE130', 'term': '2000-fall'}]})})

            context.api = mismatch
            context.store.delete('timetable-verification:' + source.owner() + ':' + persistence.term_key(metadata))
            assert (await persistence.verify_saved(context, source, source.snapshot()))['confirmed'] == 0
            calendar = module.SchoolCalendar(context, source)
            key = persistence.term_key(metadata)
            context.store.write('school-calendar:' + year, {'terms': {key: {'week_one': '2000-09-04'}}, 'checked_at': old_time})
            assert not calendar.due(metadata), 'Known school dates do not expire weekly'
            assert calendar.refresh(metadata, force=False)['terms'][key]['week_one'] == '2000-09-04', 'Repeated automatic triggers use saved dates'
            context.store.write('school-calendar:' + year, {'attempted_term': key, 'error': 'fixture failure', 'checked_at': old_time})
            assert not calendar.due(metadata), 'Failed calendar reads require explicit retry, not a page-load loop'
            context.auth.revision = 'different-account'
            assert not source.snapshot()['data']['courses'], 'Account changes never reuse another account timetable'
        finally:
            source.close()


asyncio.run(check())
print('timetable persistence: no hourly rereads, restart reuse, passive verification, explicit updates, new semester and account isolation passed')
