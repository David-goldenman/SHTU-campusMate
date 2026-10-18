import tempfile
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ..auth import LoginRequired
from .remote import Remote, SourceError


def download(context, provider, hosts, resolve, cancelled, target=None, *, max_bytes=None):
    """Finish authenticated I/O in one thread; response transfer uses a local temp file."""
    temporary = None
    try:
        with context.auth.authenticated_client(provider, target=target) as client:
            remote = Remote(client, cancelled, hosts)
            url, filename = resolve(remote)
            for _ in range(6):
                remote.check()
                remote.checked_url(url)
                with client.stream("GET", url, timeout=30, follow_redirects=False) as response:
                    if response.is_redirect:
                        if not response.headers.get("location"):
                            raise SourceError("文件跳转缺少地址。")
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code in {401, 403}:
                        raise LoginRequired("下载需要重新登录来源。")
                    if not response.is_success:
                        raise SourceError("来源文件暂时无法下载。")
                    media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
                    if media_type in {"text/html", "application/xhtml+xml", "application/json"}:
                        raise SourceError("来源返回了页面或错误对象，请重新同步后下载。")
                    length = response.headers.get('content-length', '')
                    if max_bytes is not None and length.isdigit() and int(length) > max_bytes:
                        raise SourceError('文件超过单次读取大小限制，请在原站查看。')
                    directory = context.data_dir / 'tmp' / 'downloads'
                    directory.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                        temporary = Path(output.name)
                        size = 0
                        for chunk in response.iter_bytes():
                            remote.check()
                            size += len(chunk)
                            if max_bytes is not None and size > max_bytes:
                                raise SourceError('文件超过单次读取大小限制，请在原站查看。')
                            output.write(chunk)
                    if temporary.stat().st_size == 0:
                        raise SourceError("来源返回了空文件，请稍后重试。")
                    filename = str(filename or unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or "course-material").replace("\\", "/").rsplit("/", 1)[-1].replace("\r", "").replace("\n", "")[:180]
                    return FileResponse(temporary, media_type=media_type, filename=filename, background=BackgroundTask(temporary.unlink, missing_ok=True))
            raise SourceError("文件跳转次数过多。")
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
