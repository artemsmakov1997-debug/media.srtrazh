"""Browser filters select authentic platform variants while displaying one copy."""

import json
from pathlib import Path
import tempfile

from media_strazh.publishing import snapshot
from media_strazh.storage import Store
from test_crossposts import FLAGGED
from test_rating import save_publication


def crosspost_ui(browser, base, site, errors):
    with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / 'copies.sqlite3') as store:
        save_publication(store, 1, text=FLAGGED)
        save_publication(store, 2, 'rt_telegram', text=FLAGGED)
        save_publication(store, 3, 'rt_telegram', text=FLAGGED + ' Затем опубликовано отдельное сообщение.')
        data = snapshot(store)
    assert len(data['articles']) == 2 and data['deduplication']['duplicates_excluded'] == 1
    screenshots = Path('/tmp/media-strazh-archive-checks'); screenshots.mkdir(exist_ok=True)
    for width in (320, 1280):
        context = browser.new_context(viewport={'width': width, 'height': 900},
                                      is_mobile=width == 320, has_touch=width == 320)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/data/analysis.json', lambda route: route.fulfill(json=data))
        try:
            for route, selector in (('/analysis/', '.publication'), ('/archive/', '.archive-item')):
                page.goto(base + route)
                page.wait_for_function('(selector) => document.querySelectorAll(selector).length === 2', arg=selector)
                for platform, count, prefix in (('website', 1, 'https://russiatoday.ru/'),
                                                 ('telegram', 2, 'https://t.me/'), ('', 2, None)):
                    page.select_option('#platform', platform)
                    assert page.locator(selector).count() == count, (route, width, platform)
                    if prefix:
                        urls = page.locator(selector + ' .source-link').evaluate_all('(links) => links.map(link=>link.href)')
                        assert len(urls) == count and all(url.startswith(prefix) for url in urls), urls
                details = page.locator(selector + (' .auto-details-button' if route == '/analysis/' else ' .more-btn')).first
                details.tap() if width == 320 else details.click()
                modal = '#automaticModal' if route == '/analysis/' else '#messageModalOverlay'
                page.locator(modal + ' mark').first.wait_for()
                close = '#automaticModalClose' if route == '/analysis/' else '#messageCloseBtn'
                page.locator(close).tap() if width == 320 else page.locator(close).click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (width, route)
                page.screenshot(path=str(screenshots / ('crossposts-' + route.strip('/') + '-' + str(width) + '.png')))
            assert page.evaluate('''() => {
                const raw={id:1,publication_id:'p',publisher_id:'rt',platform:'website',variants:[
                  {id:2,publication_id:'other',publisher_id:'rt',platform:'telegram'}]};
                try {PublicationGroups.candidates([raw]); return false;} catch {return true;}
            }''')
        finally:
            context.close()
    print('Cross-platform copies: one card, authentic website/Telegram filters, desktop + touch passed', flush=True)
