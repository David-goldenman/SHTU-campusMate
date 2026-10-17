"""Public errors carry a support ID; diagnostics never contain request data."""
import logging
import sqlite3
import uuid

from fastapi.responses import JSONResponse

logger = logging.getLogger('campus.errors')


class PublicError(RuntimeError):
    """A deliberately public local-environment message, never raw provider text."""


STATUS = {
    400: ('invalid_request', '请检查输入和本地服务设置。'),
    401: ('login_required', '请到设置 → 账号连接，检查登录。'),
    403: ('access_denied', '请从本机工作台打开页面并刷新后重试。'),
    404: ('not_found', '请检查模块是否启用，或刷新页面。'),
    409: ('conflict', '请确认当前任务和连接状态，完成后再重试。'),
    422: ('invalid_fields', '请检查标出的字段后重新提交。'),
    500: ('internal_error', '请重试；若仍失败，请保留错误编号并重启工作台。'),
    502: ('network_error', '请检查网络及来源服务，稍后重试。'),
    503: ('busy', '请等待当前任务完成，再重试。'),
    504: ('timeout', '请先检查操作结果，避免重复提交。'),
}


def error_response(request, status, detail, *, code=None, action=None, error=None, headers=None):
    default_code, default_action = STATUS.get(status, STATUS[500])
    request_id = uuid.uuid4().hex[:12]
    body = {'detail': detail, 'code': code or default_code, 'action': action or default_action, 'request_id': request_id}
    request.scope.setdefault('state', {})['public_error'] = {key: body[key] for key in ('code', 'request_id')}
    # No URL, exception text, traceback, account, or request/response bodies.
    logger.warning('request_failed id=%s status=%s code=%s type=%s', request_id, status, body['code'], type(error).__name__ if error else 'HTTPError')
    return JSONResponse(body, status_code=status, headers={**(headers or {}), 'X-Request-ID': request_id})


async def http_error(request, error):
    return error_response(request, error.status_code, error.detail, headers=error.headers)


async def storage_error(request, error):
    busy = getattr(error, 'sqlite_errorcode', None) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    return error_response(request, 503 if busy else 500,
                          '本地数据正在使用，请稍后重试。' if busy else '本地数据无法读取或保存。',
                          code='storage_busy' if busy else 'storage_error',
                          action='请稍后重试。' if busy else '请检查磁盘空间和目录权限；数据损坏时可在本地设置恢复备份。', error=error)


async def file_error(request, error):
    return error_response(request, 500, '本地文件无法读取或保存。', code='file_error',
                          action='请检查磁盘空间、目录权限和文件占用后重试。', error=error)


async def catch_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception as error:
        return error_response(request, 500, '操作未完成，服务遇到异常。', error=error)
