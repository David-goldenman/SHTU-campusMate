import io
import posixpath
import zipfile
from xml.etree import ElementTree

from fastapi import HTTPException
from pypdf import PdfReader
from pypdf.errors import PyPdfError


def extract(content, media_type, title):
    if not content or len(content) > 30 * 1024 * 1024:
        raise HTTPException(422, "资料应为非空且至多 30 MB 的文件。")
    try:
        if content.startswith(b"%PDF"):
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 1000:
                raise HTTPException(422, "请使用未加密且至多 1000 页的 PDF。")
            kind, pages = "pdf", [(page.extract_text() or "").strip()[:20000] for page in reader.pages]
        elif content.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist() if item.filename.endswith(('.xml', '.rels'))) > 40 * 1024 * 1024:
                    raise HTTPException(422, "课件文字结构超过 40 MB，请拆分后读取。")
                relations = ElementTree.fromstring(archive.read('ppt/_rels/presentation.xml.rels'))
                targets = {item.attrib['Id']: posixpath.normpath(posixpath.join('ppt', item.attrib['Target'])).lstrip('/') for item in relations}
                presentation = ElementTree.fromstring(archive.read('ppt/presentation.xml'))
                slides = presentation.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId')
                if len(slides) > 1000:
                    raise HTTPException(422, "请使用至多 1000 页的 PPTX。")
                kind, pages = "pptx", []
                for slide in slides:
                    target = targets[slide.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                    if not target.startswith('ppt/slides/') or not target.endswith('.xml'):
                        raise ValueError("Invalid slide target")
                    node = ElementTree.fromstring(archive.read(target))
                    paragraphs = [''.join(part.itertext()) for part in node.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}p')]
                    pages.append('\n'.join(paragraphs).strip()[:20000])
        elif media_type.startswith('text/') or title.lower().endswith(('.txt', '.md', '.csv')):
            kind, pages = "text", [content.decode('utf-8-sig').strip()[:20000]]
        else:
            raise HTTPException(422, "当前支持 PDF、PPTX 和 UTF-8 文本；请下载原文件查看其他格式。")
    except (ValueError, KeyError, OSError, PyPdfError, zipfile.BadZipFile, ElementTree.ParseError):
        raise HTTPException(422, "资料文字无法解析，请下载原文件查看。") from None
    if not any(pages):
        raise HTTPException(422, "资料没有可提取的文字，扫描页或图片内容请在原文件中查看。")
    return {"kind": kind, "pages": pages}
