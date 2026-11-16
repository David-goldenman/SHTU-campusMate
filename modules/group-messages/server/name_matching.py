"""One cancellable name-only worker, independent from collection and delivery."""
import asyncio
import copy
import threading
from uuid import uuid4

from . import matching


class NameMatcher:
    def __init__(self, service):
        self.service = service
        self.stopping, self.wake = threading.Event(), threading.Event()
        self.thread, self.active = None, None
        self.pending, self.views = {}, {}

    def key(self, owner, source, connection):
        return 'name-matches:' + owner + ':' + source + ':' + connection

    def read(self, owner, source, config):
        return self.service.context.store.read(self.key(owner, source, config['connection']), {})

    def write(self, owner, source, config, cache):
        cache['result_revision'] = uuid4().hex
        self.service.context.store.write(self.key(owner, source, config['connection']), cache)

    def view(self, owner, source, config, cache, state=None, error=None):
        selected = {row['id'] for row in config.get('selected', [])}
        rows = [row for gid, row in cache.get('records', {}).items() if gid not in selected]
        if state is None:
            state = 'error' if any(row['state'] == 'error' for row in rows) else 'cancelled' if any(row['state'] == 'cancelled' for row in rows) else 'done' if all(row['state'] == 'done' for row in rows) else 'idle'
        value = {'state': state, 'completed': sum(row['state'] == 'done' for row in rows), 'total': len(rows),
                 'result_revision': cache.get('result_revision', ''), 'error': error or cache.get('error')}
        self.views[(owner, source, config['connection'])] = value
        return value

    def status(self, owner, sources):
        return {source: copy.deepcopy(self.views.get((owner, source, config['connection'])) or self.view(owner, source, config, self.read(owner, source, config)))
                for source, config in sources.items()}

    def observe(self, owner, catalog, retry=None):
        with self.service.lock:
            if self.stopping.is_set() or owner != self.service.owner():
                return
            if self.active and self.active['owner'] != owner:
                self.active['cancel'].set()
            self.pending = {source: task for source, task in self.pending.items() if task['owner'] == owner}
            course_data = matching.catalog_data(catalog)
            for source, config in self.service.sources(owner).items():
                names = {row['id']: row['name'] for row in config.get('groups', [])}
                inputs = {'version': 1, **course_data, 'groups': names}
                cache = self.read(owner, source, config)
                changed = cache.get('inputs') != inputs
                if changed:
                    previous = cache.get('records', {}) if cache.get('inputs', {}).get('courses') == course_data['courses'] and cache.get('inputs', {}).get('current_semester') == course_data['current_semester'] else {}
                    records = {}
                    for gid, name in names.items():
                        local = matching.suggest({'id': gid, 'name': name}, catalog['items'], catalog['current_semester'])
                        if local['status'] in {'ambiguous', 'unmatched'}:
                            old = previous.get(gid, {})
                            records[gid] = old if old.get('name') == name else {'name': name, 'state': 'pending'}
                    cache = {'inputs': inputs, 'input_revision': uuid4().hex, 'records': records, 'error': None}
                    self.write(owner, source, config, cache)
                if retry == source:
                    for record in cache['records'].values():
                        if record['state'] in {'error', 'cancelled'}:
                            record['state'] = 'pending'
                    cache['error'] = None
                    self.write(owner, source, config, cache)
                selected = {row['id'] for row in config.get('selected', [])}
                needed = any(row['state'] == 'pending' and gid not in selected for gid, row in cache['records'].items())
                task = {'owner': owner, 'source': source, 'connection': config['connection'], 'input_revision': cache['input_revision'], 'cancel': threading.Event()}
                active = self.active
                same_active = active and not active['cancel'].is_set() and all(active[key] == task[key] for key in ('owner', 'source', 'connection', 'input_revision'))
                if active and active['source'] == source and not same_active:
                    active['cancel'].set()
                ready = needed and course_data['courses'] and self.service.context.ai.settings().get('enabled')
                if not ready:
                    self.pending.pop(source, None)
                if ready and not same_active:
                    self.pending[source] = task
                    self.view(owner, source, config, cache, 'queued')
                    self.wake.set()
                elif not same_active and source not in self.pending:
                    self.view(owner, source, config, cache)

    def suggestion(self, owner, source, config, group, catalog, local):
        if local['status'] not in {'ambiguous', 'unmatched'}:
            return local
        cache = self.read(owner, source, config)
        inputs = cache.get('inputs', {})
        if any(inputs.get(key) != value for key, value in matching.catalog_data(catalog).items()):
            return local
        record = cache.get('records', {}).get(group['id'], {})
        return copy.deepcopy(record['result']) if record.get('state') == 'done' and record.get('name') == group['name'] and record.get('result') else local

    def cancel(self, source):
        with self.service.lock:
            owner = self.service.owner()
            config = self.service.configuration(owner, source)
            self.pending.pop(source, None)
            if self.active and self.active['source'] == source and self.active['owner'] == owner:
                self.active['cancel'].set()
            cache = self.read(owner, source, config)
            for record in cache.get('records', {}).values():
                if record['state'] == 'pending':
                    record['state'] = 'cancelled'
            self.write(owner, source, config, cache)
            self.view(owner, source, config, cache, 'cancelled')

    def current(self, task):
        if self.stopping.is_set() or task['cancel'].is_set() or task['owner'] != self.service.owner():
            return None
        config = self.service.sources(task['owner']).get(task['source'])
        if not config or config['connection'] != task['connection']:
            return None
        cache = self.read(task['owner'], task['source'], config)
        if cache.get('input_revision') != task['input_revision'] or cache.get('inputs', {}).get('groups') != {row['id']: row['name'] for row in config.get('groups', [])}:
            return None
        return config, cache

    def process(self, task):
        while not self.stopping.is_set():
            with self.service.lock:
                current = self.current(task)
                if not current:
                    return
                config, cache = current
                if not self.service.context.ai.settings().get('enabled'):
                    self.view(task['owner'], task['source'], config, cache, 'idle')
                    return
                selected = {row['id'] for row in config.get('selected', [])}
                batch = [{'id': gid, 'name': row['name']} for gid, row in cache['records'].items() if row['state'] == 'pending' and gid not in selected][:40]
                if not batch:
                    self.view(task['owner'], task['source'], config, cache)
                    return
                self.view(task['owner'], task['source'], config, cache, 'running')
                inputs = copy.deepcopy(cache['inputs'])
            results = matching.run_ai(self.service.context, batch, inputs['courses'], inputs['current_semester'], task['cancel'])
            if task['cancel'].is_set() or self.stopping.is_set():
                return
            catalog = asyncio.run(self.service.course_catalog(task['owner']))
            with self.service.lock:
                current = self.current(task)
                if not current:
                    return
                if matching.catalog_data(catalog) != {key: inputs[key] for key in ('courses', 'current_semester')}:
                    self.observe(task['owner'], catalog)
                    return
                config, cache = current
                for group in batch:
                    cache['records'][group['id']].update(state='done', result=results[group['id']])
                self.write(task['owner'], task['source'], config, cache)
                self.view(task['owner'], task['source'], config, cache, 'running')

    def loop(self):
        while not self.stopping.is_set():
            self.wake.wait(1)
            self.wake.clear()
            while not self.stopping.is_set():
                with self.service.lock:
                    if not self.pending:
                        break
                    source = next(iter(self.pending))
                    task = self.active = self.pending.pop(source)
                try:
                    self.process(task)
                except Exception:
                    with self.service.lock:
                        current = self.current(task)
                        if current:
                            config, cache = current
                            for row in cache['records'].values():
                                if row['state'] == 'pending':
                                    row['state'] = 'error'
                            cache['error'] = '部分群名暂未完成匹配，已保留完成的建议，可重试剩余项。'
                            self.write(task['owner'], source, config, cache)
                            self.view(task['owner'], source, config, cache, 'error')
                finally:
                    with self.service.lock:
                        self.active = None

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.loop, name='group-name-matching', daemon=True)
            self.thread.start()
            if getattr(self.service.context, 'runtime', None):
                self.service.context.runtime.watch('群名与课程匹配', self.thread)

    def close(self):
        self.stopping.set()
        with self.service.lock:
            if self.active:
                self.active['cancel'].set()
            self.pending.clear()
        self.wake.set()
        if self.thread:
            self.thread.join()
