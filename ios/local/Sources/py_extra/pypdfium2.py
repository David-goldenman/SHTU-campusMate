"""pypdfium2-compatible shim backed by Apple PDFKit.

The shipping backend rasterizes PDF pages with ``pypdfium2`` (PDFium, a large
C++ library). On iOS the system already ships PDFKit, so the app exports three
C functions from its main binary (see Sources/PDFKitBridge.m) and this module
wraps them in the small part of the pypdfium2 API the backend uses::

    with pdfium.PdfDocument(path) as pdf:
        page = pdf[0]
        width, height = page.get_size()
        bitmap = page.render(scale=2.0)
        image = bitmap.to_pil()

``to_pil`` returns a tiny stand-in object with ``convert``/``save``/``close``
because the page is already rasterized to PNG by PDFKit.
"""

import ctypes
import os
import shutil
import tempfile

_lib = ctypes.CDLL(None)
_lib.cm_pdf_page_count.argtypes = [ctypes.c_char_p]
_lib.cm_pdf_page_count.restype = ctypes.c_int
_lib.cm_pdf_page_size.argtypes = [ctypes.c_char_p, ctypes.c_int,
                                  ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
_lib.cm_pdf_page_size.restype = ctypes.c_int
_lib.cm_pdf_render_page.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_double, ctypes.c_char_p]
_lib.cm_pdf_render_page.restype = ctypes.c_int


def _path(value):
    return os.fsencode(os.fspath(value))


class PdfDocument:
    def __init__(self, path):
        self.path = os.fspath(path)
        self._count = _lib.cm_pdf_page_count(_path(self.path))
        if self._count < 0:
            raise ValueError("无法读取 PDF 文件。")

    def __len__(self):
        return self._count

    def __getitem__(self, index):
        if index < 0:
            index += self._count
        if not 0 <= index < self._count:
            raise IndexError("PDF 页码超出范围。")
        return PdfPage(self.path, index)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self):
        return None


class PdfPage:
    def __init__(self, path, index):
        self._path = path
        self._index = index

    def get_size(self):
        width = ctypes.c_double()
        height = ctypes.c_double()
        if _lib.cm_pdf_page_size(_path(self._path), self._index,
                                 ctypes.byref(width), ctypes.byref(height)) != 0:
            raise ValueError("无法读取页面尺寸。")
        return width.value, height.value

    def render(self, scale=1.0):
        handle, name = tempfile.mkstemp(suffix=".png", prefix="pdf-page-")
        os.close(handle)
        if _lib.cm_pdf_render_page(_path(self._path), self._index, float(scale), _path(name)) != 0:
            os.unlink(name)
            raise ValueError("PDF 页面渲染失败。")
        return PdfBitmap(name)

    def close(self):
        return None


class PdfBitmap:
    def __init__(self, png_path):
        self._png = png_path
        self._closed = False

    def to_pil(self):
        return RenderedImage(self._png)

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                os.unlink(self._png)
            except FileNotFoundError:
                pass


class RenderedImage:
    """Stand-in for the PIL image returned by ``bitmap.to_pil()``."""

    def __init__(self, png_path):
        self._png = png_path

    def convert(self, mode="RGB"):
        return self

    def save(self, target, format=None, **options):
        shutil.copyfile(self._png, os.fspath(target))

    def close(self):
        return None
