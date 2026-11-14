#import "PDFKitBridge.h"

#import <Foundation/Foundation.h>
#import <PDFKit/PDFKit.h>
#import <UIKit/UIKit.h>

// Keep the symbols in the executable and in its dynamic symbol table so the
// embedded Python can resolve them through ctypes.CDLL(None).
#define CM_EXPORT __attribute__((used, visibility("default")))

static PDFDocument *cm_open(const char *path) {
    if (path == NULL) {
        return nil;
    }
    NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:path]];
    return [[PDFDocument alloc] initWithURL:url];
}

CM_EXPORT int cm_pdf_page_count(const char *path) {
    @autoreleasepool {
        PDFDocument *document = cm_open(path);
        if (document == nil) {
            return -1;
        }
        return (int)document.pageCount;
    }
}

CM_EXPORT int cm_pdf_page_size(const char *path, int index, double *width, double *height) {
    @autoreleasepool {
        PDFDocument *document = cm_open(path);
        if (document == nil || index < 0 || index >= (int)document.pageCount) {
            return -1;
        }
        PDFPage *page = [document pageAtIndex:(NSUInteger)index];
        CGRect box = [page boundsForBox:kPDFDisplayBoxMediaBox];
        if (width != NULL) *width = box.size.width;
        if (height != NULL) *height = box.size.height;
        return 0;
    }
}

CM_EXPORT int cm_pdf_render_page(const char *path, int index, double scale, const char *output) {
    @autoreleasepool {
        if (output == NULL || scale <= 0) {
            return -1;
        }
        PDFDocument *document = cm_open(path);
        if (document == nil || index < 0 || index >= (int)document.pageCount) {
            return -1;
        }
        PDFPage *page = [document pageAtIndex:(NSUInteger)index];
        CGRect box = [page boundsForBox:kPDFDisplayBoxMediaBox];
        CGSize size = CGSizeMake(box.size.width * scale, box.size.height * scale);
        if (size.width < 1 || size.height < 1) {
            return -1;
        }

        UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat defaultFormat];
        format.opaque = YES;
        format.scale = 1.0;
        UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:size format:format];
        UIImage *image = [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
            CGContextRef cg = context.CGContext;
            CGContextSetRGBFillColor(cg, 1, 1, 1, 1);
            CGContextFillRect(cg, CGRectMake(0, 0, size.width, size.height));
            CGContextSaveGState(cg);
            CGContextTranslateCTM(cg, 0, size.height);
            CGContextScaleCTM(cg, scale, -scale);
            [page drawWithBox:kPDFDisplayBoxMediaBox toContext:cg];
            CGContextRestoreGState(cg);
        }];
        NSData *png = UIImagePNGRepresentation(image);
        if (png == nil) {
            return -1;
        }
        NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:output]];
        return [png writeToURL:url atomically:YES] ? 0 : -1;
    }
}
