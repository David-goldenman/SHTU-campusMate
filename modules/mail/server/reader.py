from urllib.parse import urlsplit
from html import escape
import re

from bs4 import BeautifulSoup, Comment

from backend.services.auth import LoginRequired
from backend.services.campus import SourceError, identity, rows, timestamp

BASE = "https://mail.shanghaitech.edu.cn/coremail/"
EXPIRED = {"FA_UNAUTHORIZED", "FA_INVALID_SESSION", "FA_INVALID_TEMP_SESSION", "FA_SECURITY"}


def rpc(remote, parameters, function, payload):
    data = remote.json("POST", BASE + "s/json", params={**parameters, "func": function}, json=payload)
    if not isinstance(data, dict):
        raise SourceError("邮箱没有返回对象。")
    code = data.get("code") or data.get("errorCode")
    if code in EXPIRED:
        raise LoginRequired("邮箱会话已到期，请到设置导入新的会话。")
    if code != "S_OK":
        raise SourceError("邮箱未接受读取请求，请稍后重试。")
    return data


def inbox(remote, parameters, previous):
    data = rpc(remote, parameters, "mbox:listMessages", {"fid": 1, "start": 0, "limit": 100, "mode": "all", "order": "date", "desc": True, "returnTotal": True})
    if "var" not in data:
        raise SourceError("邮箱没有返回收件箱列表，已保留缓存。")
    value = data.get("var")
    messages, issues = [], []
    old = {item["id"]: item for item in previous.get("messages", [])}
    for item in rows(value, "messages") if isinstance(value, dict) else rows(value):
        mid = item.get("id")
        if not isinstance(mid, (str, int)) or str(mid) == "":
            issues.append("一封邮件缺少标识，未加入列表。")
            continue
        sender = item.get("from") or ""
        if isinstance(sender, dict):
            sender = " ".join(str(sender.get(key) or "") for key in ("name", "email")).strip()
        flags = item.get("flags")
        read = flags.get("read") if isinstance(flags, dict) else None
        received = timestamp(item.get("receivedDate"))
        if item.get("receivedDate") and received is None:
            issues.append("一封邮件的收件时间无法识别，已保留原邮件入口。")
        canonical = identity("mail", mid)
        messages.append({"id": canonical, "source": "mail", "source_id": str(mid), "title": str(item.get("subject") or "（无主题）"), "sender": str(sender), "received_at": received, "unread": not read if type(read) is bool else None, "url": BASE, "body_text": old.get(canonical, {}).get("body_text", "")})
    return {"messages": messages, "issues": list(dict.fromkeys(issues)), "metadata": {"folder": "收件箱", "limit": 100, "total": data.get("total", value.get("total") if isinstance(value, dict) else None)}}


def presentation(content):
    if not isinstance(content, str):
        raise SourceError("邮件正文格式无法识别。")
    if not re.search(r'</?(?:html|body|p|div|span|br|table|ul|ol|h[1-6]|a|pre|strong|b)\b', content, re.I):
        paragraphs = re.split(r'\n\s*\n', content.replace('\r\n', '\n'))
        content = ''.join('<p>' + escape(part).replace('\n', '<br>') + '</p>' for part in paragraphs)
    tree = BeautifulSoup(content, "html.parser")
    for comment in tree.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for node in tree.select("script, style, iframe, object, embed, form, svg, math, template, head"):
        node.decompose()
    allowed = set("p div span br hr b strong i em u s sup sub wbr blockquote pre code ul ol li table thead tbody tfoot tr td th caption h1 h2 h3 h4 h5 h6 dl dt dd a".split())
    for node in list(tree.find_all(True)):
        if not node.name:
            continue
        if node.name == 'font':
            node.name = 'span'
        if node.name == "img":
            node.replace_with("[图片：" + str(node.get("alt") or "邮件图片") + "]")
        elif node.name not in allowed:
            node.unwrap()
        else:
            attrs = {}
            style = str(node.get('style', '')).lower()
            classes = []
            align = re.search(r'text-align\s*:\s*(left|right|center|justify)\b', style)
            if align or str(node.get('align', '')).lower() in {'left', 'right', 'center', 'justify'}:
                classes.append('mail-align-' + (align[1] if align else node['align'].lower()))
            if re.search(r'font-weight\s*:\s*(?:bold|[7-9]00)', style):
                classes.append('mail-bold')
            if re.search(r'font-style\s*:\s*italic', style):
                classes.append('mail-italic')
            if re.search(r'text-decoration(?:-line)?\s*:[^;]*underline', style):
                classes.append('mail-underline')
            size = re.search(r'font-size\s*:\s*(\d+(?:\.\d+)?)(px|pt)\b', style)
            if size:
                pixels = float(size[1]) * (4 / 3 if size[2] == 'pt' else 1)
                classes.append('mail-font-' + ('small' if pixels < 14 else 'large' if pixels >= 19 else 'normal'))
            color = re.search(r'(?:^|;)\s*color\s*:\s*([^;]+)', style)
            value = (color[1] if color else str(node.get('color', ''))).strip().lower()
            if value in {'red', '#ff0000', '#f00', 'rgb(255, 0, 0)'}:
                classes.append('mail-important')
            if re.search(r'font-family\s*:[^;]*(?:宋体|simsun|times|serif)', style) and 'sans-serif' not in style:
                classes.append('mail-serif')
            if classes:
                attrs['class'] = ' '.join(classes)
            href = str(node.get("href") or "").strip()
            if node.name == "a" and urlsplit(href).scheme.lower() in {"http", "https", "mailto"}:
                attrs.update(href=href, target="_blank", rel="noopener noreferrer")
            if node.name in {"td", "th"}:
                for key in ("colspan", "rowspan"):
                    value = str(node.get(key, ""))
                    if value.isdigit() and 1 <= int(value) <= 30:
                        attrs[key] = value
            node.attrs = attrs
    body = tree.body or tree
    return {"body_html": body.decode_contents(), "body_text": body.get_text("\n", strip=True), "url": BASE}


def read_message(remote, parameters, message_id):
    data = remote.json("POST", BASE + "XT/jsp/readMessage.jsp", params=parameters, data={"mid": message_id, "markRead": "false", "mboxa": ""})
    if not isinstance(data, dict):
        raise SourceError("邮箱正文返回格式已变化。")
    if data.get("code") in EXPIRED:
        raise LoginRequired("邮箱会话已到期。")
    if data.get("code") != "S_OK" or not isinstance(data.get("var"), dict):
        raise SourceError("邮箱未返回邮件正文。")
    mail = data["var"].get("mail", data["var"])
    part = mail.get("mainPartData") if isinstance(mail, dict) else None
    if not isinstance(part, dict):
        raise SourceError("邮件正文结构已变化。")
    return {**presentation(part.get("content")), "attachments": mail.get("attachments") if isinstance(mail.get("attachments"), list) else []}
