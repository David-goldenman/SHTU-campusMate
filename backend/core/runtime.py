"""One in-memory request result and a small set of owned workers per module."""
import threading
from copy import deepcopy
from concurrent.futures import Future
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class RuntimeStatus:
    def __init__(self):
        self.lock = threading.RLock()
        self.loaded_at = now()
        self.last_request = self.last_success_at = self.last_error = None
        self.workers = {}
        self.sources = {}

    def record_source(self, name, state, *, cached_at=None):
        """Source results are independent of successful HTTP status polling."""
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise ValueError('Source state needs a fixed public task name')
        with self.lock:
            if name not in self.sources and len(self.sources) >= 16:
                raise ValueError('单个模块最多登记 16 项来源状态。')
            value = {key: state[key] for key in ('status', 'last_success_at', 'started_at', 'finished_at') if key in state}
            diagnostic = state.get('diagnostic') or {}
            value.update({key: diagnostic[key] for key in ('code', 'action', 'request_id', 'operation_id', 'component', 'phase') if key in diagnostic})
            self.sources[name] = {**value, 'cached_at': cached_at}

    def watch(self, name, worker):
        """Register an existing owned Thread/Future; this does not start or stop it."""
        if not isinstance(worker, (threading.Thread, Future)) or not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise ValueError('运行状态需要简短任务名和 Thread/Future。')
        with self.lock:
            if name not in self.workers and len(self.workers) >= 16:
                raise ValueError('单个模块最多登记 16 项后台任务。')
            self.workers[name] = worker

    def record(self, status, elapsed, error=None, *, operation=None):
        with self.lock:
            result = {'at': now(), 'status': status, 'duration_ms': round(elapsed * 1000)}
            result.update({key: operation[key] for key in ('operation_id', 'component', 'phase') if operation and key in operation})
            self.last_request = result
            if status < 400:
                self.last_success_at = result['at']
            else:
                self.last_error = {**result, **(error or {})}

    def snapshot(self):
        with self.lock:
            workers = []
            for name, worker in self.workers.items():
                if isinstance(worker, threading.Thread):
                    status = 'running' if worker.is_alive() else 'stopped'
                    kind = 'thread'
                else:
                    status = 'cancelled' if worker.cancelled() else 'running' if not worker.done() else 'error' if worker.exception() else 'idle'
                    kind = 'task'
                workers.append({'name': name, 'kind': kind, 'status': status})
            return {'loaded_at': self.loaded_at, 'last_request': self.last_request, 'last_success_at': self.last_success_at,
                    'last_error': self.last_error, 'workers': workers, 'sources': deepcopy(self.sources)}
