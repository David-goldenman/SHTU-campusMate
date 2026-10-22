"""Opt-in reads shared only within a live GET request, never across requests."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Hashable, TypeVar

from fastapi import HTTPException

T = TypeVar('T')


@dataclass
class ReadBatch:
    active: bool = True
    transports: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)


_batch: ContextVar[ReadBatch | None] = ContextVar('module_read_batch', default=None)


def current_batch() -> ReadBatch | None:
    batch = _batch.get()
    return batch if batch is not None and batch.active else None


@contextmanager
def request_reads(enabled: bool = True):
    """Nested reads inherit their caller; writes temporarily leave that batch."""
    if enabled and current_batch() is not None:
        yield
        return
    previous = current_batch()
    if not enabled and previous is not None:
        # A write may change anything that was read earlier in this batch.
        previous.transports.clear()
        previous.values.clear()
    batch = ReadBatch() if enabled else None
    token = _batch.set(batch)
    try:
        yield
    finally:
        if batch is not None:
            batch.active = False
            batch.transports.clear()
            batch.values.clear()
        _batch.reset(token)


async def read_once(context: Any, key: Hashable, revision: Callable[[], Hashable],
                    load: Callable[[], Awaitable[T]]) -> T:
    """Share an explicitly read-only calculation; each caller owns its result."""
    batch = current_batch()
    if batch is None:
        return await load()
    version = revision()
    loop, task = asyncio.get_running_loop(), asyncio.current_task()
    identity = (id(context), key, version, id(loop))
    record = batch.values.get(identity)
    if record is None:
        future = loop.create_future()
        # Observe errors even when all followers have already disconnected.
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        batch.values[identity] = (future, task)
        try:
            value = await load()
            if version != revision():
                raise HTTPException(409, '读取期间账号或资料版本已变化，请刷新后重试。')
            future.set_result(deepcopy(value))
            return value
        except BaseException as error:
            if batch.values.get(identity, (None,))[0] is future:
                batch.values.pop(identity, None)
            if isinstance(error, asyncio.CancelledError):
                future.cancel()
            else:
                future.set_exception(error)
            raise
    future, leader = record
    if not future.done() and leader is task:
        raise RuntimeError('只读聚合存在循环调用。')
    value = await asyncio.shield(future)
    if version != revision():
        raise HTTPException(409, '读取期间账号或资料版本已变化，请刷新后重试。')
    return deepcopy(value)
