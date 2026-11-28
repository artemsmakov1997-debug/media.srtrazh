"""Real local photo uploads, crop evidence, caption engine, privacy and responsive PRO."""
import binascii
import functools
import http.server
import json
from pathlib import Path
import shutil
import struct
import threading
import zlib


def png(width, height, rectangle=None, invert=False):
    import math
    x0, y0 = rectangle or (0, 0)
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        for col in range(width):
            x, y = col + x0, row + y0
            values = [110 + 65 * math.sin(x * .13) + 45 * math.cos(y * .19),
                      120 + 75 * math.cos(x * .09 + y * .12), 115 + 80 * math.sin(y * .14 - x * .1)]
            if 48 < x < 105 and 30 < y < 79:
                values = [210, 65 + y, 35 + x]
            rgb = [max(0, min(255, round(v))) for v in values]
            raw.extend(255 - v if invert else v for v in rgb)
    def chunk(tag, value):
        return struct.pack('>I', len(value)) + tag + value + struct.pack('>I', binascii.crc32(tag + value) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def photo_ui(browser, base):
    output = Path('/tmp/photo-context-checks'); output.mkdir(exist_ok=True)
    full, clipped = png(160, 120), png(96, 72, (32, 24))
    upload = lambda name, value: {'name': name, 'mimeType': 'image/png', 'buffer': value}
    context = browser.new_context(viewport={'width': 1280, 'height': 950}, has_touch=True,
                                  accept_downloads=True, reduced_motion='reduce')
    errors, requests = [], []
    try:
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append((request.method, request.url, request.post_data)))
        page.goto(base + '/analysis/#photo')
        page.evaluate('document.fonts.ready')
        assert page.locator('#photoPanel').is_visible()
        assert page.locator('[data-mode=photo]').get_attribute('aria-selected') == 'true'
        caption = '⚡ Фото, которое никогда не опубликуют официальные российские каналы. Потому что оно реальное, а не пропущенное через 200 фильтров. <script>window.photoLeak=1</script>'
        page.locator('#photoFile').set_input_files(upload('private-publication-photo.png', clipped))
        page.locator('#photoReference').set_input_files(upload('private-comparison-photo.png', full))
        page.locator('#photoPublicationPreview').wait_for(state='visible')
        page.locator('#photoReferencePreview').wait_for(state='visible')
        page.locator('#photoCaption').fill(caption)
        page.locator('.photo-context-fields summary').click()
        source = 'https://example.org/private-photo-source?draft=not-sent'
        page.locator('#photoSource').fill(source)
        page.locator('#photoPublished').fill('2026-11-28')
        page.locator('#photoSubmit').click()
        page.locator('#photoResult').wait_for(state='visible', timeout=120000)
        assert page.locator('#photoComparison h3').inner_text() == 'Найдена возможная общая область'
        assert page.locator('.photo-crop-box').is_visible()
        assert '36%' in page.locator('#photoComparison').inner_text()
        assert page.locator('#photoCaptionEvidence').inner_text() == caption
        assert page.locator('#photoCaptionEvidence script').count() == 0
        assert not page.evaluate('window.photoLeak')
        assert page.locator('#photoCaptionEvidence .photo-trigger').count() >= 3
        page.locator('#photoCaptionEvidence .photo-trigger').first.tap()
        assert page.locator('#photoCueNote').is_visible()
        assert page.locator('#photoCueNote strong').count() >= 1
        assert page.locator('#photoSourceLink a').get_attribute('href') == source
        assert page.locator('#photoError').is_hidden()
        with page.expect_download() as download:
            page.locator('#photoDownload').click()
        report = json.loads(Path(download.value.path()).read_text())
        assert report['schema_version'] == 'photo-context-1.0'
        assert report['affects_rating'] is False and report['semantic_image_analysis'] is False
        assert report['comparison']['kind'] == 'crop_candidate'
        assert report['caption']['status'] == 'complete'
        assert report['caption']['algorithm_version']
        assert report['image']['width'] == 96 and report['reference']['height'] == 120
        assert len(report['image']['sha256']) == 64
        for finding in report['caption']['findings']:
            for evidence in finding['evidence']:
                assert caption[evidence['start']:evidence['end']] == evidence['quote']
        # All copy, controls and preview boxes fit; fifth tab spans the phone row.
        for width in (320, 390, 768, 1280, 1920):
            page.set_viewport_size({'width': width, 'height': 950})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), width
            for selector in ('#photoSubmit', '#photoDownload', '.photo-upload-grid', '#photoCaptionEvidence'):
                assert page.locator(selector).evaluate('el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1}'), (width, selector)
            if width < 721:
                tab = page.locator('[data-mode=photo]').bounding_box()
                tabs = page.locator('.analysis-tabs').bounding_box()
                assert abs(tab['width'] - tabs['width']) < 2
            else:
                ys = page.locator('.analysis-tabs button').evaluate_all('els=>els.map(el=>el.getBoundingClientRect().top)')
                assert max(ys) - min(ys) < 2
            labels = page.locator('.analysis-tabs button').evaluate_all('''els=>els.map(el=>{
                const box=el.getBoundingClientRect(),range=document.createRange();
                range.selectNodeContents(el.querySelector('strong'));
                const r=range.getBoundingClientRect();return r.left>=box.left&&r.right<=box.right;
            })''')
            assert all(labels), (width, labels)
            if width in (390, 1280):
                page.screenshot(path=str(output / f'photo-result-{width}.png'), full_page=True)
        # Removing a reference invalidates old findings and removes its frame.
        page.locator('#photoRemoveReference').click()
        assert page.locator('#photoResult').is_hidden()
        assert page.locator('#photoReferencePreview').is_hidden()
        page.locator('#photoCaption').fill('')
        page.locator('#photoSubmit').click(); page.locator('#photoResult').wait_for()
        assert 'Для сравнения нужен второй снимок' in page.locator('#photoComparison').inner_text()
        assert 'Подпись не добавлена' in page.locator('#photoCaptionStatus').inner_text()
        page.locator('#photoReference').set_input_files(upload('same-bytes-new-name.png', clipped))
        page.locator('#photoReferencePreview').wait_for(); page.locator('#photoSubmit').click(); page.locator('#photoResult').wait_for()
        assert page.locator('#photoComparison h3').inner_text() == 'Загружен один и тот же файл'
        # Actual browser encoders, not just hand-built format headers.
        for mime, label in [('image/jpeg', 'JPEG'), ('image/webp', 'WebP')]:
            encoded = page.evaluate('''async p=>{
                const bitmap=await createImageBitmap(new Blob([new Uint8Array(p.bytes)],{type:'image/png'}));
                const canvas=new OffscreenCanvas(bitmap.width,bitmap.height);
                canvas.getContext('2d').drawImage(bitmap,0,0);bitmap.close();
                const blob=await canvas.convertToBlob({type:p.mime,quality:.85});
                return Array.from(new Uint8Array(await blob.arrayBuffer()));
            }''', {'bytes': list(clipped), 'mime': mime})
            page.locator('#photoFile').set_input_files({'name': 'encoded-photo', 'mimeType': mime, 'buffer': bytes(encoded)})
            page.wait_for_function('format=>document.querySelector("#photoPublicationPreview").textContent.includes(format)', arg=label)
            page.locator('#photoReference').set_input_files(upload('full-source.png', full))
            page.locator('#photoReferencePreview').wait_for(); page.locator('#photoSubmit').click(); page.locator('#photoResult').wait_for()
            assert page.locator('#photoComparison h3').inner_text() == 'Найдена возможная общая область', label
        # Tall photos stay compact; the reference frame uses the image's true box.
        portrait = png(80, 400)
        page.locator('#photoFile').set_input_files(upload('portrait.png', portrait))
        page.locator('#photoReference').set_input_files(upload('portrait-reference.png', portrait))
        page.locator('#photoPublicationPreview').wait_for(); page.locator('#photoReferencePreview').wait_for()
        for selector in ('#photoPublicationPreview img', '#photoReferencePreview .photo-reference-image'):
            box = page.locator(selector).bounding_box()
            assert box['height'] <= 361 and abs(box['width'] / box['height'] - .2) < .01, (selector, box)
        # A renamed SVG is rejected by its actual bytes, never inserted as markup.
        page.locator('#photoFile').set_input_files(upload('disguised.png', b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>'))
        page.locator('#photoPublicationError').wait_for()
        assert 'JPEG, PNG и WebP' in page.locator('#photoPublicationError').inner_text()
        assert page.locator('#photoResult').is_hidden()
        page.locator('#photoFile').set_input_files(upload('too-big.png', bytes(12 * 1024 * 1024 + 1)))
        page.wait_for_function("document.querySelector('#photoPublicationError').textContent.includes('12 МБ')")
        page.locator('#photoReset').click()
        assert page.locator('#photoFile').input_value() == ''
        assert page.locator('#photoCaption').input_value() == ''
        assert page.locator('#photoResult').is_hidden()
        # Images and captions never enter outgoing payloads or source URL requests.
        from urllib.parse import unquote
        assert all(method == 'GET' and payload is None and caption not in unquote(url) and source not in url and
                   'private-publication-photo' not in url and 'private-comparison-photo' not in url
                   for method, url, payload in requests), requests
        assert not errors, errors
    finally:
        context.close()

    # Actual mobile touch and graceful caption-engine failure; no fake "all clear".
    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                                  accept_downloads=True, reduced_motion='reduce')
    try:
        page = context.new_page()
        page.route('**/manual-worker.js', lambda route: route.abort())
        page.goto(base + '/analysis/#photo')
        page.locator('#photoFile').set_input_files(upload('phone.png', full))
        page.locator('#photoPublicationPreview').wait_for()
        page.locator('#photoCaption').fill('Фото, которое никогда не опубликуют официальные каналы. 200 фильтров.')
        page.locator('#photoSubmit').tap(); page.locator('#photoResult').wait_for()
        assert 'Применены только специальные правила' in page.locator('#photoCaptionStatus').inner_text()
        assert 'частично' in page.locator('#photoState').inner_text()
        page.locator('#photoCaptionEvidence .photo-trigger').last.tap()
        assert 'обработки' in page.locator('#photoCueNote').inner_text()
        # A stalled analysis can be cancelled, and cannot resurrect stale results.
        page.unroute('**/manual-worker.js')
        page.route('**/manual-worker.js', lambda route: route.fulfill(content_type='text/javascript', body='self.onmessage=()=>{};'))
        page.locator('#photoCaption').fill('Текст для проверки отмены.')
        with page.expect_event('worker'):
            page.locator('#photoSubmit').tap()
        assert page.locator('#photoSubmit').is_disabled()
        page.locator('#photoReset').tap()
        assert page.locator('#photoSubmit').is_enabled()
        assert page.locator('#photoResult').is_hidden()
        assert page.locator('#photoPublicationPreview img').get_attribute('src') is None
        page.locator('#photoFile').set_input_files(upload('retry.png', full))
        page.locator('#photoPublicationPreview').wait_for()
        page.locator('#photoCaption').fill('Повторная проверка отмены.')
        with page.expect_event('worker'):
            page.locator('#photoSubmit').tap()
        page.locator('[data-mode=stories]').tap()
        page.locator('[data-mode=photo]').tap()
        assert page.locator('#photoSubmit').is_enabled()
        assert 'остановлена' in page.locator('#photoState').inner_text()
        page.locator('#photoCaption').fill('')
        page.locator('#photoSubmit').tap(); page.locator('#photoResult').wait_for()
        assert 'Подпись не добавлена' in page.locator('#photoCaptionStatus').inner_text()
    finally:
        context.close()
    # Force an old decode to finish after its replacement: the latest file wins.
    context = browser.new_context(viewport={'width': 1280, 'height': 900}, reduced_motion='reduce')
    try:
        page = context.new_page()
        original_worker = (Path(__file__).resolve().parents[1] / 'photo-image-worker.js').read_text()
        prefix = '''const decodeOriginal=self.createImageBitmap.bind(self);
            self.createImageBitmap=async(...args)=>{
                const wait=args[0].size===OLD_FILE_SIZE?350:0;
                const result=await decodeOriginal(...args);
                if(wait)await new Promise(resolve=>setTimeout(resolve,wait));return result;
            };\n'''
        prefix = prefix.replace('OLD_FILE_SIZE', str(len(full)))
        page.route('**/photo-image-worker.js*', lambda route: route.fulfill(content_type='text/javascript', body=prefix + original_worker))
        page.goto(base + '/analysis/#photo')
        page.locator('#photoFile').set_input_files(upload('old.png', full))
        page.locator('#photoFile').set_input_files(upload('latest.png', clipped))
        page.locator('#photoReference').set_input_files(upload('latest-copy.png', clipped))
        page.wait_for_function("document.querySelector('#photoPublicationPreview').textContent.includes('latest.png')")
        page.locator('#photoReferencePreview').wait_for()
        # Allow the delayed old result to arrive before checking the stored pixels.
        page.wait_for_timeout(400)
        page.locator('#photoSubmit').click(); page.locator('#photoResult').wait_for()
        assert '96 × 72' in page.locator('#photoFacts').inner_text()
        assert page.locator('#photoComparison h3').inner_text() == 'Загружен один и тот же файл'
    finally:
        context.close()
    print('Photo PRO: local JPEG/PNG/WebP uploads, crop frame, file identity, Python caption rules, Unicode/XSS safety, private data not transmitted, mobile touch, cancellation and partial analysis passed', flush=True)


if __name__ == '__main__':
    import argparse
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True, type=Path)
    args = parser.parse_args()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(args.site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
            photo_ui(browser, f'http://127.0.0.1:{server.server_port}')
            browser.close()
    finally:
        server.shutdown(); server.server_close()
