"""Synthetic reading-policy regression, with optional real Windows OCR smoke check."""
import base64
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from checks.module_support import load, sandbox

package = load('academic-assistant')
reader_module = sys.modules[package.Reader.__module__]


def fixture(folder):
    image = Image.new('RGB', (1200, 500), 'white')
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 54) if os.name == 'nt' else ImageFont.load_default(size=54)
    ImageDraw.Draw(image).text((60,100), 'SYNTHETIC HOMEWORK 42', font=font, fill='black')
    path = folder / 'scan.png'
    image.save(path)
    pdf = folder / 'scan.pdf'
    image.save(pdf, 'PDF', resolution=150)
    return path, pdf


def main():
    started = time.monotonic()
    def cancelled():
        if time.monotonic() - started > .3:
            raise HTTPException(409, 'Synthetic cancellation')
    try:
        reader_module.run_worker([sys.executable, '-c', 'import time; time.sleep(30)'], check=cancelled)
        raise AssertionError('A running worker must stop on cancellation')
    except HTTPException as error:
        assert error.status_code == 409 and time.monotonic() - started < 5
    with sandbox('academic-assistant') as context:
        source, pdf = fixture(context.data_dir)
        reader = package.Reader(context)
        body = package.Document(record_id='synthetic', limit=4)
        native, cache = context.data_dir / 'native.json', context.data_dir / 'pages.json'
        def read(path=source):
            return reader.read(path,native,cache,body,media_type='image/png',title=path.name,check=lambda:None)
        calls = []
        vision = {'ready':False, 'revision':'one'}
        context.ai.vision_settings = lambda:dict(vision)
        def visual(prompt, images, **kwargs):
            calls.append('vision')
            assert base64.b64decode(images[0]['data']).startswith(b'\x89PNG')
            return {'content':json.dumps({'text':'SYNTHETIC HOMEWORK 42','description':'A synthetic page.','uncertain':''})}
        context.ai.vision = visual
        with patch.object(reader_module,'local_ocr',return_value='LOCAL OCR 42') as ocr:
            value = read()
            assert value['pages'][0]['method']=='ocr' and not calls
            read()
            assert ocr.call_count==1, 'Unchanged page results must be cached'
            vision['ready']=True
            value=read()
            assert value['pages'][0]['method']=='vision' and value['pages'][0]['description']
            assert calls==['vision']
            reader_module.save_settings(context,reader_module.ReaderSettings(mode='local'))
            assert read()['pages'][0]['text']=='LOCAL OCR 42' and calls==['vision']
            reader_module.save_settings(context,reader_module.ReaderSettings(mode='auto'))
            def failed(*args,**kwargs):
                raise HTTPException(502,'Synthetic unsupported image input')
            context.ai.vision=failed
            value=read()
            assert value['pages'][0]['method']=='ocr' and any('回退' in text for text in value['pages'][0]['warnings'])
            # A transient vision failure must not become a permanent local cache entry.
            before=ocr.call_count
            read()
            assert ocr.call_count==before+1
            reader_module.save_settings(context,reader_module.ReaderSettings(fallback=False))
            try:
                read();raise AssertionError('Disabled fallback must preserve the vision error')
            except HTTPException as error:
                assert error.status_code==502
            def changed(*args,**kwargs):
                vision['revision']='two'
                return visual(*args,**kwargs)
            context.ai.vision=changed
            before=cache.read_text(encoding='utf-8')
            try:
                read();raise AssertionError('Changing configuration must invalidate in-flight results')
            except HTTPException as error:
                assert error.status_code==409
            assert cache.read_text(encoding='utf-8')==before
            reader.stopped.set()
            try:
                read();raise AssertionError('Stopped modules must not read documents')
            except HTTPException as error:
                assert error.status_code==409
            reader.stopped.clear()
            reader_module.save_settings(context,reader_module.ReaderSettings(mode='local'))
            native.unlink()
            cache.unlink(missing_ok=True)
            value=read(pdf)
            assert value['kind']=='pdf' and value['pages'][0]['method']=='ocr', value
        if '--live-ocr' in sys.argv:
            native.unlink()
            cache.unlink(missing_ok=True)
            value=read(pdf)
            assert '42' in value['pages'][0]['text'], value
            assert value['pages'][0]['method']=='ocr'
            print('PASS: real scanned PDF rendering and Windows OCR read synthetic text')
        if '--docling-python' in sys.argv:
            python=sys.argv[sys.argv.index('--docling-python')+1]
            reader_module.save_settings(context,reader_module.ReaderSettings(mode='local',ocr_backend='docling',docling_python=python))
            native.unlink(missing_ok=True)
            value=read(pdf)
            assert '42' in value['pages'][0]['text'], value
            print('PASS: real Docling reads a synthetic scanned PDF page')
    print('PASS: local/vision selection, quality gating, page caches, opt-out, fallback, retry, stale configuration and scanned PDF rendering')


if __name__=='__main__':
    main()
