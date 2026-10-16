"""Piazza-only adaptation of WYT's message-hub source_api/connectors/storage."""
import html
import math
import re
import secrets
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

from backend.services.auth import LoginRequired

BASE = "https://piazza.com"
ID = re.compile(r"[A-Za-z0-9_-]{1,100}")


def identifier(value):
    value = str(value)
    if not ID.fullmatch(value):
        raise ValueError("Piazza 课程或帖子 ID 格式不正确。")
    return value


def safe_url(value):
    if not str(value).strip():
        return ""
    value = urljoin(BASE + "/", str(value))
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return ""


class PostHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.assets = [], []
        self.ignored = 0

    def handle_data(self, data):
        if not self.ignored:
            self.text.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        if self.ignored:
            return
        if tag in {"p", "br", "div", "li"}:
            self.text.append("\n")
        data = dict(attrs)
        url = data.get("src" if tag == "img" else "href") or ""
        if tag == "img" or (tag == "a" and re.search(r"\.(pdf|zip|docx?|xlsx?|pptx?|csv|py|ipynb)(\?|$)|/uploads/|/files/|amazonaws", url, re.I)):
            absolute = safe_url(url)
            if absolute:
                self.assets.append({"kind": "image" if tag == "img" else "file", "url": absolute,
                                    "name": data.get("alt") or urlsplit(absolute).path.rsplit("/", 1)[-1] or "课程附件"})

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)


def classify(body, files=False):
    """Preserve the share bundle's explainable candidate-importance rules."""
    text = body.lower()
    deadline = re.search(r"截止|deadline|\bdue\b|提交.{0,12}(前|之前)|今晚|明天.{0,8}(交|考)", text)
    change = re.search(r"(考试|exam|教室|上课|答辩).{0,25}(调整|改|取消|change|cancel)|紧急|urgent", text)
    action = re.search(r"请.{0,20}(提交|确认|填写|完成)|必须|需要.{0,10}(提交|完成)|\bsubmit\b", text)
    if change:
        return "high", "包含紧急事项或考试、课程安排变化，请核对原文。"
    if deadline and action:
        return "high", "同时出现时间要求和待执行事项。"
    if deadline:
        return "medium", "提及截止时间或近期安排，需要结合上下文确认。"
    if files:
        return "medium", "包含图片或文件，可打开原始附件核对。"
    return "normal", "暂未发现明确的行动要求。"


def timestamp(value):
    """Do not substitute today's date for an unknown post timestamp."""
    try:
        if isinstance(value, (int, float)):
            result = value / 1000 if value > 1e12 else value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            result = parsed.timestamp()
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def parse_post(post, course_id):
    if not isinstance(post, dict):
        raise ValueError("Piazza 帖子格式已变化。")
    cid = identifier(post.get("id") or post.get("cid") or post.get("nr") or "")
    history = post.get("history") or []
    if not isinstance(history, list):
        raise ValueError("Piazza 帖子历史格式已变化。")
    root = history[0] if history else post
    if not isinstance(root, dict):
        raise ValueError("Piazza 帖子正文格式已变化。")
    title = html.unescape(re.sub(r"<[^>]*>", " ", str(root.get("subject") or post.get("subject") or "课程消息"))).strip()
    parsed = PostHTML()
    parsed.feed(str(root.get("content") or post.get("content") or ""))
    children = post.get("children") or []
    if not isinstance(children, list):
        raise ValueError("Piazza 回复格式已变化。")
    pending = list(reversed(children))
    count = 0
    while pending:
        node = pending.pop()
        count += 1
        if count > 500 or not isinstance(node, dict):
            raise ValueError("Piazza 回复过多或格式已变化，请在原站查看。")
        history = node.get("history") or []
        if not isinstance(history, list) or (history and not isinstance(history[0], dict)):
            raise ValueError("Piazza 回复历史格式已变化。")
        body = history[0].get("content", "") if history else node.get("subject") or node.get("content") or ""
        parsed.text.append("\n[回复]\n")
        parsed.feed(str(body))
        children = node.get("children") or []
        if not isinstance(children, list):
            raise ValueError("Piazza 回复格式已变化。")
        pending.extend(reversed(children))
    body = "\n".join(text.strip() for text in parsed.text if text.strip())
    level, reason = classify(title + "\n" + body, bool(parsed.assets))
    return {"id": cid, "course_id": course_id, "title": title, "body": body,
            "attachments": parsed.assets, "level": level, "reason": reason,
            "created_at": timestamp(post.get("created")), "updated_at": timestamp(post.get("updated")),
            "url": BASE + "/class/" + identifier(course_id) + "?cid=" + quote(str(post.get("nr") or cid), safe="")}


class Piazza:
    READ_METHODS = {"network.get_my_feed", "content.get"}

    def __init__(self, client):
        self.client = client

    def rpc(self, method, params):
        if method not in self.READ_METHODS:
            raise ValueError("仅支持课程帖子读取。")
        token = next((cookie.value for cookie in self.client.cookies.jar
                      if cookie.name == "session_id" and cookie.domain.lstrip(".") == "piazza.com"), "")
        response = self.client.post(BASE + "/logic/api",
                                    params={"method": method, "aid": secrets.token_hex(8)},
                                    json={"method": method, "params": params},
                                    headers={"CSRF-Token": token}, follow_redirects=False, timeout=25)
        if response.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise LoginRequired("请在设置中重新连接 Piazza。")
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            raise RuntimeError("Piazza 响应超过 8 MB，本页未导入。")
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("Piazza 未返回课程数据，请检查登录状态。") from None
        if not isinstance(result, dict) or result.get("error") or result.get("result") is None:
            raise RuntimeError("Piazza 拒绝读取，请检查登录状态及课程权限。")
        return result["result"]

    def feed(self, course_id, offset=0):
        value = self.rpc("network.get_my_feed", {"nid": course_id, "limit": 20, "offset": offset, "sort": "updated"})
        if not isinstance(value, dict) or not isinstance(value.get("feed"), list):
            raise RuntimeError("Piazza 课程列表格式已变化。")
        rows = value["feed"]
        if len(rows) > 20 or any(not isinstance(row, dict) or not row.get("id") for row in rows):
            raise RuntimeError("Piazza 分页格式已变化。")
        return rows

    def post(self, course_id, post_id):
        return self.rpc("content.get", {"nid": course_id, "cid": post_id, "student_view": None})
