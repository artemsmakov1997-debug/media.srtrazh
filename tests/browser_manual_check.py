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
import test_latest_media_rhetoric
import test_quantitative_cues
import test_event_terminology
import test_territory_terminology
import test_oct15_rhetoric
import test_hostile_rhetoric
import test_context_precision
import test_historical_juxtaposition
import test_comparative_framing
import test_person_labels
import test_literature_rhetoric
import test_numeric_consistency
import test_discourse_expansion
import test_political_vocabulary
import test_political_framing
import test_collective_accusations


def select_analysis_filter(page, selector, value):
    """Select directly: filters must be visible without an extra disclosure action."""
    assert page.locator(selector).is_visible()
    page.select_option(selector, value)


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

    modules = (test_analysis, test_rhetoric, test_expanded_rhetoric, test_contextual_rhetoric, test_latest_media_rhetoric, test_quantitative_cues, test_event_terminology, test_territory_terminology, test_oct15_rhetoric, test_hostile_rhetoric, test_context_precision, test_historical_juxtaposition, test_person_labels, test_comparative_framing, test_literature_rhetoric, test_numeric_consistency, test_discourse_expansion, test_political_vocabulary, test_political_framing, test_collective_accusations)
    originals = [module.analyze for module in modules]
    for module in modules:
        module.analyze = capture
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(test_analysis.AnalysisTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_rhetoric.RhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_expanded_rhetoric.ExpandedRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_contextual_rhetoric.ContextualRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_latest_media_rhetoric.LatestMediaRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_quantitative_cues.QuantitativeCueTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_event_terminology.EventTerminologyTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_territory_terminology.TerritoryTerminologyTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_oct15_rhetoric.OctoberRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_hostile_rhetoric.HostileRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_context_precision.ContextPrecisionTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_historical_juxtaposition.HistoricalJuxtapositionTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_person_labels.PersonLabelTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_comparative_framing.ComparativeFramingTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_literature_rhetoric.LiteratureRhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_numeric_consistency.NumericConsistencyTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_discourse_expansion.DiscourseExpansionTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_political_vocabulary.PoliticalVocabularyTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_political_framing.PoliticalFramingTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_collective_accusations.CollectiveAccusationTests),
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


def annotation_tool_ui(browser, base, errors, requests):
    """Synthetic browser fixture, separate from the real unlabelled corpus."""
    from test_benchmark import record
    from media_strazh.benchmark import evaluate_benchmark
    rows = [record(1, '📰 Все знают о решении.'), record(2, 'Открыта городская библиотека.')]
    markup = (ROOT / 'media_strazh/annotation.html').read_text()
    payload = ('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n').encode()
    for mobile in (False, True):
        context = browser.new_context(viewport={'width': 375 if mobile else 1280, 'height': 812},
                                      is_mobile=mobile, has_touch=mobile, accept_downloads=True)
        try:
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append((request.method, request.url, request.post_data)))
            page.route('**/annotation-review-fixture.html', lambda route: route.fulfill(body=markup, content_type='text/html'))
            page.goto(base + '/annotation-review-fixture.html')
            page.locator('#file').set_input_files({'name': 'development.jsonl', 'mimeType': 'application/x-ndjson', 'buffer': payload})
            page.locator('#workspace').wait_for(state='visible')
            assert set(page.locator('#category option').evaluate_all('els => els.map(el => el.value)')) == set(rows[0]['annotation_categories'])
            assert page.locator('#source').is_hidden()
            assert page.locator('#bodyText').inner_text() == rows[0]['document']['text']
            page.locator('#reviewer').fill('Synthetic UI reviewer')
            page.evaluate("""() => {const node=document.querySelector('#bodyText').firstChild,range=document.createRange();
              const start=node.textContent.indexOf('Все знают');range.setStart(node,start);range.setEnd(node,start+'Все знают'.length);
              const selection=getSelection();selection.removeAllRanges();selection.addRange(range);}
            """)
            page.wait_for_function("document.getElementById('selection').textContent.includes('Все знают')")
            page.select_option('#category', 'generalization')
            page.locator('#add').click()
            assert page.locator('#spans li').count() == 1
            page.locator('#complete').click()
            assert 'подтвердите' in page.locator('#message').inner_text()
            page.locator('#completeCheck').check();page.locator('#complete').click()
            page.locator('#next').click()
            assert page.locator('#spans li').count() == 0
            page.locator('#completeCheck').check();page.locator('#complete').click()
            assert 'Проверено: 2 из 2' in page.locator('#progress').inner_text()
            with page.expect_download() as download:
                page.locator('#export').click()
            reviewed = [json.loads(line) for line in Path(download.value.path()).read_text().splitlines()]
            span = reviewed[0]['spans'][0]
            assert (span['start'], span['end'], span['quote']) == (2, 11, 'Все знают')
            assert reviewed[1]['fully_annotated'] and reviewed[1]['labels'] == []
            assert evaluate_benchmark(reviewed)['metrics']['exact_spans_with_status']['tp'] == 1
            page.locator('#note').fill('Заметка после предыдущей выгрузки.')
            page.locator('#reopen').click()
            page.once('dialog', lambda dialog: dialog.accept())
            page.reload()
            page.locator('#file').set_input_files({'name': 'reviewed-development.jsonl', 'mimeType': 'application/x-ndjson', 'buffer': ('\n'.join(json.dumps(r,ensure_ascii=False) for r in reviewed)+'\n').encode()})
            page.locator('#workspace').wait_for(state='visible')
            assert 'Проверено: 1 из 2' in page.locator('#progress').inner_text()
            assert page.locator('#spans li').count() == 1
            page.locator('#next').click()
            assert page.locator('#note').input_value() == 'Заметка после предыдущей выгрузки.'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('img').count() == 0
        finally:
            context.close()


def quantitative_manual_ui(browser, base, errors, requests):
    text = test_quantitative_cues.RADIOSVOBODA_EXCERPT
    expected = analyze({"text": text})["findings"]
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            page.goto(base + "/analysis.html")
            page.locator('[data-mode="manual"]').click()
            page.locator("#manualText").fill(text)
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            marks = page.locator("#manualTextEvidence mark")
            assert marks.all_text_contents() == [f["evidence"][0]["quote"] for f in expected]
            assert page.locator("#manualTextEvidence").inner_text() == text
            for index, finding in enumerate(expected):
                trigger = marks.nth(index)
                if mobile:
                    trigger.tap()
                else:
                    trigger.hover()
                page.locator("#manualTooltip").wait_for(state="visible")
                assert finding["explanation"] in page.locator("#manualTooltip").inner_text()
                if mobile:
                    trigger.tap()
            assert page.locator("#manualWarnings p").all_text_contents() == [
                "Найденные признаки требуют проверки; они не доказывают манипуляцию, намерение автора или ложность фактов.",
                "Отсутствие признаков не означает нейтральность текста.",
            ]
            page.locator("#manualEdit").click()
            assert page.locator("#manualText").input_value() == text
            from urllib.parse import unquote
            assert all(text not in unquote(url) and body is None for _, url, body in requests)
        finally:
            context.close()


def hostile_rhetoric_manual_ui(browser, base, errors, requests):
    """User passages retain text, overlapping cues, attribution and touch tips."""
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            page.goto(base + "/analysis.html")
            page.locator('[data-mode="manual"]').click()
            for text, phrase in ((test_hostile_rhetoric.VANNACCI_POST, "Бутафорного"),
                                 (test_hostile_rhetoric.HOSTILE_POST, "киевскую вошь"),
                                 (test_person_labels.DOCUMENT["text"], "клоун")):
                page.locator("#manualText").fill(text)
                page.locator("#manualSubmit").click()
                page.locator("#manualResult").wait_for(state="visible", timeout=120000)
                assert page.locator("#manualTextEvidence").inner_text() == text
                expected = analyze({"text": text})
                marks = page.locator("#manualTextEvidence mark")
                for finding in expected["findings"]:
                    assert marks.filter(has_text=finding["evidence"][0]["quote"]).count() or all(
                        page.locator("#manualTextEvidence").evaluate("(el, span) => {let offset=0,covered=0; for(const node of el.childNodes){const length=Array.from(node.textContent).length;if(node.nodeName==='MARK')covered+=Math.max(0,Math.min(span[1],offset+length)-Math.max(span[0],offset));offset+=length;}return covered===span[1]-span[0];}", [e["start"], e["end"]])
                        for e in finding["evidence"])
                trigger = marks.filter(has_text=phrase).first
                if mobile:
                    trigger.tap()
                else:
                    trigger.hover()
                page.locator("#manualTooltip").wait_for(state="visible")
                expected_explanation = next(f["explanation"] for f in expected["findings"] if phrase in f["evidence"][0]["quote"])
                assert expected_explanation in page.locator("#manualTooltip").inner_text()
                if text == test_hostile_rhetoric.HOSTILE_POST:
                    assert marks.filter(has_text="не хочет мириться").first.get_attribute("data-status") == "quoted_candidate"
                assert page.locator("#manualWarnings p").count() == 2
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.locator("#manualEdit").click()
                assert page.locator("#manualText").input_value() == text
        finally:
            context.close()


def person_labels_automatic_ui(browser, base, site, errors, requests):
    """Both political targets have the same saved markers and readable tooltip."""
    document = test_person_labels.DOCUMENT
    expected = analyze(document)
    snapshot = json.loads((site / "data/analysis.json").read_text())
    item = copy.deepcopy(snapshot["articles"][0])
    item.pop("variants", None)  # This fixture constructs a different publication.
    item.pop("publication_id", None)
    item.update(title="Обозначения политических участников", summary=expected["summary"],
                findings=expected["findings"], display_excerpt=document["text"], findings_omitted=0)
    snapshot["articles"] = [item]
    for mobile in (False, True):
        context = browser.new_context(viewport={"width":375 if mobile else 1280, "height":812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
            page.goto(base + "/analysis.html")
            select_analysis_filter(page, "#marker", "euphemism_dysphemism")
            assert page.locator(".publication").count() == 1
            page.locator(".auto-details-button").click()
            marks = page.locator("#automaticModal mark")
            assert marks.all_text_contents() == [f["evidence"][0]["quote"] for f in expected["findings"]]
            marks.first.tap() if mobile else marks.first.hover()
            page.locator("#automaticTooltip").wait_for(state="visible")
            assert expected["findings"][0]["explanation"] in page.locator("#automaticTooltip").inner_text()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            context.close()


def terminology_layer_ui(browser, base, site, errors, requests):
    terms = (*test_event_terminology.CASES.values(),
             test_territory_terminology.CASES["terminology.occupied_territory"],
             test_territory_terminology.CASES["terminology.liberated_territory"])
    document = {"title": test_territory_terminology.HEADLINE,
                "text": "\n".join(terms) + "\nПолитзаключённый освобождён."}
    expected = analyze(document)
    snapshot = json.loads((site / "data/analysis.json").read_text())
    source = next(source for source in snapshot["sources"] if source["id"] == "mediazona_telegram")
    item = copy.deepcopy(snapshot["articles"][0])
    item.pop("variants", None)  # This fixture constructs a different publication.
    item.pop("publication_id", None)
    item.update(id=1, source_id=source["id"], source=source["name"], publisher_id="mediazona",
                platform="telegram", title=document["title"], summary=expected["summary"], findings=expected["findings"],
                display_excerpt=document["text"], findings_omitted=0, url="https://t.me/mediazzzona/1")
    snapshot["articles"] = [item]
    snapshot["totals"] = {"displayed": 1, "analyzed": 1, "with_review_candidates": 0, "review_fragments": 0}
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
            page.goto(base + "/analysis.html")
            select_analysis_filter(page, "#source", "mediazona")
            select_analysis_filter(page, "#marker", "event_terminology")
            assert page.locator(".publication").count() == 1
            select_analysis_filter(page, "#marker", "territory_terminology")
            assert page.locator(".publication").count() == 1
            assert page.locator(".publication .legal-status-tag").all_text_contents() == ["иноагент"]
            assert ("Найдено фрагментов для проверки: " + str(expected["summary"]["marker_fragments"])) in page.locator(".publication > .badge").inner_text()
            assert "С фрагментами для проверки: 1." in page.locator("#totals").inner_text()
            page.locator(".auto-details-button").click()
            page.locator("#automaticModal").wait_for(state="visible")
            marks = page.locator("#automaticModal mark")
            assert marks.count() == len(expected["findings"])
            if mobile:
                marks.first.tap()
            else:
                marks.first.hover()
            page.locator("#automaticTooltip").wait_for(state="visible")
            assert "Информационная отметка" in page.locator("#automaticTooltip").inner_text()
            assert "Отрицание или обсуждение" not in page.locator("#automaticTooltip").inner_text()
            if mobile:
                marks.first.tap()
                page.locator("#automaticTooltip").wait_for(state="hidden")
            if mobile:
                marks.last.tap()
            else:
                marks.last.hover()
            page.locator("#automaticTooltip").wait_for(state="visible")
            assert "кто дал такую оценку" in page.locator("#automaticTooltip").inner_text()
            assert "Информационная отметка" in page.locator("#automaticTooltip").inner_text()
            page.locator("#automaticModalClose").click()
            page.locator('[data-mode="manual"]').click()
            page.locator("#manualTitle").fill(document["title"])
            page.locator("#manualText").fill(document["text"])
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            marks = page.locator("#manualTitleEvidence mark, #manualTextEvidence mark")
            assert marks.count() == len(expected["findings"])
            for index, finding in enumerate(expected["findings"]):
                if mobile:
                    marks.nth(index).tap()
                else:
                    marks.nth(index).hover()
                page.locator("#manualTooltip").wait_for(state="visible")
                assert finding["explanation"] in page.locator("#manualTooltip").inner_text()
                assert page.locator("#manualTooltip h3").all_text_contents() == [finding["label"]]
                if mobile:
                    marks.nth(index).tap()
            with page.expect_download() as download_info:
                page.locator("#manualDownload").click()
            exported = json.loads(Path(download_info.value.path()).read_text())
            assert exported == expected
            assert exported["summary"]["candidate_fragments"] == 0
        finally:
            context.close()


def context_precision_ui(browser, base, site, errors, requests):
    """The screenshot regressions agree in saved automatic and local manual views."""
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            for document, literal in ((test_context_precision.SCHOOL_DOCUMENT, "истерика"),
                                      (test_context_precision.INSECTS_DOCUMENT, "насекомых")):
                expected = analyze(document)
                snapshot = json.loads((site / "data/analysis.json").read_text())
                item = copy.deepcopy(snapshot["articles"][0])
                item.pop("variants", None)  # This fixture constructs a different publication.
                item.pop("publication_id", None)
                item.update(title=document["title"], summary=expected["summary"], findings=expected["findings"],
                            display_excerpt=document["text"], findings_omitted=0)
                snapshot["articles"] = [item]
                snapshot["totals"] = {"displayed": 1, "analyzed": 1, "with_review_candidates": 0, "review_fragments": 0}
                page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
                page.goto(base + "/analysis.html")
                if expected["findings"]:
                    page.locator(".auto-details-button").click()
                    page.locator("#automaticModal").wait_for(state="visible")
                    assert page.locator("#automaticModal mark").filter(has_text=literal).count() == 0
                    assert ("Найдено фрагментов для проверки: " + str(expected["summary"]["marker_fragments"])) in page.locator(".publication > .badge").inner_text()
                    page.locator("#automaticModalClose").click()
                else:
                    page.wait_for_function("document.getElementById('selection').textContent === 'Показано публикаций: 0.'")
                    assert page.locator(".publication").count() == 0
                page.locator('[data-mode="manual"]').click()
                page.locator("#manualTitle").fill(document["title"])
                page.locator("#manualText").fill(document["text"])
                page.locator("#manualSubmit").click()
                page.locator("#manualResult").wait_for(state="visible", timeout=120000)
                assert page.locator("#manualTextEvidence").inner_text() == document["text"]
                assert page.locator("#manualTextEvidence mark").filter(has_text=literal).count() == 0
                assert page.locator("#manualWarnings p").count() == 2
                with page.expect_download() as download_info:
                    page.locator("#manualDownload").click()
                assert json.loads(Path(download_info.value.path()).read_text()) == expected
                page.unroute("**/data/analysis.json")
        finally:
            context.close()


def comparative_framing_ui(browser, base, site, errors, requests):
    """Notices, visual limits and new rhetoric use the existing interface."""
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            for text in (test_comparative_framing.HISTORICAL_TEXT, test_comparative_framing.COMPARISON_TEXT):
                document = {"text": text}
                automatic = analyze({**document, "media": {"image_count": 2}})
                manual = analyze(document)
                snapshot = json.loads((site / "data/analysis.json").read_text())
                item = copy.deepcopy(snapshot["articles"][0])
                item.pop("variants", None)  # This fixture constructs a different publication.
                item.pop("publication_id", None)
                item.update(title="Проверочная публикация", summary=automatic["summary"], findings=automatic["findings"],
                            display_excerpt=text, findings_omitted=0)
                snapshot["articles"] = [item]
                page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
                page.goto(base + "/analysis.html")
                select_analysis_filter(page, "#marker", "rhetorical_context")
                assert page.locator(".publication").count() == 1
                page.locator(".auto-details-button").click()
                page.locator("#automaticModal").wait_for(state="visible")
                mark = page.locator("#automaticModal mark").first
                mark.tap() if mobile else mark.hover()
                page.locator("#automaticTooltip").wait_for(state="visible")
                tooltip = page.locator("#automaticTooltip").inner_text()
                assert "Информационная отметка" in tooltip
                if text == test_comparative_framing.COMPARISON_TEXT:
                    assert "Сравнение иллюстраций" in tooltip
                    assert "не анализировал" in tooltip
                else:
                    assert "Историческая отсылка" in tooltip
                    assert ("Найдено фрагментов для проверки: " + str(automatic["summary"]["marker_fragments"])) in page.locator(".publication > .badge").inner_text()
                page.locator("#automaticModalClose").click()
                page.locator('[data-mode="manual"]').click()
                page.locator("#manualText").fill(text)
                page.locator("#manualSubmit").click()
                page.locator("#manualResult").wait_for(state="visible", timeout=120000)
                assert page.locator("#manualTextEvidence").inner_text() == text
                marks = page.locator("#manualTextEvidence mark")
                assert marks.count() > 0
                marks.first.tap() if mobile else marks.first.hover()
                page.locator("#manualTooltip").wait_for(state="visible")
                assert manual["findings"][0]["explanation"] in page.locator("#manualTooltip").inner_text()
                assert page.locator("#manualWarnings p").count() == 2
                with page.expect_download() as download:
                    page.locator("#manualDownload").click()
                assert json.loads(Path(download.value.path()).read_text()) == manual
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.unroute("**/data/analysis.json")
        finally:
            context.close()


def historical_juxtaposition_ui(browser, base, site, errors, requests):
    """The same multi-passage finding is visible in automatic and manual views."""
    text = test_historical_juxtaposition.USER_TEXT
    expected = analyze({"text": text})
    finding = expected["findings"][0]
    quotes = [e["quote"] for e in finding["evidence"]]
    for mobile in (False, True):
        context = browser.new_context(viewport={"width": 375 if mobile else 1280, "height": 812},
                                      is_mobile=mobile, has_touch=mobile)
        try:
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
            snapshot = json.loads((site / "data/analysis.json").read_text())
            item = copy.deepcopy(snapshot["articles"][0])
            item.pop("variants", None)  # This fixture constructs a different publication.
            item.pop("publication_id", None)
            item.update(title="Сопоставление заявлений", summary=expected["summary"], findings=expected["findings"],
                        display_excerpt=text, findings_omitted=0)
            snapshot["articles"] = [item]
            page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
            page.goto(base + "/analysis.html")
            page.locator(".auto-details-button").click()
            page.locator("#automaticModal").wait_for(state="visible")
            assert page.locator("#automaticModal mark").all_text_contents() == quotes
            assert "Найдено фрагментов для проверки: 4" in page.locator(".publication > .badge").inner_text()
            mark = page.locator("#automaticModal mark").nth(1)
            mark.tap() if mobile else mark.hover()
            page.locator("#automaticTooltip").wait_for(state="visible")
            assert finding["explanation"] in page.locator("#automaticTooltip").inner_text()
            if not mobile:
                tooltip = page.locator("#automaticTooltip")
                tooltip.hover()
                page.wait_for_timeout(200)  # Allow the marker's hide timer to expire.
                assert tooltip.is_visible()  # Hovering the comment keeps it readable.
                assert tooltip.evaluate("tip => getComputedStyle(tip).fontSize") == "16px"
                assert abs(tooltip.bounding_box()["width"] - 480) < 1
                page.set_viewport_size({"width": 1280, "height": 420})
                mark.hover()
                tooltip.wait_for(state="visible")
                tooltip.hover()
                assert tooltip.evaluate("tip => tip.scrollHeight > tip.clientHeight")
                page.mouse.wheel(0, 120)
                page.wait_for_function("document.getElementById('automaticTooltip').scrollTop > 0")
                assert tooltip.is_visible()
                box = tooltip.bounding_box()
                assert box["y"] >= 0 and box["y"] + box["height"] <= 421
                page.set_viewport_size({"width": 1280, "height": 812})
            page.locator("#automaticModalClose").click()
            page.locator('[data-mode="manual"]').click()
            page.locator("#manualText").fill(text)
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            assert page.locator("#manualTextEvidence").inner_text() == text
            assert page.locator("#manualTextEvidence mark").all_text_contents() == quotes
            mark = page.locator("#manualTextEvidence mark").nth(1)
            mark.tap() if mobile else mark.hover()
            page.locator("#manualTooltip").wait_for(state="visible")
            assert finding["explanation"] in page.locator("#manualTooltip").inner_text()
            if not mobile:
                tooltip = page.locator("#manualTooltip")
                assert tooltip.evaluate("tip => getComputedStyle(tip).fontSize") == "16px"
                page.wait_for_function("getComputedStyle(document.getElementById('manualTooltip')).opacity === '1'")
                assert abs(tooltip.bounding_box()["width"] - 480) < 1
                page.emulate_media(reduced_motion="reduce")
                assert tooltip.evaluate("tip => getComputedStyle(tip).transitionDuration") == "0s"
                page.emulate_media(reduced_motion="no-preference")
            assert page.locator("#manualWarnings p").count() == 2
            with page.expect_download() as download:
                page.locator("#manualDownload").click()
            assert json.loads(Path(download.value.path()).read_text()) == expected
            from urllib.parse import unquote
            assert all(text not in unquote(url) and body is None for _, url, body in requests)
        finally:
            context.close()


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


def literature_rhetoric_ui(browser, base, site, errors, requests, document_keys=None):
    """Real native/Wasm output, inline comments and counters on desktop and touch."""
    for mobile in (False, True):
        context = browser.new_context(viewport={'width': 375 if mobile else 1280, 'height': 900},
                                      is_mobile=mobile, has_touch=mobile, accept_downloads=True)
        try:
            page = context.new_page()
            # Keep the emulated phone on touch throughout: a mouse click can
            # hover a marker as the dialog opens, making its first tap close it.
            def activate(selector):
                target = page.locator(selector)
                target.tap() if mobile else target.click()
            page.add_init_script("""window.literaturePointerTypes=[];
                document.addEventListener('pointerdown',event=>{
                    if(event.target.closest('button,mark')) literaturePointerTypes.push(event.pointerType);
                },true);""")
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append((request.method, request.url, request.post_data)))
            documents = {**test_literature_rhetoric.DOCUMENTS, **test_numeric_consistency.DOCUMENTS,
                         **test_discourse_expansion.DOCUMENTS, **test_political_vocabulary.DOCUMENTS,
                         **test_political_framing.DOCUMENTS, **test_collective_accusations.DOCUMENTS}
            keys = document_keys or ('guilt_pressure', 'inaccessible_evidence', 'precision_without_method', 'repeated_slogan',
                        'numeric_majority', 'numeric_daily', 'question_deflection', 'consequence_chain',
                        'circular_justification', 'absence_as_concealment', 'unspecified_measures', 'unattributed_decision',
                        'geopolitical_west', 'collective_west', 'western_partners', 'putinoid_group', 'vatnik_group',
                        'occupier_actor', 'liberator_actor', 'propagandist_actor',
                        'denazification', 'demilitarization', 'anti_russian', 'liberal_actor',
                        'political_persecution', 'repression', 'oppression', 'ideological_slur',
                        'bought_voice', 'double_standards', 'betrayal_label', 'collective_full', 'collective_hook')
            for key in keys:
                document = {'title': 'Проверочный пример', **documents[key]}
                expected = analyze(document)
                snapshot = json.loads((site / 'data/analysis.json').read_text())
                item = copy.deepcopy(snapshot['articles'][0])
                item.pop("variants", None)  # This fixture constructs a different publication.
                item.pop("publication_id", None)
                item.update(title=document['title'], display_excerpt=document['text'],
                            summary=expected['summary'], findings=expected['findings'], findings_omitted=0,
                            algorithm_version=expected['algorithm_version'])
                snapshot['articles'] = [item]
                snapshot['totals'].update(displayed=1, analyzed=1, with_markers=1)
                page.route('**/data/analysis.json', lambda route: route.fulfill(json=snapshot))
                page.goto(base + '/analysis.html')
                page.locator('.publication').wait_for()
                count = expected['summary']['marker_fragments']
                assert 'Найдено фрагментов для проверки: ' + str(count) in page.locator('.publication > .badge').inner_text()
                assert 'С фрагментами для проверки: 1.' in page.locator('#totals').inner_text()
                select_analysis_filter(page, '#marker', expected['findings'][0]['category'])
                assert page.locator('.publication').count() == 1
                activate('.auto-details-button')
                marker = page.locator('#automaticModal mark').first
                if mobile:
                    assert page.locator('#automaticTooltip').is_hidden(), (key, 'No mouse hover before the first tap')
                marker.tap() if mobile else marker.hover()
                page.locator('#automaticTooltip').wait_for(state='visible')
                assert expected['findings'][0]['explanation'] in page.locator('#automaticTooltip').inner_text()
                if mobile:
                    marker.tap()
                    page.locator('#automaticTooltip').wait_for(state='hidden')
                    marker.tap()
                    page.locator('#automaticTooltip').wait_for(state='visible')
                page.wait_for_function("getComputedStyle(document.getElementById('automaticTooltip')).opacity === '1'")
                assert page.locator('#automaticModalClose').evaluate('''button => {
                    const rect = button.getBoundingClientRect();
                    return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
                }'''), (mobile, key, 'The comment must leave the close control reachable')
                activate('#automaticModalClose')
                activate('[data-mode="manual"]')
                page.locator('#manualTitle').fill(document['title'])
                page.locator('#manualText').fill(document['text'])
                activate('#manualSubmit')
                page.locator('#manualResult').wait_for(state='visible', timeout=120000)
                assert page.locator('#manualTextEvidence').inner_text() == document['text']
                if key == 'collective_full':
                    # The loaded question and its national-essence claim overlap.
                    # Rendered segments may merge/split; counters count evidence.
                    highlighted = page.locator('#manualTextEvidence mark').all_text_contents()
                    for phrase in ('всем известны', 'дементник', 'русские - да, они очень хотят войны'):
                        assert any(phrase in segment for segment in highlighted), (mobile, phrase, highlighted)
                else:
                    assert page.locator('#manualTextEvidence mark').count() == count
                marker = page.locator('#manualTextEvidence mark').first
                marker.tap() if mobile else marker.hover()
                page.locator('#manualTooltip').wait_for(state='visible')
                assert expected['findings'][0]['explanation'] in page.locator('#manualTooltip').inner_text()
                with page.expect_download() as download_info:
                    activate('#manualDownload')
                assert json.loads(Path(download_info.value.path()).read_text()) == expected
                assert set(page.evaluate('literaturePointerTypes')) == ({'touch'} if mobile else {'mouse'}), (mobile, key)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.unroute('**/data/analysis.json')
        finally:
            context.close()


def contextual_analysis_ui(browser, base, site, errors, requests):
    """A quoted-only publication must remain visible under the candidate filter."""
    document = {"title": "", "text": test_contextual_rhetoric.BLAHA_TEXT}
    expected = analyze(document)
    snapshot = json.loads((site / "data/analysis.json").read_text())
    source = next(source for source in snapshot["sources"] if source["id"] == "izvestia_telegram")
    item = copy.deepcopy(snapshot["articles"][0])
    item.pop("variants", None)  # This fixture constructs a different publication.
    item.pop("publication_id", None)
    item.update(id=253503, source_id=source["id"], publisher_id=source["publisher_id"],
                platform="telegram", source=source["name"], title="", forwarded=True,
                display_excerpt="Эксперты обсудили изменения медиарынка и представили результаты исследования.",
                message_preview="Forwarded from Test channel " + document["text"][:160],
                url="https://t.me/izvestia/253503",
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
        assert page.locator("#marker option").count() == 15  # Ten candidate types, four informational layers, and all.
        marker = expected["findings"][0]["category"]
        select_analysis_filter(page, "#marker", marker)
        assert page.locator(".publication").count() == 1
        select_analysis_filter(page, "#marker", "")
        assert "Найдено фрагментов для проверки: 12" in page.locator(".publication > .badge").inner_text()
        assert page.locator(".legal-status-note").count() == 0
        assert page.locator(".publication-title").count() == 1
        # Telegram captions are not headlines; never show "Forwarded from"
        # or truncate an arbitrary message preview into a fake title.
        heading = page.locator(".publication-title")
        assert heading.inner_text() == "Эксперты обсудили изменения медиарынка и представили результаты исследования."
        assert "Forwarded from" not in heading.inner_text()
        assert "…" not in heading.inner_text()
        assert heading.evaluate("el => getComputedStyle(el).webkitLineClamp") == "none"
        assert heading.evaluate("el => el.scrollHeight <= el.clientHeight + 1")
        # The narrow layout keeps both actions readable and aligned.
        page.set_viewport_size({"width": 375, "height": 812})
        details_box = page.locator(".publication .auto-details-button").bounding_box()
        source_box = page.locator(".publication .source-link").bounding_box()
        assert details_box["x"] + details_box["width"] <= source_box["x"] + 1
        assert abs(details_box["y"] - source_box["y"]) < 2
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1280, "height": 900})
        # On desktop the source action belongs to the card's bottom-right.
        source = page.locator(".publication .source-link")
        card_box = page.locator(".publication").bounding_box()
        source_box = source.bounding_box()
        details_box = page.locator(".publication .auto-details-button").bounding_box()
        assert abs((source_box["x"] + source_box["width"]) -
                   (card_box["x"] + card_box["width"] - 20)) < 4
        assert source_box["x"] > details_box["x"] + details_box["width"]
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
        # An animated, accessible visual preview is shown only while the worker
        # is running and then removed when the annotated result is ready.
        page.locator("#manualScan").wait_for(state="visible", timeout=5000)
        assert "головорезов" in page.locator("#manualScanPreview").inner_text()
        page.locator("#manualResult").wait_for(state="visible", timeout=120000)
        assert not page.locator("#manualScan").is_visible()
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



def new_media_filters_ui(browser, base, site, errors, requests):
    """Local fixtures test the three publisher choices across their platforms."""
    snapshot = json.loads((site / "data/analysis.json").read_text())
    sources = {source["id"]: source for source in snapshot["sources"]}
    sample = copy.deepcopy(snapshot["articles"][0])
    sample.pop("variants", None)
    sample.pop("publication_id", None)
    snapshot["articles"] = []
    for number, source_id in enumerate(("aif", "aif_telegram", "inosmi", "inosmi_telegram", "smotri_telegram", "mediazona_telegram"), 1):
        source = sources[source_id]
        document = {"title": "" if source["platform"] == "telegram" else "Решение правительства",
                    "text": "Власти приняли возмутительное решение."}
        result = analyze(document)
        item = copy.deepcopy(sample)
        item.update(id=number, source_id=source_id, source=source["name"], publisher_id=source["publisher_id"],
                    platform=source["platform"], title=document["title"], summary=result["summary"],
                    findings=result["findings"], display_excerpt=document["text"], findings_omitted=0,
                    url=f'https://t.me/{source["channel"]}/1' if source["platform"] == "telegram" else f'https://{source["allowed_hosts"][0]}/news/1')
        snapshot["articles"].append(item)
    context = browser.new_context(viewport={"width": 375, "height": 812})
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append((request.method, request.url, request.post_data)))
        page.route("**/data/analysis.json", lambda route: route.fulfill(json=snapshot))
        page.goto(base + "/analysis.html")
        page.locator(".publication").first.wait_for()
        assert page.locator(".publication").count() == 6
        for publisher in ("aif", "inosmi"):
            select_analysis_filter(page, "#source", publisher)
            select_analysis_filter(page, "#platform", "")
            assert page.locator(".publication").count() == 2
            select_analysis_filter(page, "#platform", "website")
            assert page.locator(".publication").count() == 1
            select_analysis_filter(page, "#platform", "telegram")
            assert page.locator(".publication").count() == 1
        select_analysis_filter(page, "#source", "smotri")
        assert page.locator(".publication").count() == 1
        assert page.locator(".source-link").get_attribute("href") == "https://t.me/smotri_media/1"
        select_analysis_filter(page, "#source", "mediazona")
        assert page.locator(".publication").count() == 1
        assert page.locator(".source-link").get_attribute("href") == "https://t.me/mediazzzona/1"
        assert page.locator(".publication .legal-status-tag").all_text_contents() == ["иноагент"]
        select_analysis_filter(page, "#platform", "website")
        assert page.locator(".publication").count() == 0
        select_analysis_filter(page, "#platform", "")
        select_analysis_filter(page, "#source", "other")
        assert page.locator(".publication").count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        print("New publisher and platform filters passed", flush=True)
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
            select_analysis_filter(page, "#source", "rt")
            displayed = json.loads((site / "data/analysis.json").read_text())["articles"]
            assert page.locator(".publication").count() == sum(a["publisher_id"] == "rt" and bool(a.get("findings")) for a in displayed)

            # Both platforms belong to one outlet; URL guards use its configured hosts/channel.
            snapshot = json.loads((site / "data/analysis.json").read_text())
            fixture = copy.deepcopy(snapshot)
            fixture["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            source_meta = {source["id"]: source for source in fixture["sources"]}
            sample = copy.deepcopy(displayed[0])
            sample.pop("variants", None)
            sample.pop("publication_id", None)
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
                item["summary"]["marker_fragments"] = 0
                item["summary"]["marker_count"] = 0
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
            assert page.locator("#source option").count() == 22  # Existing choices plus Медиазона.
            assert "иноагент" in page.locator('#source option[value="mediazona"]').inner_text()
            assert "нежелательная организация" not in page.locator('#source option[value="mediazona"]').inner_text()
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
            select_analysis_filter(page, "#platform", "telegram")
            select_analysis_filter(page, "#source", "lenta")
            assert page.locator(".publication").count() == 0
            select_analysis_filter(page, "#source", "other")
            assert page.locator(".publication").count() == 1  # Other Telegram publisher has a detected finding.
            select_analysis_filter(page, "#platform", "")
            select_analysis_filter(page, "#source", "rt")
            assert page.locator(".publication").count() == 1
            assert page.locator("#marker option").count() == 15
            select_analysis_filter(page, "#marker", "emotional_evaluation")
            assert page.locator(".publication").count() == 1
            select_analysis_filter(page, "#marker", "fear")
            assert page.locator(".publication").count() == 0
            assert page.locator("#marker option").count() == 15  # Options do not vanish when results are empty.
            select_analysis_filter(page, "#marker", "")
            select_analysis_filter(page, "#platform", "telegram")
            assert page.locator(".publication").count() == 0
            select_analysis_filter(page, "#platform", "website")
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
            quantitative_manual_ui(browser, base, errors, requests)
            annotation_tool_ui(browser, base, errors, requests)
            hostile_rhetoric_manual_ui(browser, base, errors, requests)
            person_labels_automatic_ui(browser, base, site, errors, requests)
            terminology_layer_ui(browser, base, site, errors, requests)
            context_precision_ui(browser, base, site, errors, requests)
            historical_juxtaposition_ui(browser, base, site, errors, requests)
            comparative_framing_ui(browser, base, site, errors, requests)
            literature_rhetoric_ui(browser, base, site, errors, requests)
            contextual_analysis_ui(browser, base, site, errors, requests)
            new_media_filters_ui(browser, base, site, errors, requests)
            from browser_pro_check import pro_ui
            pro_ui(browser, base, site)
            from browser_photo_context_check import photo_ui
            photo_ui(browser, base)
            from browser_public_check import public_ui
            public_ui(browser, base, site)
            from browser_rating_check import rating_ui
            rating_ui(browser, base, site, errors, requests)
            from browser_archive_check import archive_ui
            archive_ui(browser, base, site)
            from browser_crossposts_check import crosspost_ui
            crosspost_ui(browser, base, site, errors)
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
