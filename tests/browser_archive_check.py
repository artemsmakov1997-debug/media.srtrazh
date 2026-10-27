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
        assert page.locator('.chip,.cell-category').count() == 0
        for selector in ('#source', '#platform', '#marker'):
            assert page.locator(selector).is_visible()
        assert 'демо' not in page.locator('#rtText').inner_text()
        assert page.locator('.archive-item[data-id="1"] .archive-publisher-status').all_text_contents() == ['иноагент', 'нежелательная организация']
        assert page.locator('.archive-item[data-id="2"] .archive-publisher-status').all_text_contents() == ['иноагент']
        assert page.locator('.archive-item[data-id="3"] .archive-publisher-status').count() == 0
        assert page.locator('.archive-platform').count() == 0
        assert page.locator('.archive-item[data-id="4"]').get_attribute('data-status') == 'danger'
        assert '10:00:00 МСК' in page.locator('.cell-time').first.inner_text()
        assert page.locator('.publication-time-clock').first.inner_text() == '10:00:00 МСК'
        assert page.locator('.publication-time-date').first.inner_text() == '27.10.2026'
        assert page.locator('.archive-item .publication-time').first.evaluate(
            'el => {const clock=el.querySelector(".publication-time-clock").getBoundingClientRect();'
            'const date=el.querySelector(".publication-time-date").getBoundingClientRect();'
            'return getComputedStyle(el).flexDirection==="column" && clock.bottom<=date.top+1;}')
        if width > 900:
            assert page.locator('.archive-item').first.evaluate(
                'el => {const media=el.querySelector(".cell-media").getBoundingClientRect();'
                'const stamp=el.querySelector(".cell-time").getBoundingClientRect();'
                'return media.right+5<=stamp.left;}')
        assert page.locator('.cell-time').first.evaluate('(el)=>getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
        assert page.locator('.cell-time').first.evaluate('(el)=>getComputedStyle(el).borderTopWidth') == '0px'
        assert page.locator('.cell-original .source-link').count() == 4
        assert page.locator('.cell-original .source-link').first.get_attribute('href') == data['articles'][0]['url']
        assert 'Категория' not in page.locator('.archive-header-row').inner_text()
        assert page.locator('#archiveList img').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        page.select_option('#source', 'mediazona')
        page.select_option('#platform', 'telegram')
        page.select_option('#marker', 'actor_terminology')
        assert page.locator('.archive-item').count() == 1
        assert page.locator('.archive-item').get_attribute('data-id') == '2'
        page.locator('#resetFilters').click()
        assert page.locator('.archive-item').count() == 4
        assert page.locator('#resetFilters').is_disabled()
        page.select_option('#marker', 'fear')
        assert page.locator('.archive-item').count() == 2
        page.select_option('#platform', 'website')
        assert page.locator('.archive-item').get_attribute('data-id') == '1'
        page.locator('#resetFilters').click()
        page.locator('#searchInput').fill('политзаключённый')
        assert page.locator('.archive-item').get_attribute('data-id') == '2'
        page.locator('#searchInput').fill('')
        if width == 1280:
            source_link = page.locator('.cell-original .source-link').first
            source_link.evaluate('(el)=>el.addEventListener("click",event=>event.preventDefault(),{once:true})')
            source_link.click()
            assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'true'
        button = page.locator('.archive-item[data-id="1"] .more-btn')
        button.click()
        assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'false'
        assert page.locator('#modalFullText mark').first.inner_text() == 'Ад на пороге'
        assert page.locator('#messageModalTitle,.message-modal-title,.modal-fulltext-label').count() == 0
        assert page.locator('.message-modal').get_attribute('aria-labelledby') == 'messageModalLabel'
        assert page.locator('#messageModalLabel').inner_text() == 'Разбор сообщения'
        assert 'Показаны сохранённые фрагменты' not in page.locator('#modalFullText').inner_text()
        assert page.locator('#modalMedia .archive-publisher-status').count() == 2
        assert page.locator('#modalMedia .archive-platform').count() == 0
        assert page.locator('.message-modal-body').evaluate('(el)=>Array.from(el.children).map(el=>el.className)') == ['modal-fulltext-wrap', 'modal-meta-row', 'modal-method-link']
        assert page.locator('#modalOriginal,#modalExplain').count() == 0
        mark = page.locator('#modalFullText mark').first
        mark.hover()
        page.wait_for_selector('#archiveTooltip:not([hidden])')
        assert 'Запугивание' in page.locator('#archiveTooltip').inner_text()
        assert mark.get_attribute('aria-describedby') == 'archiveTooltip'
        assert mark.get_attribute('title') is None
        popup = page.locator('#archiveTooltip').bounding_box()
        assert popup['x'] >= 10 and popup['x'] + popup['width'] <= width - 10
        assert popup['y'] >= 10 and popup['y'] + popup['height'] <= 890
        if width > 760: assert popup['width'] >= 420
        page.wait_for_function("getComputedStyle(document.getElementById('archiveTooltip')).opacity === '1'")
        assert page.locator('#messageCloseBtn').evaluate('''button => {
            const rect = button.getBoundingClientRect();
            return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
        }'''), (width, 'The comment must leave the close control reachable')
        assert 'они не доказывают манипуляцию' not in page.locator('#modalFullText').inner_text()
        assert 'Отсутствие признаков не означает нейтральность текста.' not in page.locator('#modalFullText').inner_text()
        page.locator('#messageCloseBtn').click()
        assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'true'
        button.click()
        page.keyboard.press('Escape')
        assert button.evaluate('(el)=>el===document.activeElement')
        assert page.locator('#archiveTooltip').is_hidden()
        if width <= 900:
            card = page.locator('.archive-item').first
            assert card.locator('.cell-count').is_visible()
            more = card.locator('.more-btn').bounding_box()
            source = card.locator('.source-link').bounding_box()
            time = card.locator('.cell-time').bounding_box()
            assert more['x'] + more['width'] <= source['x'] + 2
            assert abs(more['y'] - source['y']) < 2
            assert abs(source['x'] + source['width'] - time['x'] - time['width']) < 2
            assert more['height'] >= 44
        page.screenshot(path=str(screenshots / f'archive-{width}.png'), full_page=True)
        assert not errors, errors
        page.close()

    # A full incoming snapshot is limited to ten rows after applying filters.
    # Filtering and search still reach publications beyond the initial ten.
    full = copy.deepcopy(data)
    full['articles'] = [dict(copy.deepcopy(data['articles'][i % 4]), id=i+1) for i in range(100)]
    full['articles'][-1]['message_preview'] = 'Уникальный фрагмент из конца подборки'
    for width in (320, 375, 390, 768, 1024, 1280, 1440):
        page = browser.new_page(viewport={'width': width, 'height': 900}, device_scale_factor=1)
        page.route('**/data/analysis.json', lambda route: route.fulfill(json=full))
        page.goto(base + ('/archive.html' if width == 1024 else '/archive/'))
        page.wait_for_function('document.querySelectorAll(".archive-item").length === 10')
        assert page.locator('.archive-item').evaluate_all('(els)=>els.map(el=>Number(el.dataset.id))') == list(range(1, 11))
        assert 'Показано: 10' in page.locator('#rtText').inner_text()
        assert page.locator('.archive-platform').count() == 0
        assert_rows_contain_content(page)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
        page.screenshot(path=str(screenshots / f'archive-ten-{width}.png'))
        last = page.locator('.archive-item').last.locator('.more-btn')
        last.click()
        assert page.locator('#messageModalOverlay').get_attribute('aria-hidden') == 'false'
        page.keyboard.press('Escape')
        page.select_option('#marker', 'fear')
        assert page.locator('.archive-item').count() == 10
        assert page.locator('.archive-item').evaluate_all('(els)=>els.every(el=>el.dataset.status === "danger")')
        assert_rows_contain_content(page)
        page.locator('#resetFilters').click()
        assert page.locator('.archive-item').count() == 10
        page.locator('#searchInput').fill('Уникальный фрагмент из конца подборки')
        assert page.locator('.archive-item').count() == 1
        assert page.locator('.archive-item').get_attribute('data-id') == '100'
        assert 'Показано: 1' in page.locator('#rtText').inner_text()
        page.locator('#searchInput').fill('')
        assert page.locator('.archive-item').count() == 10
        assert_rows_contain_content(page)
        page.close()

    page = browser.new_page()
    page.route('**/data/analysis.json', lambda route: route.fulfill(json=full))
    page.goto(base + '/archive/?publisher=mediazona')
    page.wait_for_selector('.archive-item')
    assert page.locator('.archive-item').count() == 10
    assert page.locator('.archive-item').evaluate_all('(els)=>els.every(el=>el.dataset.publisher === "mediazona")')
    assert page.locator('#source').input_value() == 'mediazona'
    page.locator('#resetFilters').click()
    assert page.locator('.archive-item').evaluate_all('(els)=>els.some(el=>el.dataset.publisher !== "mediazona")')
    page.close()

    page = browser.new_page()
    page.route('**/data/analysis.json', lambda route: route.fulfill(json=data))
    page.goto(base + '/archive/?publisher=mediazona')
    page.wait_for_selector('.archive-item')
    assert page.locator('.archive-item').count() == 1
    assert page.locator('.archive-item').get_attribute('data-publisher') == 'mediazona'
    assert 'Найдено фрагментов для проверки: 1' in page.locator('.archive-item .cell-count').inner_text()
    page.locator('.more-btn').click()
    assert 'Обозначение участника' in page.locator('#modalCategory').inner_text()
    marker = page.locator('#modalFullText mark').first
    marker.hover()
    page.wait_for_selector('#archiveTooltip:not([hidden])')
    assert 'Информационная отметка' in page.locator('#archiveTooltip').inner_text()
    page.close()
    # A bad source URL never becomes a clickable outbound link.
    bad = copy.deepcopy(data); bad['articles'][0]['url'] = 'javascript:alert(1)'
    page = browser.new_page(); page.route('**/data/analysis.json', lambda route: route.fulfill(json=bad))
    page.goto(base + '/archive.html'); page.wait_for_selector('.archive-item')
    assert page.locator('.archive-item[data-id="1"] .source-link').count() == 0
    assert 'Источник недоступен' in page.locator('.archive-item[data-id="1"]').inner_text()
    page.close()
    # First tap opens a comment, the second closes it. Reduced motion has no animation.
    context = browser.new_context(viewport={'width':375,'height':844}, has_touch=True, is_mobile=True, reduced_motion='reduce')
    page = context.new_page(); page.route('**/data/analysis.json', lambda route: route.fulfill(json=data))
    page.goto(base + '/archive/'); page.wait_for_selector('.archive-item')
    page.locator('.more-btn').first.click()
    page.locator('#modalFullText mark').first.tap()
    page.wait_for_selector('#archiveTooltip:not([hidden])')
    assert page.locator('#archiveTooltip').evaluate('(el)=>getComputedStyle(el).transitionDuration') == '0s'
    page.locator('#modalFullText mark').first.tap()
    assert page.locator('#archiveTooltip').is_hidden()
    context.close()
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
    assert page.locator('.archive-item').count() == min(10, len(snapshot['articles']))
    assert page.locator('.archive-platform').count() == 0
    assert_rows_contain_content(page)
    page.close()
    print(json.dumps({'archive_viewports': 7, 'real_snapshot_ids': 'passed', 'source_links_and_legal_labels': 'passed',
                      'unicode_evidence_and_touch': 'passed', 'no_fabricated_fallback': 'passed',
                      'ten_row_limit_after_filtering_and_search': 'passed', 'platform_labels_removed': 'passed',
                      'analysis_filters_mobile_cards_and_shared_tooltips':'passed'}))


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
