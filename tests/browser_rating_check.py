"""Real rating arithmetic, charts and offline appeal on desktop and mobile."""

import argparse
import copy
import functools
import http.server
import json
from pathlib import Path
import shutil
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright
from test_rating import browser_rating_fixture


def rating_ui(browser, base, site, errors, requests):
    fixture = browser_rating_fixture()
    output = Path('/tmp/media-strazh-rating-checks')
    output.mkdir(exist_ok=True)
    for width in (1440, 1280, 1100, 1099, 1024, 768, 390, 360, 320):
        mobile = width < 768
        context = browser.new_context(viewport={"width": width, "height": 900 if not mobile else 812},
                                      is_mobile=mobile, has_touch=mobile, reduced_motion="reduce")
        try:
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append((request.method, request.url, request.post_data)))
            page.route('**/data/rating.json', lambda route: route.fulfill(json=fixture))
            page.goto(base + '/index.html')
            page.locator('.media-card').first.wait_for()
            assert page.locator('#dailyCounterValue').inner_text() == str(fixture['totals']['flagged'])
            assert page.locator('#dailyCounterMobile').inner_text() == str(fixture['totals']['flagged'])
            assert 'DEMO' not in page.locator('main').inner_text()
            assert not page.locator('#ratingStatus').is_visible()
            assert 'Независимый проект по разработке системы' not in page.locator('main').inner_text()
            assert 'По собранной выборке' not in page.locator('main').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            if mobile:
                assert not page.locator('.hero .hero-counter').is_visible()
                assert page.locator('.hero-counter-mobile').is_visible()
            else:
                assert page.locator('.hero .hero-counter').is_visible()
                assert not page.locator('.hero-counter-mobile').is_visible()
            if mobile:
                page.locator('#mediaDots button[aria-label="Показать RT на русском"]').click()
                card = page.locator('.media-card.is-active')
                assert card.get_attribute('data-publisher') == 'rt'
                assert card.locator('.rating-score').inner_text() == '25%'
                assert page.locator('.media-card:not(.is-active)').first.evaluate('card => card.inert')
            else:
                card = page.locator('.media-card[data-publisher="rt"]')
            assert card.locator('.rating-score').inner_text() == '25%'
            # Logo is loaded from an external favicon service when available;
            # offline test runners must also accept the safe monogram fallback.
            assert card.locator('.logo-icon').count() == 1
            if card.locator('.logo-image').count():
                assert card.locator('.logo-image').get_attribute('src').startswith('https://www.google.com/s2/favicons?')
            else:
                assert card.locator('.logo-icon').inner_text().strip()
            assert card.locator('.media-details, .media-meta, .media-type').count() == 0
            assert card.locator('.media-footer .link-button').inner_text() == 'Смотреть примеры'
            assert card.locator('.media-footer .link-button').evaluate('el => Math.abs(el.getBoundingClientRect().width - el.parentElement.getBoundingClientRect().width) < 2')
            assert card.locator('.small-graph circle').last.get_attribute('data-score') == '25'
            assert card.locator('.small-graph circle').last.get_attribute('data-collected') == '4'
            assert card.locator('.small-graph circle').last.get_attribute('data-flagged') == '1'
            assert card.locator('.rating-chart-caption-label').inner_text() == 'Найдено спорных сообщений:'
            assert card.locator('.rating-chart-caption-value').inner_text() == '1'
            assert card.locator('.rating-chart-caption').evaluate('el => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1')
            assert card.locator('.small-graph svg').get_attribute('aria-label').startswith('RT на русском.')
            if not mobile:
                expected_cards = min(6 if width >= 1024 else 4, len(fixture['publishers']))
                assert page.locator('.media-card').count() == expected_cards
                zero_card = page.locator('.media-card[data-publisher="mediazona"]')
                assert zero_card.locator('.rating-score').inner_text() == '0%'
                assert zero_card.locator('.rating-chart-caption-label').inner_text() == 'Найдено спорных сообщений:'
                assert zero_card.locator('.rating-chart-caption-value').inner_text() == '0'
                assert 'Количество собранных публикаций по часам' in zero_card.locator('.small-graph svg').get_attribute('aria-label')
                assert zero_card.locator('.small-graph svg circle').count() == 24
                assert zero_card.locator('.small-graph svg circle').last.get_attribute('data-flagged') == '0'
                if width >= 1024:
                    # A carousel renders only the six highest-ranked publishers.
                    # Check the visible missing-data state rather than expecting
                    # an arbitrary unranked publisher (e.g. Kommersant) in that page.
                    no_data = page.locator('.media-card:has(.rating-score.no-data-score)').first
                    assert no_data.count() == 1
                    assert no_data.locator('.rating-chart-caption').inner_text() == 'Нет публикаций за 24 часа'
                    assert 'Нет данных за последние 24 часа' in no_data.locator('.small-graph').inner_text()
            page.screenshot(path=str(output / f'rating-{width}.png'), full_page=True)

            trigger = page.locator('.show-full-list-trigger:visible').first
            trigger.click()
            page.locator('#fullListModal.open').wait_for()
            assert page.locator('.full-list-row').count() == len(fixture['publishers'])
            for publisher, score, level in (('ria', '100%', 'red'), ('tass', '50%', 'yellow'), ('rt', '25%', 'yellow'), ('mediazona', '0%', 'green')):
                row = page.locator(f'.full-list-row[data-publisher="{publisher}"]')
                assert row.locator('.fli-rating').inner_text() == score
                assert level in row.locator('.fli-rating').get_attribute('class')
            assert 'иноагент' in page.locator('.full-list-row[data-publisher="mediazona"]').inner_text()
            empty = page.locator('.full-list-row[data-publisher="kommersant"]')
            assert empty.locator('.fli-rating').inner_text() == '—'
            assert 'green' not in empty.locator('.fli-rating').get_attribute('class')
            page.locator('#modalSort').select_option('rating-asc')
            assert page.locator('.full-list-row').first.get_attribute('data-publisher') == 'mediazona'
            page.locator('#modalSearch').fill('RT на русском')
            assert page.locator('.full-list-row').count() == 1
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.locator('#fullListCloseBtn').click()
            assert trigger.evaluate('element => element === document.activeElement')

            page.locator('#appealLink').click()
            page.locator('#appealModal.open').wait_for()
            assert page.locator('#appealPublisher').evaluate('element => element === document.activeElement')
            assert page.locator('main').evaluate('element => element.inert')
            page.locator('#appealPublisher').fill('RT на русском')
            explanation = 'Проверочная апелляция: алгоритм неверно определил буквальное значение слова.'
            page.locator('#appealExplanation').fill(explanation)
            assert page.locator('#appealUrl').input_value() == ''
            assert page.locator('#appealForm').evaluate('form => form.checkValidity()')
            with page.expect_download() as download:
                page.locator('#appealForm button[type="submit"]').click()
            text = Path(download.value.path()).read_text()
            assert 'RT на русском' in text and explanation in text and 'Ссылка: Не указана' in text
            assert 'почту пока не подключена' in page.locator('#appealStatus').inner_text()
            assert all(explanation not in url and body is None for _, url, body in requests)
            page.locator('#appealUrl').fill('javascript://test')
            page.locator('#appealForm button[type="submit"]').click()
            assert not page.locator('#appealUrl').evaluate('element => element.checkValidity()')
            page.locator('#appealUrl').fill('https://t.me/rt_russian/42')
            with page.expect_download() as download:
                page.locator('#appealForm button[type="submit"]').click()
            assert 'https://t.me/rt_russian/42' in Path(download.value.path()).read_text()
            page.locator('#appealCloseBtn').focus()
            page.keyboard.press('Shift+Tab')
            assert page.locator('#appealForm button[type="reset"]').evaluate('element => element === document.activeElement')
            page.keyboard.press('Tab')
            assert page.locator('#appealCloseBtn').evaluate('element => element === document.activeElement')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            page.screenshot(path=str(output / f'appeal-{width}.png'), full_page=True)
            page.keyboard.press('Escape')
            assert not page.locator('#appealModal').is_visible()
            assert page.locator('#appealLink').evaluate('element => element === document.activeElement')
            assert not page.locator('main').evaluate('element => element.inert')
            page.locator('#appealLink').click()
            assert page.locator('#appealExplanation').input_value() == explanation
            page.locator('#appealForm button[type="reset"]').click()
            assert page.locator('#appealPublisher').input_value() == ''
            assert page.locator('#appealExplanation').input_value() == ''
            page.locator('#appealCloseBtn').click()
            if width == 1280:
                page.clock.install()
                page.clock.fast_forward(16000)
                assert page.locator('#dailyCounterValue').inner_text() == '3'
                page.locator('.media-card[data-publisher="rt"] .link-button').click()
                page.wait_for_url('**/analysis/?source=rt')
                page.wait_for_function("document.getElementById('source').value === 'rt'")
        finally:
            context.close()

    context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion='reduce')
    try:
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/data/rating.json', lambda route: route.fulfill(status=503, body='unavailable'))
        page.goto(base + '/')
        page.locator('#ratingRetry').wait_for(state='visible')
        assert page.locator('#dailyCounterValue').inner_text() == '—'
        assert page.locator('.media-card').count() == 0
        page.unroute('**/data/rating.json')
        corrupt = copy.deepcopy(fixture)
        corrupt['publishers'][0]['score_percent'] = 17  # No silent fallback to wrong percentages.
        page.route('**/data/rating.json', lambda route: route.fulfill(json=corrupt))
        page.locator('#ratingRetry').click()
        page.wait_for_timeout(150)
        assert page.locator('.media-card').count() == 0
        page.unroute('**/data/rating.json')
        hostile = copy.deepcopy(fixture)
        hostile['publishers'][0]['name'] = '<img src=x onerror="window.ratingXss=true">'
        page.route('**/data/rating.json', lambda route: route.fulfill(json=hostile))
        page.locator('#ratingRetry').click()
        page.locator('.media-card').first.wait_for()
        assert page.locator('.media-name').first.inner_text() == hostile['publishers'][0]['name']
        assert page.evaluate('window.ratingXss !== true')
        assert page.locator('.media-card .logo-icon').count() > 0
        assert page.locator('.media-card img[onerror]').count() == 0
    finally:
        context.close()
    assert not errors, errors
    print(json.dumps({'rating_viewports': 9, 'real_formula_and_chart': 'passed',
                      'appeal_optional_url_and_local_download': 'passed', 'appeal_input_not_transmitted': True,
                      'unavailable_and_corrupt_data': 'passed'}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.site))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors, requests = [], []
    try:
        with sync_playwright() as playwright:
            launch = {'headless': True, 'args': ['--no-sandbox']}
            if shutil.which('chromium'):
                launch['executable_path'] = shutil.which('chromium')
            browser = playwright.chromium.launch(**launch)
            rating_ui(browser, f'http://127.0.0.1:{server.server_address[1]}', args.site, errors, requests)
            browser.close()
    finally:
        server.shutdown(); server.server_close()


if __name__ == '__main__':
    main()
