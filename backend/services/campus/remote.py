from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from ..auth import LoginRequired


class SourceError(HTTPException):
    def __init__(self, message="来源响应格式已变化，请稍后重试或打开原站确认。"):
        super().__init__(502, message)


def rows(value, key=None):
    if key is not None:
        if not isinstance(value, dict) or key not in value:
            raise SourceError("来源没有返回预期的数据列表，已保留缓存。")
        value = value[key]
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise SourceError("来源数据列表格式不正确，已保留缓存。")
    return value


class Remote:
    def __init__(self, client, cancelled, hosts):
        self.client, self.cancelled, self.hosts = client, cancelled, set(hosts)

    def check(self):
        if self.cancelled.is_set():
            raise SourceError("同步已停止。")

    def request(self, method, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in self.hosts or parsed.username or parsed.password:
            raise SourceError("来源地址超出允许的服务范围。")
        for attempt in range(2):
            self.check()
            try:
                response = self.client.request(method, url, timeout=20, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    self.cancelled.wait(0.25)
                    continue
                raise SourceError("来源连接超时或网络中断，已保留上次成功数据。") from None
            if response.status_code in {401, 403} or urlsplit(str(response.url)).hostname not in self.hosts or "/login" in response.url.path.lower() or "authserver" in response.url.path:
                raise LoginRequired("来源登录已失效，请到设置重新连接。")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 0:
                    delay = response.headers.get("retry-after", "0.25")
                    self.cancelled.wait(min(float(delay), 1) if delay.replace(".", "", 1).isdigit() else 0.25)
                    continue
                raise SourceError("来源暂时繁忙或限制请求，请稍后同步。")
            if response.status_code == 404:
                raise HTTPException(404, "来源内容当前不可访问。")
            if not response.is_success:
                raise SourceError("来源未接受本次读取请求。")
            return response

    def json(self, method, url, **kwargs):
        response = self.request(method, url, **kwargs)
        try:
            return response.json()
        except ValueError:
            if "html" in response.headers.get("content-type", "") and any(marker in response.text.lower() for marker in ("loginform", "authserver", 'type="password"')):
                raise LoginRequired("来源返回了登录页面，请在设置重新连接。") from None
            raise SourceError("来源返回了无法读取的 JSON，已保留缓存。") from None

    def pages(self, url, *, key="results", params=None, next_key="paging"):
        seen = set()
        for _ in range(100):
            if url in seen:
                raise SourceError("来源分页链接重复，已停止读取并保留缓存。")
            seen.add(url)
            data = self.json("GET", url, params=params)
            yield from rows(data, key)
            page = data.get(next_key) or {}
            if not isinstance(page, dict):
                raise SourceError("来源分页信息格式不正确。")
            link = page.get("nextPage")
            if not link:
                return
            from urllib.parse import urljoin
            url, params = urljoin(url, link), None
        raise SourceError("来源分页超过 100 页，请缩小读取范围。")
