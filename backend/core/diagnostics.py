"""In-process operation correlation; identifiers never come from user input."""
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class Operation:
    id: str
    component: str
    phase: str


_operation: ContextVar[Operation | None] = ContextVar('campus_operation', default=None)


@contextmanager
def operation_scope(component='core', phase='request', *, new=False):
    if not all(isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', value)
               for value in (component, phase)):
        raise ValueError('Diagnostic component and phase must be fixed public names')
    parent = _operation.get()
    operation = Operation(uuid.uuid4().hex[:12] if new or parent is None else parent.id, component, phase)
    token = _operation.set(operation)
    try:
        yield operation
    finally:
        _operation.reset(token)


def operation_metadata():
    operation = _operation.get() or Operation(uuid.uuid4().hex[:12], 'core', 'request')
    return {'operation_id': operation.id, 'component': operation.component, 'phase': operation.phase}
