"""Real Wasm/browser checks, including parity with all existing analysis test inputs.

Requires Playwright and Chromium; unit tests do not require either or the network.
"""

import argparse
import copy
from datetime import datetime, timedelta, timezone
import functools
import http.server
import io
import json
from pathlib import Path
import shutil
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from media_strazh.analysis import analyze
import test_analysis
import test_rhetoric
import test_expanded_rhetoric
import test_contextual_rhetoric


def examples():
    cases = []

    def capture(document):
        case = {"document": copy.deepcopy(document)}
        try:
            case["result"] = analyze(document)
        except ValueError as error:
            case["error"] = str(error)
            cases.append(case)
            raise
        cases.append(case)
        return case["result"]

    modules = (test_analysis, test_rhetoric, test_expanded_rhetoric, test_contextual_rhetoric)
    originals = [module.analyze for module in modules]
    for module in modules:
        module.analyze = capture
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(test_analysis.AnalysisTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_rhetoric.RhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_expanded_rhetoric.ExpandedRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_contextual_rhetoric.ContextualRhetoricTests),
    ])
    try:
        output = io.StringIO()
        result = unittest.TextTestRunner(stream=output).run(suite)
        if not result.wasSuccessful():
            raise AssertionError(output.getvalue())
    finally:
        for module, original in zip(modules, originals):
            module.analyze = original
    return cases, result.testsRun


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def inline_touch_and_overlap(browser, base, errors, requests):
    def observe(page):
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))

    context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    try:
        page = context.new_page()
        observe(page)
        page.goto(base + "/analysis.html")
        page.locator('[data-mode="manual"]').tap()
        text = "Политики опасны без смирительной рубашки.\n" + "Открыта библиотека.\n" * 50
        page.locator("#manualText").fill(text)
        page.locator("#manualSubmit").tap()
        page.locator("#manualResult").wait_for(state="visible", timeout=120000)
        trigger = page.locator("#manualTextEvidence mark").first
        trigger.tap()
        page.locator("#manualTooltip").wait_for(state="visible")
        assert page.locator("#manualTooltip h3").count() == 2
        box = page.locator("#manualTooltip").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 376
        assert box["y"] >= 0 and box["y"] + box["height"] <= 813
        page.screenshot(path="/tmp/media-strazh-inline-mobile.png")
        trigger.tap()
        assert not page.locator("#manualTooltip").is_visible()
        page.set_viewport_size({"width": 375, "height": 420})
        trigger.tap()
        # Compact comments may fit without scrolling after removing secondary notes.
        if page.locator("#manualTooltip").evaluate("element => element.scrollHeight > element.clientHeight"):
            scrolled = page.locator("#manualTooltip").evaluate("""element => {
                element.scrollTop = 20;
                return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(element.scrollTop))));
            }""")
            assert scrolled > 0
        assert page.locator("#manualTooltip").is_visible()
        trigger.tap()
        assert not page.locator("#manualTooltip").is_visible()
        page.set_viewport_size({"width": 375, "height": 812})
        trigger.tap()
        page.locator("#manualTextEvidence").evaluate("element => { element.scrollTop = 100; }")
        page.locator("#manualTooltip").wait_for(state="hidden")
        page.locator("#manualEdit").tap()
        assert page.locator("#manualText").input_value() == text
        assert page.locator("#manualText").is_visible()
    finally:
        context.close()

    # Renderer-only fixture: partially overlapping evidence and Unicode offsets.
    # A local worker stub isolates DOM behavior; engine parity is checked separately.
    document = {"title": "", "text": "😀абвгде"}
    result = analyze(document)
    definitions = [(1, 4, "Образ врага", "enemy_image"),
                   (3, 6, "Эвфемизмы и дисфемизмы", "euphemism_dysphemism"),
                   (1, 4, "Запугивание", "fear")]
    result["findings"] = [dict(id=f"f{number}", rule_id=f"renderer.fixture.{number}", category=category,
                              label=label, status="needs_review", explanation=f"<img src=x> Пояснение {number}.",
                              review_question="Проверьте контекст.",
                              evidence=[dict(field="text", start=start, end=end, quote=document["text"][start:end])])
                          for number, (start, end, label, category) in enumerate(definitions, 1)]
    context = browser.new_context(viewport={"width": 375, "height": 812})
    try:
        page = context.new_page()
        observe(page)
        script = "self.onmessage = event => self.postMessage({id:event.data.id,type:'result',result:" + json.dumps(result) + "});"
        page.route("**/manual-worker.js", lambda route: route.fulfill(body=script, content_type="application/javascript"))
        page.goto(base + "/analysis.html")
        page.locator('[data-mode="manual"]').click()
        page.locator("#manualText").fill(document["text"])
        page.locator("#manualSubmit").click()
        page.locator("#manualResult").wait_for(state="visible")
        assert page.locator("#manualTextEvidence").inner_text() == document["text"]
        marks = page.locator("#manualTextEvidence mark")
        assert marks.all_text_contents() == ["аб", "в", "гд"]
        marks.nth(1).hover()
        assert set(page.locator("#manualTooltip h3").all_text_contents()) == {entry[2] for entry in definitions}
        assert page.locator("#manualTooltip img").count() == 0
        page.locator("#manualForm button[type=reset]").click()
        assert not page.locator("#manualTooltip").is_visible()
    finally:
        context.close()


def contextual_analysis_ui(browser, base, site, errors, requests):
    """A quoted-only publication must remain visible under the candidate filter."""
    document = {"title": "", "text": test_contextual_rhetoric.BLAHA_TEXT}
    expected = analyze(document)
    snapshot = json.loads((site / "data/analysis.json").read_text())
    source = next(source for source in snapshot["sources"] if source["id"] == "izvestia_telegram")
    item = copy.deepcopy(snapshot["articles"][0])
    item.update(id=253503, source_id=source["id"], publisher_id=source["publisher_id"],
                platform="telegram", source=source["name"], title="",
                message_preview=document["text"][:160], url="https://t.me/izvestia/253503",
                summary=expected["summary"], findings=expected["findings"], findings_omitted=0)
    snapshot["articles"] = [item]
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
        page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
        page.goto(base + "/analysis.html")
        page.locator(".publication").wait_for()
        assert page.locator("#marker option").count() == 11  # Ten implemented marker categories + all.
        marker = expected["findings"][0]["category"]
        page.select_option("#marker", marker)
        assert page.locator(".publication").count() == 1
        page.select_option("#marker", "")
        assert "Найдено фрагментов для проверки: 11" in page.locator(".publication > .badge").inner_text()
        assert page.locator(".legal-status-note").count() == 0
        assert page.locator(".publication-title").count() == 1
        assert len(page.locator(".publication-title").inner_text()) <= 120
        # The narrow layout keeps both actions readable and aligned.
        page.set_viewport_size({"width": 375, "height": 812})
        details_box = page.locator(".publication .auto-details-button").bounding_box()
        source_box = page.locator(".publication .source-link").bounding_box()
        assert details_box["x"] + details_box["width"] <= source_box["x"] + 1
        assert abs(details_box["y"] - source_box["y"]) < 2
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1280, "height": 900})
        page.locator(".auto-details-button").click()
        page.locator("#automaticModal").wait_for(state="visible")
        auto_marks = page.locator("#automaticModal mark")
        assert any("головорезов" in text for text in auto_marks.all_text_contents())
        auto_marks.filter(has_text="головорезов").hover()
        assert "Цитата или переданная речь" in page.locator("#automaticTooltip").inner_text()
        page.locator("#automaticModalClose").click()
        page.locator('[data-mode="manual"]').click()
        page.locator("#manualText").fill(document["text"])
        page.locator("#manualSubmit").click()
        page.locator("#manualResult").wait_for(state="visible", timeout=120000)
        assert page.locator("#manualTextEvidence").inner_text() == document["text"]
        assert page.locator("#manualTextEvidence mark").count() == 12
        def hover_fragment(text):
            mark = page.locator("#manualTextEvidence mark").filter(has_text=text)
            mark.scroll_into_view_if_needed()
            # Hover after the reader/page scrolling has completed, as a person
            # does. Intentional scrolling dismisses existing comments.
            page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
            mark.hover()
            page.locator("#manualTooltip").wait_for(state="visible")
        hover_fragment("головорезов")
        assert page.locator("#manualTooltip h3").all_text_contents() == ["Эвфемизмы и дисфемизмы"]
        hover_fragment("<...>")
        assert "пропуск сам по себе не доказывает" in page.locator("#manualTooltip").inner_text()
        assert "Сокращение цитаты — требуется сверка с оригиналом" not in page.locator("#manualTooltip").inner_text()
        assert page.locator("#manualWarnings p").count() == 2
        with page.expect_download() as download_info:
            page.locator("#manualDownload").click()
        exported = json.loads(Path(download_info.value.path()).read_text())
        assert exported == expected
        print("Quoted publication filter and user-example inline analysis passed", flush=True)
    finally:
        context.close()



def pro_business_navigation_ui(browser, base):
    """PRO chooser, gated Business start, mentions and period filtering."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        for route in ("index.html", "archive.html", "about.html", "method.html", "help.html"):
            page.goto(base + "/" + route)
            page.locator("a.pro-nav-link").click()
            assert page.locator(".pro-gateway-dialog").is_visible(), route
            assert page.locator(".pro-gateway-option--research").get_attribute("href") == "analysis.html"
            assert page.locator(".pro-gateway-option--business").get_attribute("href") == "business.html"
            page.locator(".pro-gateway-close").click()
            assert not page.locator(".pro-gateway-dialog").is_visible(), route
        page.goto(base + "/index.html")
        # Desktop defaults to compact interface size without horizontal overflow.
        assert page.evaluate("getComputedStyle(document.body).zoom") == "0.8"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
        page.locator("a.pro-nav-link").click()
        page.locator(".pro-gateway-option--business").click()
        page.wait_for_url("**/business.html")
        assert page.locator(".site-header .header-back").is_visible()
        assert page.locator("#profileForm").is_visible()
        assert not page.locator("#businessResults").is_visible()
        assert not page.locator("#trendsGrid .business-trend").count()
        page.locator("#companyName").fill("Тестовая компания")
        page.select_option("#industry", "hospitality")
        page.locator('#profileForm button[type="submit"]').click()
        assert page.locator("#businessResults").is_visible()
        assert "Тестовая компания" in page.locator("#companyDisplay").inner_text()
        assert page.locator("#mentionsBody tr").count() == 4
        assert page.locator("#trendsGrid .business-trend").count() == 3
        assert "Путешествия с питомцами" in page.locator("#trendsGrid").inner_text()
        assert page.locator("#opportunitiesGrid .business-opportunity").count() == 3
        page.select_option("#period", "7")
        assert page.locator("#mentionsBody tr").count() == 2
        page.select_option("#period", "90")
        assert page.locator("#mentionsBody tr").count() == 6
        assert "демо-режим" in page.locator(".business-data-warning").inner_text().lower()
        page.locator("#editProfile").click()
        assert not page.locator("#businessResults").is_visible()
        assert page.locator("#profileForm").is_visible()
        page.goto(base + "/analysis.html")
        assert page.locator(".site-header .header-back").is_visible()

        mobile = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        try:
            p = mobile.new_page()
            p.on("pageerror", lambda error: page_errors.append(str(error)))
            p.goto(base + "/index.html")
            assert p.evaluate("getComputedStyle(document.body).zoom") == "1"
            assert p.locator(".hero h1").evaluate("element => parseFloat(getComputedStyle(element).fontSize)") <= 28
            rating_card = p.locator(".media-grid .media-card.is-active")
            rating_card.wait_for(state="visible")
            badge_box = rating_card.locator(".media-footer .badge").bounding_box()
            examples_box = rating_card.locator(".media-footer .link-button").bounding_box()
            assert badge_box["x"] < examples_box["x"]
            assert abs(badge_box["y"] - examples_box["y"]) < 5
            assert p.evaluate("document.documentElement.scrollWidth <= innerWidth")
            p.locator("#burgerBtn").click()
            p.locator(".nav-links.open .pro-nav-link").click()
            assert p.locator(".pro-gateway-dialog").is_visible()
            assert p.evaluate("document.documentElement.scrollWidth <= innerWidth")
            p.keyboard.press("Escape")
            p.goto(base + "/business.html")
            assert not p.locator("#businessResults").is_visible()
            assert p.evaluate("document.documentElement.scrollWidth <= innerWidth")
            p.locator("#companyName").fill("Тест")
            p.locator('#profileForm button[type="submit"]').click()
            assert p.locator("#businessResults").is_visible()
            assert p.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            mobile.close()
        assert not page_errors, page_errors
        print("PRO chooser and revised Business workflow passed", flush=True)
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    site = args.site.resolve()
    if not (site / "data/manual-engine.json").is_file():
        raise ValueError("Build the site and prepare the browser runtime first.")
    from playwright.sync_api import sync_playwright

    cases, native_tests = examples()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
        functools.partial(QuietHandler, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    requests, errors = [], []
    try:
        with sync_playwright() as playwright:
            launch = {"args": ["--no-sandbox"]}
            chromium = shutil.which("chromium") or shutil.which("chromium-browser")
            if chromium:
                launch["executable_path"] = chromium
            browser = playwright.chromium.launch(**launch)
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(
                (request.method, request.url, request.post_data)))
            page.goto(base + "/analysis.html")
            page.wait_for_selector("#controls:not([hidden])")
            page.evaluate("""() => {
              const worker = new Worker('manual-worker.js');
              let id = 0;
              window.browserHarness = document => new Promise((resolve, reject) => {
                const current = ++id;
                const deadline = setTimeout(() => reject(new Error('Worker timeout')), 120000);
                worker.onmessage = event => {
                  if (event.data.id !== current || event.data.type === 'state') return;
                  clearTimeout(deadline);
                  resolve(event.data);
                };
                worker.onerror = error => { clearTimeout(deadline); reject(new Error(error.message)); };
                worker.postMessage({id: current, document});
              });
              window.closeHarness = () => worker.terminate();
            }""")
            for index, case in enumerate(cases, 1):
                actual = page.evaluate("document => window.browserHarness(document)", case["document"])
                if "error" in case:
                    assert actual["type"] == "error" and actual["kind"] == "validation", index
                    assert actual["message"] == case["error"], index
                else:
                    assert actual["type"] == "result", (index, actual.get("message"))
                    assert actual["result"] == case["result"], f"Python/browser disagreement: example {index}"
            page.evaluate("window.closeHarness()")
            print(f"Python/browser parity passed: {len(cases)} inputs from {native_tests} existing tests",
                  flush=True)

            document = {"title": '<img src=x onerror="window.injected=true">',
                        "text": '😀 Все знают о решении. Автор заявил: «Все знают о решении».'}
            expected = analyze(document)
            page.locator('[data-mode="manual"]').click()
            for width, height in ((375, 812), (1024, 768), (1280, 900)):
                page.set_viewport_size({"width": width, "height": height})
                page.locator("#manualTitle").fill(document["title"])
                page.locator("#manualText").fill(document["text"])
                page.locator("#manualSubmit").click()
                page.locator("#manualResult").wait_for(state="visible", timeout=120000)
                assert page.locator("#manualTitleEvidence").inner_text() == document["title"]
                assert page.locator("#manualTextEvidence").inner_text() == document["text"]
                assert page.locator("#manualTextEvidence mark").all_text_contents() == ["Все знают", "Все знают"]
                assert not page.locator("#manualText").is_visible()
                assert page.locator("#manualText").input_value() == document["text"]
                assert page.locator("#manualFindings").count() == 0
                assert page.locator("#manualPanel img").count() == 0
                assert page.locator("#manualWarnings p").all_text_contents() == [
                    "Найденные признаки требуют проверки; они не доказывают манипуляцию, намерение автора или ложность фактов.",
                    "Отсутствие признаков не означает нейтральность текста.",
                ]
                marks = page.locator("#manualTextEvidence mark")
                marks.first.hover()
                page.locator("#manualTooltip").wait_for(state="visible")
                assert page.locator("#manualTooltip h3").all_text_contents() == ["Обобщение"]
                assert expected["findings"][0]["explanation"] in page.locator("#manualTooltip").inner_text()
                box = page.locator("#manualTooltip").bounding_box()
                assert box["x"] >= 0 and box["y"] >= 0
                assert box["x"] + box["width"] <= width + 1
                assert box["y"] + box["height"] <= height + 1
                marks.last.focus()
                marks.last.press("Enter")
                # Tooltip now includes the marker title and explanation only.
                assert "Цитата или переданная речь" not in page.locator("#manualTooltip").inner_text()
                assert page.locator("#manualTooltip h3").count() > 0
                marks.last.press("Escape")
                assert not page.locator("#manualTooltip").is_visible()
                marks.first.focus()
                marks.first.press(" ")
                assert marks.first.get_attribute("aria-expanded") == "true"
                assert page.evaluate("window.injected") is None
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                with page.expect_download() as download:
                    page.locator("#manualDownload").click()
                assert json.loads(Path(download.value.path()).read_text()) == expected
                page.screenshot(path=f"/tmp/media-strazh-manual-{width}.png")
                page.locator("#manualEdit").click()
                assert page.locator("#manualText").is_visible()
                assert page.locator("#manualText").input_value() == document["text"]
                assert not page.locator("#manualTooltip").is_visible()
                assert not page.locator("#manualResult").is_visible()
                edited = document["text"] + "\nПредставители киевского режима покинули встречу."
                page.locator("#manualText").fill(edited)
                page.locator("#manualSubmit").click()
                page.locator("#manualResult").wait_for(state="visible", timeout=120000)
                assert page.locator("#manualTextEvidence").inner_text() == edited
                assert "киевского режима" in page.locator("#manualTextEvidence mark").all_text_contents()
                page.locator("#manualForm button[type=reset]").click()
                assert not page.locator("#manualResult").is_visible()
                assert page.locator("#manualText").input_value() == ""

            # One span may carry several techniques; all explanations remain available.
            overlap_text = "Политики опасны без смирительной рубашки."
            page.locator("#manualText").fill(overlap_text)
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            overlap = page.locator("#manualTextEvidence mark")
            assert overlap.count() == 1
            overlap.hover()
            assert set(page.locator("#manualTooltip h3").all_text_contents()) == {"Образ врага", "Эвфемизмы и дисфемизмы"}
            page.locator("#manualForm button[type=reset]").click()
            page.locator("#manualText").fill("Открылась городская библиотека.")
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            assert page.locator("#manualTextEvidence mark").count() == 0
            assert "Совпадений текущих правил не найдено" in page.locator("#manualState").inner_text()
            assert page.locator("#manualWarnings p").count() == 2
            page.locator("#manualForm button[type=reset]").click()

            page.locator("#manualText").fill("   ")
            page.locator("#manualSubmit").click()
            assert page.locator("#manualError").is_visible()
            page.locator("#manualTitle").fill("1234567890")
            page.locator("#manualText").fill("а" * 199995)
            page.locator("#manualSubmit").click()
            assert "200 000" in page.locator("#manualError").inner_text()
            page.locator("#manualForm button[type=reset]").click()

            page.locator('[data-mode="automatic"]').click()
            page.select_option("#source", "rt")
            displayed = json.loads((site / "data/analysis.json").read_text())["articles"]
            assert page.locator(".publication").count() == sum(a["publisher_id"] == "rt" and bool(a.get("findings")) for a in displayed)

            # Both platforms belong to one outlet; URL guards use its configured hosts/channel.
            snapshot = json.loads((site / "data/analysis.json").read_text())
            fixture = copy.deepcopy(snapshot)
            fixture["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            source_meta = {source["id"]: source for source in fixture["sources"]}
            sample = copy.deepcopy(displayed[0])
            # The published feed can contain zero matches; seed a deterministic
            # finding so filtering and the details dialog can be tested reliably.
            sample["findings"] = [{
                "rule_id": "fixture.test_marker",
                "category": "emotional_evaluation",
                "label": "Эмоциональная оценка",
                "status": "needs_review",
                "explanation": "Тестовое объяснение найденного признака.",
                "review_question": "Проверен ли источник?",
                "evidence": [],
            }]
            fixture["articles"] = []
            for number, source_id in enumerate(("rt", "rt_telegram", "interfax", "oldlentach_telegram"), 1):
                metadata = source_meta[source_id]
                item = copy.deepcopy(sample)
                item.update(id=number, source_id=source_id, publisher_id=metadata["publisher_id"],
                            platform=metadata["platform"], source=metadata["name"])
                item["url"] = (f'https://t.me/{metadata["channel"]}/123'
                               if metadata["platform"] == "telegram"
                               else f'https://{metadata["allowed_hosts"][0]}/news/123')
                item["summary"]["review_fragments"] = 0
                item["summary"]["candidate_fragments"] = 0
                if source_id == "rt_telegram":
                    item["title"] = ""
                    item["message_preview"] = "Городская библиотека открыла новый читальный зал."
                    item["findings"] = []
                    item["forwarded"] = True
                fixture["articles"].append(item)
                metadata["displayed"] = 1
                metadata["status"] = {"last_attempt_at": snapshot["generated_at"],
                                      "last_success_at": snapshot["generated_at"],
                                      "last_error": "HTTP 403" if source_id == "interfax" else None,
                                      "next_attempt_at": None}
            fixture["totals"].update(displayed=4, analyzed=4, with_review_candidates=0)
            page.route("**/data/analysis.json", lambda route: route.fulfill(json=fixture))
            page.reload()
            page.locator(".publication").first.wait_for()
            assert page.locator("#collectionStatus").count() == 0
            assert page.locator("#source option").count() == 18  # Preserve user's existing choices, including Other.
            assert "иноагент" in page.locator('#source option[value="meduza"]').inner_text()
            assert "нежелательная организация" in page.locator('#source option[value="meduza"]').inner_text()
            assert "нежелательная организация" in page.locator('#source option[value="novayagazeta"]').inner_text()
            assert "иноагент" in page.locator('#source option[value="currenttime"]').inner_text()
            assert "нежелательная организация" in page.locator('#source option[value="dw"]').inner_text()
            assert "иноагент" not in page.locator('#source option[value="rt"]').inner_text()
            # Status is attached to publisher identity; platform-specific channel names do not decide it.
            page.evaluate("""() => {
                const item = report.articles.find(item => item.source_id === 'rt');
                item.source_id = 'test_custom_source';
                item.publisher_id = 'meduza';
                render();
            }""")
            assert page.locator(".publication .legal-status-tag").count() >= 2
            page.evaluate("""() => {
                const item = report.articles.find(item => item.source_id === 'test_custom_source');
                item.source_id = 'rt';
                item.publisher_id = 'rt';
                render();
            }""")

            assert not page.locator("#sources").is_visible()
            assert "HTTP 403" in page.locator("#sources").text_content()
            assert "Подборка давно не обновлялась" in page.locator("#updated").text_content()
            for width, height in ((375, 812), (1024, 768), (1280, 900)):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=f"/tmp/media-strazh-automatic-{width}.png")
            page.select_option("#platform", "telegram")
            page.select_option("#source", "lenta")
            assert page.locator(".publication").count() == 0
            page.select_option("#source", "other")
            assert page.locator(".publication").count() == 1  # Other Telegram publisher has a detected finding.
            page.select_option("#platform", "")
            page.select_option("#source", "rt")
            assert page.locator(".publication").count() == 1
            assert page.locator("#marker option").count() == 11
            page.select_option("#marker", "emotional_evaluation")
            assert page.locator(".publication").count() == 1
            page.select_option("#marker", "fear")
            assert page.locator(".publication").count() == 0
            assert page.locator("#marker option").count() == 11  # Options do not vanish when results are empty.
            page.select_option("#marker", "")
            page.select_option("#platform", "telegram")
            assert page.locator(".publication").count() == 0
            page.select_option("#platform", "website")
            assert page.locator(".publication").count() == 1
            assert page.locator(".publication .source-link").get_attribute("href") == fixture["articles"][0]["url"]
            page.locator(".publication .auto-details-button").click()
            assert page.locator("#automaticModal").is_visible()
            page.locator("#automaticModalClose").click()
            assert not page.locator("#automaticModal").is_visible()
            for url in ("https://evil.russian.rt.com/news/123", "https://russian.rt.com.evil.example/news/123"):
                page.evaluate("url => { report.articles.find(item => item.source_id === 'rt').url = url; render(); }", url)
                assert page.locator(".publication .source-link").count() == 0, url
            page.evaluate("() => { report.articles.find(item => item.source_id === 'rt').summary = null; render(); }")
            assert "Анализ текущей версии отсутствует" in page.locator(".publication > .badge").inner_text()
            page.unroute("**/data/analysis.json")
            page.route("**/data/analysis.json", lambda route: route.fulfill(status=503, body="unavailable"))
            page.reload()
            page.locator("#error").wait_for(state="visible")
            page.locator('[data-mode="manual"]').click()
            page.locator("#manualTitle").fill(document["title"])
            page.locator("#manualText").fill(document["text"])
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            assert page.locator("#manualTextEvidence mark").count() == 2

            # Runtime failure and recovery in a fresh cache/context.
            context = browser.new_context()
            failure = context.new_page()
            failure.on("pageerror", lambda error: errors.append(str(error)))
            failure.route("**/vendor/pyodide/**",
                          lambda route: route.fulfill(status=503, body="unavailable"))
            failure.goto(base + "/analysis.html")
            failure.locator('[data-mode="manual"]').click()
            failure.locator("#manualText").fill(document["text"])
            failure.locator("#manualSubmit").click()
            failure.locator("#manualError").wait_for(state="visible", timeout=120000)
            assert not failure.locator("#manualSubmit").is_disabled()
            failure.unroute("**/vendor/pyodide/**")
            failure.locator("#manualSubmit").click()
            failure.locator("#manualResult").wait_for(state="visible", timeout=120000)
            stalled = []
            failure.route("**/vendor/pyodide/pyodide.js", lambda route: stalled.append(route))
            failure.reload()
            failure.locator('[data-mode="manual"]').click()
            failure.locator("#manualText").fill(document["text"])
            with failure.expect_request("**/vendor/pyodide/pyodide.js"):
                failure.locator("#manualSubmit").click()
            assert failure.locator("#manualSubmit").is_disabled()
            failure.locator("#manualForm button[type=reset]").click()
            assert not failure.locator("#manualResult").is_visible()
            assert failure.locator("#manualText").input_value() == ""
            assert not failure.locator("#manualSubmit").is_disabled()
            assert not failure.locator("#manualError").is_visible()
            for route in stalled:
                route.abort()
            failure.unroute("**/vendor/pyodide/pyodide.js")
            context.close()

            inline_touch_and_overlap(browser, base, errors, requests)
            contextual_analysis_ui(browser, base, site, errors, requests)
            pro_business_navigation_ui(browser, base)
            assert not errors, errors
            from urllib.parse import unquote
            assert all(
                method == "GET"
                and body is None
                and document["text"] not in unquote(url)
                and document["title"] not in unquote(url)
                for method, url, body in requests
            ), "Manual text was sent over the network"
            browser.close()
            print(json.dumps({"viewports": [375, 1024, 1280], "manual_ui": "passed",
                              "download_and_unicode": "passed", "empty_and_oversized_input": "passed",
                              "missing_snapshot": "passed", "runtime_retry_and_reset": "passed",
                              "automatic_filter": "passed", "touch_and_overlapping_evidence": "passed",
                              "manual_input_not_transmitted": True}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
