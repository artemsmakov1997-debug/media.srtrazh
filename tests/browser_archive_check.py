"""Real archive data, exact evidence, legal annotations and unchanged row layout."""
import argparse
import copy
import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_strazh.analysis import analyze


def fixture(site):
    data = json.loads((Path(site) / 'data/analysis.json').read_text())
    data = copy.deepcopy(data)
    data['articles'] = []
    cases = [
        ('meduza', '⚡️ Ад на пороге <img src=x onerror=alert(1)>', 'Жители города обсуждают решение.'),
        ('mediazona_telegram', '', 'В публикации упоминается политзаключённый.'),
        ('rt', 'Открылась библиотека', 'В городе открылась новая библиотека.'),
        ('rt_telegram', '', 'Министр заявил: «Ад на пороге».'),
    ]
    for identifier, (source_id, title, text) in enumerate(cases, 1):
        source = next(s for s in data['sources'] if s['id'] == source_id)
        result = analyze({'title': title, 'text': text})
        data['articles'].append({
            'id': identifier, 'source_id': source_id, 'source': source['name'],
            'publisher_id': source['publisher_id'], 'platform': source['platform'],
            'title': title, 'message_preview': text[:160], 'display_excerpt': text,
            'published_at': '2026-10-27T07:00:00+00:00', 'retrieved_at': '2026-10-27T07:01:00+00:00',
            'url': 'https://t.me/' + source['channel'] + '/123' if source['platform'] == 'telegram'
                   else 'https://' + source['allowed_hosts'][0] + '/fixture/123',
            'algorithm_version': result['algorithm_version'], 'summary': result['summary'],
            'findings': result['findings'], 'findings_omitted': 0,
        })
    return data


def assert_rows_contain_content(page):
    # DOM presence alone misses flex items squeezed to their two-pixel borders.
    sizes = page.locator('.archive-item').evaluate_all('''items => items.map(item => {
      const row = item.querySelector('.archive-summary').getBoundingClientRect();
      const box = item.getBoundingClientRect();
      return {id:item.dataset.id, item:box.height, content:row.height,
              top:row.top-box.top, bottom:row.bottom-box.bottom};
    })''')
    assert sizes and all(s['content'] >= 30 and s['item'] >= s['content'] - 2
                         and s['top'] >= -2 and s['bottom'] <= 2 for s in sizes), sizes[:8]


def archive_ui(browser, base, site):
    data = fixture(site)
    screenshots = Path('/tmp/media-strazh-archive-checks'); screenshots.mkdir(exist_ok=True)
    for width in (320, 375, 390, 768, 1024, 1280, 1440):
        page = browser.new_page(viewport={'width': width, 'height': 900}, device_scale_factor=1)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/data/analysis.json', lambda route: route.fulfill(json=data))
        page.goto(base + '/archive/')
        page.wait_for_function('document.querySelectorAll(".archive-item").length === 4')
        assert page.locator('.archive-item').evaluate_all('(els) => els.map(el=>Number(el.dataset.id))') == [1,2,3,4]
        assert_rows_contain_content(page)
        assert 'демо' not in page.locator('#rtText').inner_text()
        assert page.locator('.archive-item[data-id="1"] .archive-publisher-status').all_text_contents() == ['иноагент', 'нежелательная организация']
        assert page.locator('.archive-item[data-id="2"] .archive-publisher-status').all_text_contents() == ['иноагент']
        assert page.locator('.archive-item[data-id="3"] .archive-publisher-status').count() == 0
        assert page.locator('.archive-item[data-id="4"]').get_attribute('data-status') == 'danger'
        assert '10:00 МСК' in page.locator('.cell-time').first.inner_text()
        assert page.locator('#archiveList img').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        page.locator('.chip[data-status="risky"]').click()
        assert page.locator('.archive-item').count() == 1
        assert page.locator('.archive-item').get_attribute('data-id') == '2'
        page.locator('.chip[data-status="neutral"]').click()
        assert page.locator('.archive-item').get_attribute('data-id') == '3'
        page.locator('.chip[data-status="all"]').click()
        page.locator('#searchInput').fill('политзаключённый')
        assert page.locator('.archive-item').get_attribute('data-id') == '2'
        page.locator('#searchInput').fill('')
        button = page.locator('.archive-item[data-id="1"] .more-btn')
        button.click()
        assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'false'
        assert page.locator('#modalFullText mark').first.inner_text() == 'Ад на пороге'
        assert 'не полный текст' in page.locator('#modalFullText').inner_text()
        assert page.locator('#modalOriginal a').get_attribute('href') == data['articles'][0]['url']
        assert page.locator('#modalMedia .archive-publisher-status').count() == 2
        page.locator('#modalFullText mark').first.click()
        assert 'Запугивание' in page.locator('#archiveMarkerNote').inner_text()
        assert 'они не доказывают манипуляцию' in page.locator('#modalExplain').inner_text()
        assert 'Отсутствие признаков не означает нейтральность текста.' in page.locator('#modalExplain').inner_text()
        page.keyboard.press('Escape')
        assert button.evaluate('(el)=>el===document.activeElement')
        page.screenshot(path=str(screenshots / f'archive-{width}.png'), full_page=True)
        assert not errors, errors
        page.close()

    # Match the production snapshot size. Four test rows fit the height cap
    # and cannot reveal the flex-shrink regression seen with 100 publications.
    full = copy.deepcopy(data)
    full['articles'] = [dict(copy.deepcopy(data['articles'][i % 4]), id=i+1) for i in range(100)]
    for width in (320, 375, 390, 768, 1024, 1280, 1440):
        page = browser.new_page(viewport={'width': width, 'height': 900}, device_scale_factor=1)
        page.route('**/data/analysis.json', lambda route: route.fulfill(json=full))
        page.goto(base + ('/archive.html' if width == 1024 else '/archive/'))
        page.wait_for_function('document.querySelectorAll(".archive-item").length === 100')
        assert_rows_contain_content(page)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        page.screenshot(path=str(screenshots / f'archive-100-{width}.png'))
        last = page.locator('.archive-item').last.locator('.more-btn')
        last.click()
        assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'false'
        page.keyboard.press('Escape')
        page.locator('.chip[data-status="danger"]').click()
        assert_rows_contain_content(page)
        page.locator('.chip[data-status="all"]').click()
        assert page.locator('.archive-item').count() == 100
        assert_rows_contain_content(page)
        page.close()

    page = browser.new_page()
    page.route('**/data/analysis.json', lambda route: route.fulfill(json=data))
    page.goto(base + '/archive/?publisher=mediazona')
    page.wait_for_selector('.archive-item')
    assert page.locator('.archive-item').count() == 1
    assert page.locator('.archive-item').get_attribute('data-publisher') == 'mediazona'
    page.close()
    # A bad source URL never becomes a clickable outbound link.
    bad = copy.deepcopy(data); bad['articles'][0]['url'] = 'javascript:alert(1)'
    page = browser.new_page(); page.route('**/data/analysis.json', lambda route: route.fulfill(json=bad))
    page.goto(base + '/archive.html'); page.wait_for_selector('.archive-item')
    page.locator('.more-btn').first.click()
    assert page.locator('#modalOriginal a').count() == 0
    page.close()
    # Bounded publication snippets may omit an active finding. The complete
    # summary must still prevent classification as a finding-free publication.
    omitted = copy.deepcopy(data); omitted['articles'][0]['findings'] = []
    omitted['articles'][0]['findings_omitted'] = 1
    omitted['articles'][1]['summary'] = None
    page = browser.new_page(); page.route('**/data/analysis.json', lambda route: route.fulfill(json=omitted))
    page.goto(base + '/archive/'); page.wait_for_selector('.archive-item')
    assert page.locator('.archive-item[data-id="1"]').get_attribute('data-status') == 'danger'
    assert page.locator('.archive-item[data-id="2"]').get_attribute('data-status') == 'pending'
    page.close()
    for payload in ({'schema_version': 'bad'}, None):
        page = browser.new_page()
        if payload is None: page.route('**/data/analysis.json', lambda route: route.fulfill(status=503, body='unavailable'))
        else: page.route('**/data/analysis.json', lambda route: route.fulfill(json=payload))
        page.goto(base + '/archive/')
        page.wait_for_function('document.querySelector("#rtText").textContent === "Данные анализа недоступны."')
        assert page.locator('.archive-item').count() == 0
        assert 'Не удалось загрузить реальные публикации' in page.locator('.empty-state').inner_text()
        page.close()
    # The published snapshot is also usable without fixture interception.
    page = browser.new_page(); page.goto(base + '/archive/')
    page.wait_for_selector('.archive-item')
    snapshot = json.loads((Path(site) / 'data/analysis.json').read_text())
    assert page.locator('.archive-item').count() == len(snapshot['articles'])
    assert_rows_contain_content(page)
    page.close()
    print(json.dumps({'archive_viewports': 7, 'real_snapshot_ids': 'passed', 'source_links_and_legal_labels': 'passed',
                      'unicode_evidence_and_touch': 'passed', 'no_fabricated_fallback': 'passed',
                      'full_100_row_heights_and_scrolling': 'passed'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.site.resolve()))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with sync_playwright() as playwright:
            options = {'args': ['--no-sandbox']}
            chromium = shutil.which('chromium') or shutil.which('chromium-browser')
            if chromium: options['executable_path'] = chromium
            browser = playwright.chromium.launch(**options)
            try: archive_ui(browser, 'http://127.0.0.1:' + str(server.server_port), args.site)
            finally: browser.close()
    finally: server.shutdown(); server.server_close()
