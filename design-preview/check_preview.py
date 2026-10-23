"""Functional and viewport checks for the isolated design preview, without changing source pages."""
import argparse
import asyncio
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_strazh.analysis import analyze
from media_strazh.browser import DEFAULT_RUNTIME, runtime_assets
from playwright.async_api import async_playwright

loader = importlib.util.spec_from_file_location('preview_server', ROOT / 'design-preview/serve.py')
module = importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)


async def run(runtime, output):
    runtime_assets(runtime)
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), module.make_handler(ROOT / 'design-preview/analysis/snapshot.json', runtime))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    prefix = base + '/design-preview/analysis/'
    results = {'viewports': [], 'functional': [], 'errors': [], 'external_requests': []}
    document = {'title': '', 'text': 'Все знают: нас ждёт неминуемая катастрофа. Представители киевского режима снова обвиняют всех вокруг.'}
    expected = analyze(document)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=__import__('shutil').which('chromium') or None, headless=True, args=['--no-sandbox'])
            context = await browser.new_context(viewport={'width':1440, 'height':1000}, accept_downloads=True, reduced_motion='reduce')
            page = await context.new_page()
            page.on('pageerror', lambda error: results['errors'].append(str(error)))
            page.on('request', lambda request: results['external_requests'].append(request.url) if not request.url.startswith(base) else None)
            for width in [1440, 1280, 1100, 1099, 1024, 768, 390, 360, 320]:
                await page.set_viewport_size({'width':width, 'height':1000 if width >= 768 else 844})
                await page.goto(prefix+'before.html', wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                await page.wait_for_selector('.publication')
                original_dates = [text.removeprefix('Дата публикации: ')
                                  for text in await page.locator('.publication > p.muted').all_text_contents()]
                original = await page.evaluate("""() => ({
                  zoom:getComputedStyle(document.body).zoom,
                  header:document.querySelector('.site-header').innerHTML,
                  modes:document.querySelector('.analysis-tabs').innerHTML,
                  boxes:[...document.querySelectorAll('.site-header,.header-inner,.brand,.header-back,.analysis-tabs,.mode-card'+(innerWidth>760?',#controls,#source,#platform,#marker':''))].map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:r.x,y:r.y,w:r.width,h:r.height,font:s.font,fontSize:s.fontSize,padding:s.padding,gap:s.gap};})
                })""")
                if width in (1440, 390):
                    await page.screenshot(path=str(output/f'before-{width}.png'))
                await page.goto(prefix+'after.html', wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                await page.wait_for_selector('.publication')
                measure = await page.evaluate("""() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,zoom:getComputedStyle(document.body).zoom,firstResultY:document.querySelector('.publication').getBoundingClientRect().y,visible:[...document.querySelectorAll('.publication')].filter(e=>!e.hidden).length,total:document.querySelectorAll('.publication').length})""")
                assert measure['scroll'] <= width, measure
                preserved = await page.evaluate("""() => ({
                  zoom:getComputedStyle(document.body).zoom,
                  header:document.querySelector('.site-header').innerHTML,
                  modes:document.querySelector('.analysis-tabs').innerHTML,
                  boxes:[...document.querySelectorAll('.site-header,.header-inner,.brand,.header-back,.analysis-tabs,.mode-card'+(innerWidth>760?',#controls,#source,#platform,#marker':''))].map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:r.x,y:r.y,w:r.width,h:r.height,font:s.font,fontSize:s.fontSize,padding:s.padding,gap:s.gap};})
                })""")
                assert preserved == original, f'Original header or mode layout changed at {width}px'
                assert measure['visible'] == measure['total'], measure
                dates = await page.locator('.publication').evaluate_all("""cards => cards.map(card => {
                  const time=card.querySelector('.publication-time'),source=card.querySelector('.publication-meta'),title=card.querySelector('.publication-title');
                  const c=card.getBoundingClientRect(),t=time.getBoundingClientRect(),s=source.getBoundingClientRect();
                  const clock=time.querySelector('.publication-time-clock');
                  return {value:time.querySelector('.publication-time-date').textContent+(clock?', '+clock.textContent:''),
                    contained:t.left>=c.left&&t.right<=c.right&&t.top>=c.top,
                    topRight:c.right-t.right<=24&&t.top-c.top<=24,
                    beforeTitle:t.bottom<=title.getBoundingClientRect().top,
                    sourceSeparate:s.right<=t.left,
                    hiddenLabel:getComputedStyle(time.querySelector('.publication-time-context')).clipPath==='inset(50%)'};
                })""")
                assert [item['value'] for item in dates] == original_dates, 'Published time must stay unchanged'
                assert all(all(item[key] for key in ['contained','topRight','beforeTitle','sourceSeparate','hiddenLabel']) for item in dates), (width, dates)
                assert await page.locator('.page-heading,.manual-guidance,#listPagination,#sourceDetailsToggle').count() == 0
                measure['original_header_and_modes'] = 'identical'
                measure['publication_dates'] = 'original values, top right, no overlap or visible label'
                results['viewports'].append(measure)
                if width in (1440, 390):
                    await page.screenshot(path=str(output/f'after-{width}.png'))

            await page.set_viewport_size({'width':1440, 'height':1000})
            await page.goto(prefix+'before.html', wait_until='networkidle')
            before_count = await page.locator('.publication').count()
            await page.select_option('#source', 'rt')
            before_rt = await page.locator('.publication-title').all_text_contents()
            await page.goto(prefix+'after.html', wait_until='networkidle')
            assert await page.locator('.publication').count() == before_count
            await page.select_option('#source', 'rt')
            assert await page.locator('.publication-title').all_text_contents() == before_rt
            await page.select_option('#source', '')
            assert await page.locator('.publication').count() == before_count
            assert await page.locator('.publication:visible').count() == before_count
            results['functional'].append('same data and filtered publications as original; reset; original full list')
            await page.locator('.auto-details-button').first.click()
            assert await page.locator('#automaticModal').is_visible()
            await page.keyboard.press('Shift+Tab')
            assert await page.evaluate('!!document.activeElement.closest("[role=dialog]")')
            await page.keyboard.press('Escape')
            assert not await page.locator('#automaticModal').is_visible()
            assert await page.locator('.auto-details-button').first.evaluate('(e)=>document.activeElement===e')
            results['functional'].append('original evidence modal; focus containment and restoration')
            await page.locator('[data-mode="manual"]').click()
            await page.locator('#manualText').fill(document['text'])
            await page.screenshot(path=str(output/'manual-input-1440.png'))
            await page.locator('#manualSubmit').click()
            await page.wait_for_selector('#manualResult:visible', timeout=45000)
            assert await page.locator('#manualTextEvidence mark').count() > 0
            async with page.expect_download() as download_info:
                await page.locator('#manualDownload').click()
            download = await download_info.value
            got = json.loads(Path(await download.path()).read_text())
            assert got == expected, 'The preview must preserve Python/Wasm result parity.'
            await page.locator('#manualTextEvidence mark').first.hover()
            assert await page.locator('#manualTooltip').is_visible()
            await page.screenshot(path=str(output/'manual-result-1440.png'))
            await page.locator('#manualEdit').click()
            assert await page.locator('#manualText').input_value() == document['text']
            await page.locator('button[type="reset"]').click()
            assert await page.locator('#manualText').input_value() == ''
            assert await page.locator('#manualSubmit').is_enabled()
            results['functional'].append('real Wasm analysis; exact Python/JSON parity; tooltip; edit; clear')

            touch = await browser.new_context(viewport={'width':390,'height':844}, has_touch=True, reduced_motion='reduce')
            mobile = await touch.new_page()
            await mobile.goto(prefix+'after.html', wait_until='networkidle')
            assert not await mobile.locator('#filterPanel').get_attribute('open')
            await mobile.locator('#filterPanel summary').click()
            await mobile.select_option('#source', 'tass'); await mobile.select_option('#platform', 'website')
            assert 'нет публикаций' in await mobile.locator('#articles').inner_text()
            await mobile.locator('#resetFilters').click()
            await mobile.locator('[data-mode="manual"]').tap()
            await mobile.locator('#manualText').fill(document['text'])
            await mobile.screenshot(path=str(output/'manual-input-390.png'))
            await mobile.locator('#manualSubmit').tap()
            await mobile.wait_for_selector('#manualResult:visible', timeout=45000)
            await mobile.locator('#manualTextEvidence mark').first.tap()
            box = await mobile.locator('#manualTooltip').bounding_box()
            assert box and box['x'] >= 0 and box['x'] + box['width'] <= 390
            assert await mobile.locator('#manualWarnings').is_visible()
            await mobile.screenshot(path=str(output/'manual-result-390.png'))
            results['functional'].append('mobile filter disclosure; empty filter; touch tooltip; warnings')
            await mobile.locator('[data-mode="automatic"]').tap()
            await mobile.locator('.auto-details-button').first.tap()
            await mobile.screenshot(path=str(output/'detail-390.png'))
            await mobile.keyboard.press('Escape')

            await page.emulate_media(reduced_motion='reduce')
            await page.goto(prefix+'after.html', wait_until='networkidle')
            await page.locator('.auto-details-button').first.click()
            assert await page.evaluate('document.getAnimations().length') == 0
            results['functional'].append('reduced motion has no running UI animation')
            await page.keyboard.press('Escape')
            await page.goto(prefix+'compare.html', wait_until='networkidle')
            await page.locator('[data-view="before"]').click()
            assert await page.locator('#beforePane').is_visible()
            assert not await page.locator('#afterPane').is_visible()
            await page.locator('[data-view="split"]').click()
            assert await page.locator('#beforePane').is_visible() and await page.locator('#afterPane').is_visible()
            await page.locator('[data-size="phone"]').click()
            assert await page.locator('#afterPane').evaluate('(e)=>e.getBoundingClientRect().width') == 390
            results['functional'].append('before/after/split comparison and phone size')

            fixture = json.loads((ROOT/'design-preview/analysis/snapshot.json').read_text())
            item = fixture['articles'][0]
            item['published_at'] = None
            item['source'] = 'Очень длинное название редакции для проверки переноса строк · Telegram'
            marked_source = next(source for source in fixture['sources'] if source.get('publisher_id') == 'meduza')
            item['source_id'] = marked_source['id']
            fixture['articles'] = [item]
            await page.route('**/data/analysis.json', lambda route: route.fulfill(json=fixture))
            await page.set_viewport_size({'width':320,'height':844})
            await page.goto(prefix+'after.html', wait_until='networkidle')
            assert await page.locator('.publication-time-date').inner_text() == 'не указана'
            assert await page.locator('.publication-time-clock').count() == 0
            assert await page.locator('.legal-status-tag').count() > 0
            assert await page.evaluate("""() => {
              const card=document.querySelector('.publication'),time=card.querySelector('.publication-time').getBoundingClientRect();
              return document.documentElement.scrollWidth<=innerWidth && [...card.querySelectorAll('.publication-meta,.legal-status-tag')].every(e=>e.getBoundingClientRect().right<=time.left);
            }""")
            results['functional'].append('missing publication date and long source with legal badges fit at 320px')
            assert not results['errors'], results['errors']
            assert not results['external_requests'], results['external_requests']
            await browser.close()
    finally:
        server.shutdown()
        (output/'checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--output', type=Path, default=ROOT/'design-preview/checks')
    args = parser.parse_args()
    asyncio.run(run(args.runtime, args.output))
