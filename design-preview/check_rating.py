"""Read-only checks and screenshots for the proposed rating page."""
import argparse
import asyncio
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import shutil
import threading
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
loader=importlib.util.spec_from_file_location('rating_server', ROOT/'design-preview/serve.py')
module=importlib.util.module_from_spec(loader)
loader.loader.exec_module(module)


async def run(output):
    output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),module.make_handler(ROOT/'design-preview/rating/analysis-snapshot.json',ROOT/'_runtime/pyodide'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}'
    page_url=base+'/design-preview/rating/'
    report={'viewports':[],'checks':[],'errors':[]}
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=shutil.which('chromium') or None,headless=True,args=['--no-sandbox'])
            page=await browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            page.on('pageerror',lambda e:report['errors'].append(str(e)))
            describe="""() => ({header:document.querySelector('body > header').innerHTML,
              headerBox:(()=>{const r=document.querySelector('body > header').getBoundingClientRect();return [r.x,r.y,r.width,r.height]})(),
              background:getComputedStyle(document.body).backgroundImage,
              color:getComputedStyle(document.body).backgroundColor})"""
            for width in [1440,1280,1100,1099,1024,768,390,360,320]:
                await page.set_viewport_size({'width':width,'height':1000 if width>=768 else 844})
                await page.goto(page_url+'before.html',wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                original=await page.evaluate(describe)
                if width in (1440,390):
                    await page.wait_for_timeout(1300)
                    await page.screenshot(path=str(output/f'before-{width}.png'))
                await page.goto(page_url+'after.html',wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                assert await page.evaluate(describe)==original, f'Header/background changed at {width}px'
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), width
                assert 'DEMO' in await page.locator('.hero-counter-mobile' if width<768 else '.hero-counter').inner_text()
                if width in (1440,390):await page.screenshot(path=str(output/f'after-{width}.png'))
                await page.locator('.show-full-list-trigger:visible').first.click()
                assert await page.locator('.full-list-row').count()==9
                assert await page.locator('.modal-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
                assert await page.locator('.modal-footer a').get_attribute('href')=='analysis.html'
                await page.keyboard.press('Escape')
                assert await page.locator('.show-full-list-trigger:visible').first.evaluate('(e)=>document.activeElement===e')
                report['viewports'].append({'width':width,'header_and_background':'unchanged','modal':'fits'})
            await page.set_viewport_size({'width':390,'height':844})
            await page.goto(page_url+'after.html',wait_until='networkidle')
            expected=await page.evaluate('mediaData.map(item=>item.name)')
            seen=[]
            for _ in range(9):
                seen.append(await page.locator('.media-card.is-active .media-name').inner_text())
                assert await page.locator('.media-card:not(.is-active)').evaluate_all('es=>es.every(e=>e.inert&&e.getAttribute("aria-hidden")==="true")')
                await page.locator('#ratingNext').click()
            assert seen==expected, (seen,expected)
            stable=await page.locator('.media-card.is-active .media-name').inner_text()
            await page.wait_for_timeout(5200)
            assert await page.locator('.media-card.is-active .media-name').inner_text()==stable
            await page.locator('.media-card.is-active .link-button').focus()
            await page.keyboard.press('Tab')
            assert await page.evaluate('document.activeElement.id')=='ratingPrev'
            report['checks'].append('all nine outlets in order; inactive slides inert; no autoplay; no hidden keyboard focus')
            await page.locator('.show-full-list-trigger:visible').first.click()
            await page.locator('#modalSearch').fill('Горизонт')
            assert await page.locator('.full-list-row').count()==1
            await page.locator('#modalSearch').fill('несуществующее название')
            assert 'Ничего не найдено' in await page.locator('#fullListContainer').inner_text()
            await page.locator('#modalSearch').fill('')
            await page.select_option('#modalSort','name-asc')
            assert await page.locator('.full-list-row').count()==9
            for _ in range(12):
                await page.keyboard.press('Tab')
                assert await page.evaluate('!!document.activeElement.closest("[role=dialog]")')
            await page.screenshot(path=str(output/'full-list-390.png'))
            await page.keyboard.press('Escape')
            assert not await page.locator('main').evaluate('(e)=>e.inert')
            report['checks'].append('full list search, empty state, sorting, focus containment and return; analysis link retained')
            await page.goto(page_url+'compare.html',wait_until='networkidle')
            await page.locator('[data-view="before"]').click()
            assert await page.locator('#beforePane').is_visible()
            await page.locator('[data-view="after"]').click()
            assert await page.locator('#afterPane').is_visible()
            assert not report['errors'],report['errors']
            await browser.close()
    finally:
        server.shutdown()
        (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/rating-preview-checks'))
    args=parser.parse_args()
    asyncio.run(run(args.output))
