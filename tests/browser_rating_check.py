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
            example = page.locator('#heroExampleText')
            assert example.get_attribute('data-example-total') == '10'
            assert example.get_attribute('data-example-index') == '0'
            assert example.locator('mark.hero-trigger').count() >= 2
            assert 'Экономика рухнула' in example.inner_text()
            assert example.get_attribute('data-phase') == 'highlighted'
            assert example.locator('mark.hero-trigger:not(.is-highlighted)').count() == 0
            assert page.locator('#heroExampleCallouts .hero-example-callout.is-visible').count() == 2
            assert page.locator('#heroExampleCallouts').evaluate(
                'el => getComputedStyle(el).pointerEvents === "none"')
            assert page.locator('#heroExampleCallouts .hero-example-callout').all_inner_texts() == [
                'Катастрофизация', 'Оценочная лексика']
            geometry = page.locator('#heroExampleCallouts').evaluate(
                'layer => {const t=document.querySelector("#heroExampleText").getBoundingClientRect(); '
                'const a=layer.getBoundingClientRect(); '
                'return {title:{top:t.top,bottom:t.bottom,height:t.height}, '
                'stage:{top:a.top,bottom:a.bottom,height:a.height}, '
                'tips:[...layer.children].map(b=>{const r=b.getBoundingClientRect(); '
                'return {top:r.top,bottom:r.bottom,height:r.height,label:b.textContent};})}; }')
            assert all(b['bottom'] <= geometry['title']['top']-5 or
                       b['top'] >= geometry['title']['bottom']+5
                       for b in geometry['tips']), (width, geometry)
            if width >= 1024:
                # The daily count shares the headline's vertical centre, not
                # the bottom of the much taller reserved annotation stage.
                assert page.locator('.hero').evaluate(
                    'hero => {const stage=hero.querySelector(".hero-example-stage").getBoundingClientRect();'
                    'const c=hero.querySelector(".hero-counter").getBoundingClientRect();'
                    'return Math.abs((stage.top+stage.bottom-c.top-c.bottom)/2)<20;}')
                # Both first-sentence markers are on its first line: their
                # labels must stay next to those words, even at 80% CSS zoom.
                assert page.locator('#heroExampleCallouts').evaluate(
                    'layer => [...layer.children].every(tip => {'
                    'const mark=document.querySelectorAll("#heroExampleText mark")[+tip.dataset.triggerIndex];'
                    'const a=tip.getBoundingClientRect(), b=mark.getBoundingClientRect();'
                    'const s=layer.getBoundingClientRect().width/layer.offsetWidth;'
                    'const pointer=a.left+parseFloat(getComputedStyle(tip).getPropertyValue("--callout-pointer-x"))*s;'
                    'return Math.min(Math.abs(a.bottom-b.top),Math.abs(a.top-b.bottom))<12 && '
                    'Math.abs(pointer-(b.left+b.right)/2)<2;})')
                # Restore the large two-line headline, never a tiny one-line fit.
                assert example.evaluate(
                    'el => {const s=getComputedStyle(el), line=parseFloat(s.lineHeight);'
                    'return s.whiteSpace === "normal" && '
                    'parseFloat(s.fontSize)>=28 && el.scrollWidth<=el.clientWidth+2 && '
                    'el.getBoundingClientRect().height<=2*line+3;}')
            assert not example.text_content().strip().endswith('.')
            assert page.locator('.hero-counter-mobile .counter-label-sm').text_content().strip().lower().replace('\u00a0', ' ').startswith('публикаций')
            assert page.locator('#heroExampleText .hero-example-punctuation').count() == 0
            assert page.locator('.hero-example-note').count() == 0
            assert 'Демонстрационные примеры · не цитаты СМИ' not in page.locator('main').inner_text()
            if mobile:
                assert page.locator('.hero-kicker').inner_text() == 'Первый независимый рейтинг российских СМИ'
                assert page.locator('.hero-nav a').all_inner_texts() == ['Узнать о возможностях проекта\n→']
                assert page.locator('.hero-nav .hero-pro-link').count() == 1
                assert page.locator('.hero-nav .hero-pro-link').get_attribute('data-pro-gateway') == ''
                assert page.locator('.hero-nav .hero-pro-link').evaluate(
                    'a => {const s=getComputedStyle(a), n=a.getBoundingClientRect();'
                    'const c=a.querySelector(".hero-pro-arrow");'
                    'return n.height>=44 && a.scrollWidth<=a.clientWidth+1 && '
                    's.backgroundImage==="none" && s.backgroundColor==="rgba(0, 0, 0, 0)" && '
                    's.borderTopWidth==="0px" && !!c && c.getAttribute("aria-hidden")==="true";}')
                assert not page.locator('.hero .hero-counter').is_visible()
                assert page.locator('.hero-counter-mobile').is_visible()
                # Example text and counter must be centered and large without
                # horizontal overflow on 320, 360 and 390px viewports.
                assert example.evaluate(
                    'el => getComputedStyle(el).textAlign === "center" && '
                    'parseFloat(getComputedStyle(el).fontSize) >= 19')
                assert page.locator('.hero-counter-mobile').evaluate(
                    'el => getComputedStyle(el).display === "grid" && '
                    'getComputedStyle(el).gridTemplateColumns.split(" ").length === 2')
                assert page.locator('.hero-counter-mobile .counter-value-sm').evaluate(
                    'el => parseFloat(getComputedStyle(el).fontSize) >= 50')
                assert page.locator('.hero-counter-mobile .counter-label-sm').evaluate(
                    'el => parseFloat(getComputedStyle(el).fontSize) >= 14')
                assert page.locator('.hero-counter-mobile').evaluate(
                    'el => {const box=el.getBoundingClientRect(); '
                    'const value=el.querySelector(".counter-value-sm").getBoundingClientRect(); '
                    'const label=el.querySelector(".counter-label-sm").getBoundingClientRect(); '
                    'const parent=box.parentElement || el.parentElement; '
                    'const available=parent.getBoundingClientRect(); '
                    'return value.right+4<=label.left && '
                    'Math.abs((value.top+value.bottom)/2-(label.top+label.bottom)/2)<16 && '
                    'value.left>=box.left-1 && label.right<=box.right+1 && '
                    'Math.abs((box.left+box.right)/2-(available.left+available.right)/2)<2; }')
                assert page.locator('.hero-counter-mobile .counter-label-sm').evaluate(
                    'el => {const html=el.innerHTML; return '
                    'html.includes("публикаций<br>с&nbsp;признаками<br>за&nbsp;"); }')
                assert page.locator('.hero').evaluate(
                    'el => getComputedStyle(el).borderBottomWidth === "1px"')
            else:
                assert page.locator('.hero .hero-counter').is_visible()
                assert not page.locator('.hero-counter-mobile').is_visible()
                if width >= 1024:
                    assert page.locator('.hero .hero-counter .counter-label').evaluate(
                        'el => el.innerHTML.toLowerCase().includes("публикаций<br>с признаками<br>за ")')
                    assert page.locator('.hero .hero-counter').evaluate(
                        'el => {const value=el.querySelector(".counter-value").getBoundingClientRect();'
                        'const label=el.querySelector(".counter-label").getBoundingClientRect();'
                        'const box=el.getBoundingClientRect();'
                        'return getComputedStyle(el).display === "grid" && '
                        'getComputedStyle(el).gridTemplateColumns.split(" ").length === 2 && '
                        'value.right+4<=label.left && '
                        'Math.abs((value.top+value.bottom-label.top-label.bottom)/2)<12 && '
                        'value.left>=box.left-1 && label.right<=box.right+1 && '
                        'value.top>=box.top-1 && label.bottom<=box.bottom+1 && '
                        'getComputedStyle(el.querySelector(".counter-label")).backgroundImage==="none"; }')
                else:
                    assert example.evaluate(
                        'el => parseFloat(getComputedStyle(el).fontSize) >= 27')
            if mobile:
                page.locator('#mediaDots button[aria-label="Показать RT на русском"]').click()
                card = page.locator('.media-card.is-active')
                assert card.get_attribute('data-publisher') == 'rt'
                assert page.locator('.media-card:not(.is-active)').first.evaluate('card => card.inert')
                chosen = next(item for item in fixture['publishers'] if item['id'] == 'rt')
            else:
                chosen = next(item for item in fixture['publishers']
                              if item['id'] == ('rt' if width >= 1024 else fixture['publishers'][0]['id']))
                card = page.locator(f'.media-card[data-publisher="{chosen["id"]}"]')
            assert card.locator('.rating-score').inner_text() == f'{chosen["score_percent"]:g}%'
            # BBC/RIA have supplied local logos; other publishers may use
            # external favicon services or offline lettermark fallbacks.
            assert card.locator('.logo-icon').count() == 1
            if card.locator('.logo-image').count():
                src = card.locator('.logo-image').get_attribute('src')
                expected_local = {'bbc': '/bbc-publisher.webp', 'ria': '/ria-publisher.webp'}
                if chosen['id'] in expected_local:
                    assert src == expected_local[chosen['id']], (chosen['id'], src)
                else:
                    assert src.startswith(('https://www.google.com/s2/favicons?',
                                           'https://unavatar.io/telegram/')), src
            else:
                assert card.locator('.logo-icon').inner_text().strip()
            assert card.locator('.media-details, .media-meta, .media-type').count() == 0
            assert card.locator('.media-footer .link-button').inner_text() == 'Смотреть примеры'
            assert card.locator('.media-footer .link-button').get_attribute('href') == '/archive/?publisher=' + chosen['id']
            if mobile:
                assert card.locator('.media-card-arrow').count() == 2
                assert card.locator('.media-card-arrow-prev').get_attribute('aria-label') == 'Предыдущее СМИ'
                assert card.locator('.media-card-arrow-next').get_attribute('aria-label') == 'Следующее СМИ'
                assert card.locator('.media-card-arrow').first.evaluate(
                    'el => el.getBoundingClientRect().width >= 32')
            else:
                assert card.locator('.media-card-arrow').count() == 0
            assert card.locator('.media-footer').evaluate(
                'el => {const link=el.querySelector(".link-button");'
                'const full=el.querySelector(".media-full-list-button");'
                'const a=el.getBoundingClientRect(), x=link.getBoundingClientRect(), y=full.getBoundingClientRect();'
                'const mobile=innerWidth<768;'
                'return mobile ? getComputedStyle(el).gridTemplateColumns.split(" ").length===2 && '
                'x.right+3<=y.left && x.width>=a.width*.3 && y.width>=a.width*.3 && '
                'Math.abs(x.top-y.top)<2 && y.right<=a.right+2 : '
                'Math.abs(x.width-a.width)<2 && getComputedStyle(full).display==="none"; }')
            assert card.locator('.rating-headline').evaluate(
                'el => {const s=getComputedStyle(el), v=el.querySelector(".rating-score");'
                'return s.justifyContent==="flex-start" && s.textAlign==="left" && '
                's.borderTopWidth==="0px" && s.backgroundImage!=="none" && '
                'getComputedStyle(v,"::before").content!=="none" && el.offsetHeight>=50;}')
            assert card.locator('.small-graph, .rating-progress').count() == 0
            assert card.locator('.rating-legal-info, .media-top-badges, .media-level-badge, .rating-caption-row').count() == 0
            assert card.locator('.media-name').evaluate('el => getComputedStyle(el).whiteSpace === "nowrap"')
            assert card.locator('.media-name').evaluate('el => el.scrollWidth <= el.clientWidth + 300')
            assert card.locator('.media-identity-text').evaluate(
                'el => el.closest(".media-card-header") !== null')
            assert card.locator('.rating-headline').evaluate(
                'el => el.previousElementSibling.classList.contains("media-card-header") && '
                'el.nextElementSibling.classList.contains("media-footer")')
            assert card.locator('.rating-score').inner_text() == f'{chosen["score_percent"]:g}%'
            assert card.locator('.rating-headline-label').inner_text() == 'спорных сообщений'
            assert 'собранных публикаций с признаками' in card.locator('.rating-headline').get_attribute('aria-label')
            assert card.locator('.rating-headline').evaluate(
                'el => {const box=el.getBoundingClientRect();'
                'const value=el.querySelector(".rating-score").getBoundingClientRect();'
                'const label=el.querySelector(".rating-headline-label").getBoundingClientRect();'
                'return value.left>=box.left-1 && value.right<=box.right+1 && '
                'label.left>=box.left-1 && label.right<=box.right+1;}')
            if chosen['id'] == 'mediazona':
                assert card.locator('.rating-status-stack .media-status-tag').count() == 1
                assert card.locator('.rating-status-stack').evaluate(
                    'el => el.closest(".media-identity-text") !== null')
            if not mobile:
                expected_cards = min(3 if width >= 1024 else 2, len(fixture['publishers']))
                assert page.locator('.media-card').count() == expected_cards
                # Hover lifts the interacted-with card by 2px. Verify that cards
                # share one CSS grid row using layout coordinates, not transformed
                # screen rectangles (which depend on pointer position).
                assert page.locator('.media-grid').evaluate(
                    'el => el.firstElementChild.offsetTop === el.lastElementChild.offsetTop')
                assert page.locator('.hero .hero-text').evaluate(
                    'el => getComputedStyle(el).backgroundImage === "none" && '
                    'getComputedStyle(el).borderTopWidth === "0px"')
                if width >= 1024:
                    # Desktop: large number to the LEFT of a three-line, unboxed label.
                    assert page.locator('.hero .hero-counter').evaluate(
                        'el => {const n=el.querySelector(".counter-value").getBoundingClientRect();'
                        'const label=el.querySelector(".counter-label").getBoundingClientRect();'
                        'return getComputedStyle(el).display==="grid" && n.right+4<=label.left && '
                        'Math.abs((n.top+n.bottom-label.top-label.bottom)/2)<12 && '
                        'getComputedStyle(el.querySelector(".counter-label")).borderTopWidth==="0px";}')
                else:
                    # Tablet retains the stacked counter until the desktop breakpoint.
                    assert page.locator('.hero .hero-counter').evaluate(
                        'el => getComputedStyle(el).flexDirection === "column"')
                    assert page.locator('.hero .hero-counter .counter-value').evaluate(
                        'el => el.getBoundingClientRect().top >= '
                        'el.nextElementSibling.getBoundingClientRect().bottom - 1')
                assert page.locator('.hero .counter-value').evaluate(
                    'el => getComputedStyle(el).fontFamily.includes("Orbitron")')
            else:
                zero_name = next(item['name'] for item in fixture['publishers'] if item['id'] == 'mediazona')
                page.locator(f'#mediaDots button[aria-label="Показать {zero_name}"]').click()
                zero_card = page.locator('.media-card.is-active')
                assert zero_card.locator('.rating-score').inner_text() == '0%'
                assert zero_card.locator('.rating-score').inner_text() == '0%'
                assert zero_card.locator('.rating-headline-label').inner_text() == 'спорных сообщений'
                assert zero_card.locator('.small-graph, .rating-signal-peak').count() == 0
                assert zero_card.locator('.media-identity-text .rating-status-stack .media-status-tag').all_inner_texts() == ['иноагент']
                meduza = next(item['name'] for item in fixture['publishers'] if item['id'] == 'meduza')
                page.locator(f'#mediaDots button[aria-label="Показать {meduza}"]').click()
                double = page.locator('.media-card.is-active .media-identity-text .rating-status-stack')
                assert double.locator('.media-status-tag').all_inner_texts() == [
                    'иноагент', 'нежелательная организация']
                assert double.locator('.media-status-tag').evaluate_all(
                    'els => els.every(el => el.getBoundingClientRect().width > 0)')
                assert page.locator('.media-card.is-active .rating-info-trigger').count() == 0
                page.locator('#mediaDots button[aria-label="Показать RT на русском"]').click()
            page.screenshot(path=str(output / f'rating-{width}.png'), full_page=True)

            trigger = (page.locator('.media-card.is-active .media-full-list-button')
                       if mobile else page.locator('.show-full-list-trigger:visible').first)
            if mobile:
                assert page.locator('.full-list-button-mobile').count() == 0
                assert trigger.is_visible()
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
            if width in (1280, 390):
                # Real counter widths change with the corpus. Do not clip the
                # caption or lose its shared centre when the count gains digits.
                selector = '.hero-counter-mobile' if mobile else '.hero .hero-counter'
                counter = page.locator(selector)
                original = counter.evaluate('el => {const n=el.querySelector(".counter-value,.counter-value-sm");return {text:n.textContent,digits:n.dataset.digits};}')
                for value in ('39', '123', '1\u00a0234', '12\u00a0345'):
                    counter.evaluate('(el,value) => {const n=el.querySelector(".counter-value,.counter-value-sm");n.textContent=value;n.dataset.digits=String(value.replace(/[^0-9]/g, "").length);}', value)
                    assert counter.evaluate(
                        'el => {const a=el.getBoundingClientRect();const n=el.querySelector(".counter-value,.counter-value-sm").getBoundingClientRect();'
                        'const l=el.querySelector(".counter-label,.counter-label-sm").getBoundingClientRect();'
                        'return n.left>=a.left-1 && l.right<=a.right+1 && (innerWidth<768 ? '
                        'n.right+4<=l.left && Math.abs((n.top+n.bottom-l.top-l.bottom)/2)<12 : '
                        'n.right+4<=l.left && l.right<=a.right+1 && '
                        'Math.abs((n.top+n.bottom-l.top-l.bottom)/2)<12);}')
                counter.evaluate('(el,saved) => {const n=el.querySelector(".counter-value,.counter-value-sm");n.textContent=saved.text;n.dataset.digits=saved.digits;}', original)
                if width == 1280:
                    # A late font/layout change must re-anchor labels without
                    # needing a window resize event.
                    example.evaluate('el => el.style.setProperty("font-size","34px","important")')
                    page.wait_for_function('''() => [...document.querySelectorAll('#heroExampleCallouts > span')].every(tip => {
                      const mark=document.querySelectorAll('#heroExampleText mark')[+tip.dataset.triggerIndex];
                      const layer=tip.parentElement, a=tip.getBoundingClientRect(), b=mark.getBoundingClientRect();
                      const scale=layer.getBoundingClientRect().width/layer.offsetWidth;
                      return Math.abs(a.left+parseFloat(tip.style.getPropertyValue('--callout-pointer-x'))*scale-(b.left+b.right)/2)<2;
                    })''')
                    example.evaluate('el => el.style.removeProperty("font-size")')
            if width == 390:
                # The single text link opens the existing PRO chooser and restores focus.
                link = page.locator('.hero-nav .hero-pro-link')
                link.click()
                page.locator('.pro-gateway-dialog').wait_for(state='visible')
                assert page.locator('.pro-gateway-option').count() == 2
                assert page.locator('.pro-gateway-option--research').get_attribute('href') == '/analysis/'
                assert page.locator('.pro-gateway-option--business').get_attribute('href') == '/business/'
                page.keyboard.press('Escape')
                assert link.evaluate('a => a === document.activeElement')
                page.locator('#burgerBtn').click()
                assert page.locator('#burgerBtn').get_attribute('aria-expanded') == 'true'
                page.keyboard.press('Escape')
                assert page.locator('#burgerBtn').get_attribute('aria-expanded') == 'false'
            if width == 1280:
                page.clock.install()
                page.clock.fast_forward(16000)
                assert page.locator('#dailyCounterValue').inner_text() == '3'
                # Auto-rotation can replace RT in the displayed group.
                # Every example button opens the archive filtered to that outlet.
                publisher = page.locator('.media-card').first.get_attribute('data-publisher')
                page.locator('.media-card .link-button').first.click()
                page.wait_for_url('**/archive/?publisher=' + publisher)
                page.wait_for_function('document.querySelector("#rtText").textContent.startsWith("Обновлено:")')
                assert page.locator('#archiveList .archive-item').evaluate_all('(els,id) => els.every(el=>el.dataset.publisher === id)', publisher)
        finally:
            context.close()

    # Check real-motion mobile behavior as well: reduced-motion tests alone
    # cannot detect opacity conflicts between entry keyframes and the slider.
    for width in (390, 320):
        context = browser.new_context(
            viewport={"width": width, "height": 812}, is_mobile=True,
            has_touch=True, reduced_motion='no-preference')
        try:
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.route('**/data/rating.json', lambda route: route.fulfill(json=fixture))
            page.goto(base + '/index.html')
            first = page.locator('.media-card.is-active')
            first.wait_for(state='visible')
            count_font = page.locator('.hero-counter-mobile .counter-value-sm').evaluate(
                'el => parseFloat(getComputedStyle(el).fontSize)')
            label_font = page.locator('.hero-counter-mobile .counter-label-sm').evaluate(
                'el => parseFloat(getComputedStyle(el).fontSize)')
            assert count_font >= 44, count_font  # 3–5 digits are scaled down to fit.
            assert label_font >= 14, label_font
            gap = first.locator('.media-card-header').evaluate(
                'el => el.nextElementSibling.getBoundingClientRect().top - '
                'el.getBoundingClientRect().bottom')
            assert 0 <= gap <= 16, gap
            # CSS opacity transitions legitimately take ~280 ms after class
            # changes. Wait for the settled state; fail only if it stays hidden.
            page.wait_for_function(
                '() => { const el = document.querySelector(".media-card.is-active"); '
                'return el && parseFloat(getComputedStyle(el).opacity) > .999; }',
                timeout=2500)
            assert first.evaluate('el => getComputedStyle(el).animationName === "none"')
            assert page.locator('.media-grid .media-card.is-active').count() == 1
            # Pre-laid but invisible letters must prevent reflow while typing.
            example = page.locator('#heroExampleText')
            assert example.get_attribute('data-example-total') == '10'
            assert example.locator('.hero-trigger').count() == 2
            assert example.locator('.hero-example-char:not(.is-typed)').count() > 0
            assert example.get_attribute('data-phase') in ('typing', 'highlighting', 'highlighted')
            assert example.evaluate('el => getComputedStyle(el).animationName === "none"')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            if width == 390:
                # The heading cannot move when the second line begins.
                assert example.get_attribute('data-phase') == 'typing'
                assert example.locator('mark.hero-trigger.is-highlighted').count() == 0
                assert page.locator('#heroExampleCallouts .hero-example-callout').count() == 0
                start_rect = example.evaluate(
                    'el => ({y:el.getBoundingClientRect().y - el.parentElement.getBoundingClientRect().y, '
                    'h:el.getBoundingClientRect().height, '
                    'first:el.querySelector(".hero-example-word").getBoundingClientRect().y - '
                    'el.getBoundingClientRect().y})')
                page.wait_for_function(
                    '() => document.querySelector("#heroExampleText")?.dataset.phase === "highlighted"',
                    timeout=8000)
                assert example.locator('mark.hero-trigger.is-highlighted').count() == 2
                assert page.locator('#heroExampleCallouts .hero-example-callout.is-visible').count() == 2
                assert page.locator('#heroExampleCallouts .hero-example-callout').all_inner_texts() == [
                    'Катастрофизация', 'Оценочная лексика']
                assert page.locator('#heroExampleCallouts').evaluate(
                    'layer => {const t=document.querySelector("#heroExampleText").getBoundingClientRect();'
                    'return [...layer.children].every(b => {const r=b.getBoundingClientRect();'
                    'return r.bottom <= t.top-5 || r.top >= t.bottom+5;}); }')
                # Each callout remains within the fixed stage bounds.
                assert page.locator('#heroExampleCallouts').evaluate(
                    'el => Array.from(el.children).every(box => { '
                    'const a=el.getBoundingClientRect(), b=box.getBoundingClientRect(); '
                    'return b.left >= a.left-1 && b.right <= a.right+1 && '
                    'b.top >= a.top-1 && b.bottom <= a.bottom+1; })')
                assert example.locator('.hero-example-char:not(.is-typed)').count() == 0
                end_rect = example.evaluate(
                    'el => ({y:el.getBoundingClientRect().y - el.parentElement.getBoundingClientRect().y, '
                    'h:el.getBoundingClientRect().height, '
                    'first:el.querySelector(".hero-example-word").getBoundingClientRect().y - '
                    'el.getBoundingClientRect().y})')
                assert all(abs(start_rect[k] - end_rect[k]) < 1 for k in start_rect), (start_rect, end_rect)
                assert 'Экономика рухнула' in example.inner_text()
                # Complete text + explanations stays up longer than the
                # old ~2.2s cycle; keep the threshold below the first fade.
                page.wait_for_timeout(1750)
                assert example.get_attribute('data-example-index') == '0'
                page.wait_for_function(
                    '() => document.querySelector("#heroExampleText")?.dataset.exampleIndex === "1"',
                    timeout=15000)
                page.wait_for_function(
                    '() => document.querySelector("#heroExampleText")?.dataset.phase === "highlighted"',
                    timeout=9500)
                assert 'Страну ждёт катастрофа' in example.text_content()
                assert page.locator('#heroExampleCallouts .hero-example-callout.is-visible').count() == 2
                assert example.locator('mark.hero-trigger.is-highlighted').count() == 2
                assert page.locator('.media-card.is-active').count() == 1
            assert page.locator('.media-card:not(.is-active)').first.evaluate(
                'el => getComputedStyle(el).visibility === "hidden"')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            next_name = fixture['publishers'][1]['name']
            # Arrow controls must navigate both ways without changing the
            # existing dot carousel and without keyboard focus getting lost.
            old_id = page.locator('.media-card.is-active').get_attribute('data-publisher')
            page.locator('.media-card.is-active .media-card-arrow-next').click()
            expected = (next(i for i,row in enumerate(fixture['publishers'])
                             if row['id'] == old_id) + 1) % len(fixture['publishers'])
            assert page.locator('.media-card.is-active').get_attribute('data-publisher') == fixture['publishers'][expected]['id']
            page.locator('.media-card.is-active .media-card-arrow-prev').click()
            assert page.locator('.media-card.is-active').get_attribute('data-publisher') == old_id
            page.locator(f'#mediaDots button[aria-label="Показать {next_name}"]').click()
            active_card = page.locator('.media-card.is-active')
            assert active_card.locator('.media-name').inner_text() == next_name
            page.wait_for_function(
                '() => { const el = document.querySelector(".media-card.is-active"); '
                'return el && parseFloat(getComputedStyle(el).opacity) > .999; }',
                timeout=2500)
            assert active_card.evaluate(
                'el => getComputedStyle(el).visibility === "visible"')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        finally:
            context.close()

    # Browser display rounds upwards without altering the exact underlying
    # percentage, order, or hourly graph. RT is 1/4 in the fixture; remove
    # one unflagged collected article to test the 1/3 -> 34% edge case.
    fractional = copy.deepcopy(fixture)
    sample = next(row for row in fractional['publishers'] if row['id'] == 'rt')
    removed = False
    for point in sample['series']:
        if not removed and point['collected'] > point['flagged']:
            point['collected'] -= 1
            point['analyzed'] -= 1
            removed = True
        if removed:
            point['cumulative_collected'] -= 1
            point['cumulative_analyzed'] -= 1
        collected = point['cumulative_collected']
        analyzed = point['cumulative_analyzed']
        point['score_percent'] = (100 * point['cumulative_flagged'] / collected
                                  if collected and analyzed == collected else None)
    assert removed, 'Fractional display test requires an unflagged article'
    sample['collected'] -= 1
    sample['analyzed'] -= 1
    sample['score_percent'] = 100 * sample['flagged'] / sample['collected']
    fractional['totals']['collected'] -= 1
    fractional['totals']['analyzed'] -= 1
    context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion='reduce')
    try:
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/data/rating.json', lambda route: route.fulfill(json=fractional))
        page.goto(base + '/index.html')
        rt = page.locator('.media-card[data-publisher="rt"]')
        rt.wait_for(state='visible')
        assert rt.locator('.rating-score').inner_text() == '34%'
        assert rt.locator('.rating-headline-label').evaluate(
            'el => getComputedStyle(el).fontWeight === "400"')
        assert rt.locator('.small-graph').count() == 0
        page.locator('.show-full-list-trigger:visible').first.click()
        item = page.locator('.full-list-row[data-publisher="rt"]')
        assert item.locator('.fli-rating').inner_text() == '34%'
        # Exact per-hour cumulative scores remain in the full-list chart.
        assert item.locator('.fli-graph circle[data-score]').count() == sum(
            point['score_percent'] is not None for point in sample['series'])
        actual = item.locator('.fli-graph circle[data-score]').evaluate_all(
            '([first, ...others], endAt) => {'
            'const point = [first, ...others].find(el => el.dataset.endAt === endAt);'
            'return point ? Number(point.dataset.score) : null;'
            '}', sample['series'][-1]['end_at'])
        assert actual is not None and abs(actual - sample['score_percent']) < .0001
    finally:
        context.close()

    # Validate the real publisher entries, rather than injecting duplicate
    # IDs into the rating fixture. On mobile the selector can expose any outlet
    # without changing ranks, totals or the scoring data.
    context = browser.new_context(
        viewport={"width": 390, "height": 812}, is_mobile=True,
        has_touch=True, reduced_motion='reduce')
    try:
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/data/rating.json', lambda route: route.fulfill(json=fixture))
        page.goto(base + '/index.html')
        for outlet, expected in (('bbc', '/bbc-publisher.webp'),
                                 ('ria', '/ria-publisher.webp')):
            name = next(row['name'] for row in fixture['publishers'] if row['id'] == outlet)
            page.locator(f'#mediaDots button[aria-label="Показать {name}"]').click()
            logo = page.locator(f'.media-card.is-active[data-publisher="{outlet}"] .logo-image')
            logo.wait_for(state='attached')
            assert logo.get_attribute('src') == expected
            page.wait_for_function(
                '(id) => { const el = document.querySelector('
                '`.media-card.is-active[data-publisher="${id}"] .logo-image`); '
                'return el && el.complete && el.naturalWidth >= 128; }',
                arg=outlet, timeout=5000)
            assert page.locator(
                f'.media-card.is-active[data-publisher="{outlet}"] .logo-icon.has-logo').count() == 1
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
