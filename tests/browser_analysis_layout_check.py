"""Check accepted metadata, always-visible filters and source-button alignment."""
import argparse
import asyncio
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
from playwright.async_api import async_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def run(site, output):
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    report = {'viewports': [], 'errors': []}
    snapshot = json.loads((site/'data/analysis.json').read_text())
    expected_dates = [item['published_at'] for item in snapshot['articles'] if item.get('findings')]
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=shutil.which('chromium') or None,
                                              headless=True, args=['--no-sandbox'])
            page = await browser.new_page(reduced_motion='reduce')
            page.on('pageerror', lambda error: report['errors'].append(str(error)))
            for width in [1440,1280,1100,1099,1024,768,390,360,320]:
                await page.set_viewport_size({'width':width,'height':1000 if width>760 else 844})
                await page.goto(base+'/analysis.html', wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                await page.wait_for_selector('.publication-time')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                dates = await page.locator('.publication').evaluate_all("""cards=>cards.map(card=>{
                  const time=card.querySelector('.publication-time'),source=card.querySelector('.publication-meta');
                  const t=time.getBoundingClientRect(),s=source.getBoundingClientRect(),c=card.getBoundingClientRect();
                  const link=card.querySelector('.source-link');
                  return {label:time.textContent,iso:time.getAttribute('datetime'),tag:time.tagName,
                    contains:t.left>=c.left&&t.right<=c.right&&t.top>=c.top,
                    separate:s.right<=t.left,aboveTitle:t.bottom<=card.querySelector('.publication-title').getBoundingClientRect().top,
                    dateHeight:t.height,background:getComputedStyle(time).backgroundColor,border:getComputedStyle(time).borderTopWidth,
                    aligned:!link||Math.abs(link.getBoundingClientRect().right-t.right)<1};
                })""")
                assert len(dates) == len(expected_dates)
                for row, raw in zip(dates, expected_dates):
                    assert row['contains'] and row['separate'] and row['aboveTitle'], (width,row)
                    assert row['background'] == 'rgba(0, 0, 0, 0)' and row['border'] == '0px', (width,row)
                    assert (row['tag']=='TIME' and row['iso']) if raw else (row['tag']=='SPAN' and row['iso'] is None)
                    if width<=760:
                        assert row['aligned'] and row['dateHeight']<=40, (width,row)
                if width<=760:
                    assert await page.locator('#filterPanel summary').count()==0
                    for field in ['#source','#platform','#marker']:
                        assert await page.locator(field).is_visible()
                    await page.select_option('#source','rt')
                    await page.select_option('#platform','website')
                    await page.select_option('#marker','clickbait')
                    assert await page.locator('#resetFilters').is_enabled()
                    await page.locator('#resetFilters').click()
                    assert await page.locator('.publication').count()==len(expected_dates)
                    assert await page.locator('#resetFilters').is_disabled()
                    assert await page.locator('#platform').input_value()==''
                    assert await page.locator('#marker').input_value()==''
                else:
                    assert await page.locator('#source').is_visible()
                report['viewports'].append({'width':width,'cards':len(dates),'dates':'top right','filters':'always visible','mobile_alignment':'passed' if width<=760 else 'original'})
                if width in (1440,390):
                    await page.screenshot(path=str(output/f'analysis-{width}.png'))
            assert not report['errors'], report['errors']
            await browser.close()
    finally:
        server.shutdown()
        (output/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path('/tmp/analysis-layout-checks'))
    args=parser.parse_args()
    asyncio.run(run(args.site.resolve(),args.output))
