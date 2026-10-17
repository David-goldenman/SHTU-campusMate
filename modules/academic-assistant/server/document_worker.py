"""Bounded local parsing/rendering worker; receives only a private job-file path."""
import json
import math
import sys
from pathlib import Path


def render(job, root):
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 40_000_000
    results = []
    if job['kind'] == 'pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(job['input']) as pdf:
            for number in job['pages']:
                page = pdf[number - 1]
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
                        raise ValueError('Invalid page dimensions')
                    bitmap = page.render(scale=min(2.5, 2200 / max(width, height)))
                    try:
                        image = bitmap.to_pil().convert('RGB')
                        target = root / f'page-{number}.png'
                        image.save(target)
                        image.close()
                        results.append({'page': number, 'file': str(target)})
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    elif job['kind'] == 'image':
        with Image.open(job['input']) as source:
            if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('Image dimensions exceeded')
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((2200, 2200))
            target = root / 'page-1.png'
            image.save(target)
            image.close()
            results.append({'page': 1, 'file': str(target)})
    return results


def main():
    path = Path(sys.argv[1])
    job = json.loads(path.read_text(encoding='utf-8'))
    if job['operation'] == 'native':
        from documents import extract
        result = extract(Path(job['input']).read_bytes(), job['media_type'], job['title'], allow_empty=True)
    elif job['operation'] == 'render':
        result = {'images': render(job, path.parent)}
    elif job['operation'] == 'docling':
        from docling.document_converter import DocumentConverter
        # Docling's local defaults do not enable remote model services.
        converted = DocumentConverter().convert(Path(job['input']))
        result = {'text': converted.document.export_to_markdown()[:20000]}
    else:
        raise ValueError('Unknown operation')
    Path(job['output']).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
