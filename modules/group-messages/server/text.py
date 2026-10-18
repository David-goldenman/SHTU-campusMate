"""QJQ's readable-message and limited redaction rules, shared by both adapters."""
import re
from xml.etree.ElementTree import ParseError
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring


def public_text(text):
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{16,}\b', '[密钥已隐藏]', text)
    text = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', '[手机号已隐藏]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[邮箱已隐藏]', text)
    return re.sub(r'(学号\s*[:：]?\s*)\d{6,15}', r'\1[已隐藏]', text)


def readable(message):
    if message.type_code in {1, 10000}:
        return message.text, 'text' if message.type_code == 1 else 'system', ''
    if message.type_code == 49 and len(message.text) <= 2 * 1024 * 1024:
        try:
            root = fromstring(message.text)
            app = root if root.tag == 'appmsg' else root.find('.//appmsg')
            if app is not None:
                kind, title = app.findtext('type', ''), app.findtext('title', '')
                if kind == '6':
                    return '[文件标题，正文未读取] ' + title, 'file_title', ''
                if kind == '57':
                    quoted = app.findtext('refermsg/content', '')
                    return title + ('\n[引用的旧消息] ' + quoted if quoted else ''), 'reply', app.findtext('refermsg/svrid', '')
                if kind == '5':
                    return '[链接标题，正文未读取] ' + title, 'link_title', ''
        except (ParseError, DefusedXmlException, ValueError):
            pass
    return '[图片、语音或其他非文字内容未读取]', 'unread_media', ''
