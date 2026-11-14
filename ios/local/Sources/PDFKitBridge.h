#ifndef PDFKitBridge_h
#define PDFKitBridge_h

/// Minimal C surface over PDFKit so the embedded Python can rasterize PDF
/// pages without shipping pypdfium2 (a large C++ dependency).
///
/// Symbols are exported from the main executable (-export_dynamic) and reached
/// from Python with ctypes.CDLL(None); see py_extra/pypdfium2.py.
int cm_pdf_page_count(const char *path);
int cm_pdf_page_size(const char *path, int index, double *width, double *height);
int cm_pdf_render_page(const char *path, int index, double scale, const char *output);

#endif /* PDFKitBridge_h */
