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

    modules = (test_analysis, test_rhetoric, test_expanded_rhetoric)
    originals = [module.analyze for module in modules]
    for module in modules:
        module.analyze = capture
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(test_analysis.AnalysisTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_rhetoric.RhetoricTests),
        unittest.defaultTestLoader.loadTestsFromTestCase(test_expanded_rhetoric.ExpandedRhetoricTests),
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
                assert page.locator("#manualFindings .finding").count() == len(expected["findings"])
                assert page.locator("#manualResult img").count() == 0
                assert page.evaluate("window.injected") is None
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                with page.expect_download() as download:
                    page.locator("#manualDownload").click()
                assert json.loads(Path(download.value.path()).read_text()) == expected
                page.screenshot(path=f"/tmp/media-strazh-manual-{width}.png")
                page.locator("#manualForm button[type=reset]").click()
                assert not page.locator("#manualResult").is_visible()
                assert page.locator("#manualText").input_value() == ""

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
            assert page.locator(".publication").count() == sum(a["publisher_id"] == "rt" for a in displayed)

            # Both platforms belong to one outlet; URL guards use its configured hosts/channel.
            snapshot = json.loads((site / "data/analysis.json").read_text())
            fixture = copy.deepcopy(snapshot)
            fixture["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            source_meta = {source["id"]: source for source in fixture["sources"]}
            sample = copy.deepcopy(displayed[0])
            fixture["articles"] = []
            for number, source_id in enumerate(("rt", "rt_telegram", "interfax"), 1):
                metadata = source_meta[source_id]
                item = copy.deepcopy(sample)
                item.update(id=number, source_id=source_id, publisher_id=metadata["publisher_id"],
                            platform=metadata["platform"], source=metadata["name"])
                item["url"] = (f'https://t.me/{metadata["channel"]}/123'
                               if metadata["platform"] == "telegram"
                               else f'https://{metadata["allowed_hosts"][0]}/news/123')
                item["summary"]["review_fragments"] = 0
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
            fixture["totals"].update(displayed=3, analyzed=3, with_review_candidates=0)
            page.route("**/data/analysis.json", lambda route: route.fulfill(json=fixture))
            page.reload()
            page.locator("#collectionState").filter(has_text="с ошибками").wait_for()
            assert page.locator("#collectionState").is_visible()
            assert "Подборка давно не обновлялась" in page.locator("#collectionState").inner_text()
            assert page.locator("#collectionStatus").get_attribute("open") is None
            assert page.locator("#source option").count() == 17  # All outlets, without duplicate platforms.
            page.locator("#collectionStatus > summary").click()
            assert page.locator("#sources").is_visible()
            assert "HTTP 403" in page.locator("#sources").inner_text()
            for width, height in ((375, 812), (1024, 768), (1280, 900)):
                page.set_viewport_size({"width": width, "height": height})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=f"/tmp/media-strazh-automatic-{width}.png")
            page.select_option("#source", "rt")
            assert page.locator(".publication").count() == 2
            page.select_option("#platform", "telegram")
            assert page.locator(".publication").count() == 1
            assert page.locator(".publication h2").inner_text() == fixture["articles"][1]["message_preview"]
            assert "Это пересланное сообщение" in page.locator(".publication").inner_text()
            assert page.locator(".publication .source-link").get_attribute("href") == fixture["articles"][1]["url"]
            page.locator(".publication summary").click()
            assert "Совпадений текущих правил не найдено" in page.locator(".publication details").inner_text()
            page.evaluate("() => { report.articles.find(item => item.platform === 'telegram').summary.review_fragments = 1; render(); }")
            page.locator("#candidates").check()
            assert page.locator(".publication").count() == 1
            page.select_option("#platform", "website")
            assert page.locator(".publication").count() == 0
            page.locator("#candidates").uncheck()
            assert page.locator(".publication").count() == 1
            page.select_option("#platform", "telegram")
            for url in ("https://evil.t.me/rt_russian/123", "https://t.me/other_channel/123",
                        "https://t.me/rt_russian", "https://t.me/rt_russian/123?other=1",
                        "https://russian.rt.com/news/123"):
                page.evaluate("url => { report.articles.find(item => item.platform === 'telegram').url = url; render(); }", url)
                assert page.locator(".publication .source-link").count() == 0, url
            page.select_option("#platform", "website")
            page.evaluate("() => { report.articles.find(item => item.source_id === 'rt').url = 'https://evil.russian.rt.com/news/123'; render(); }")
            assert page.locator(".publication .source-link").count() == 0
            page.evaluate("() => { report.articles.find(item => item.source_id === 'rt').summary = null; render(); }")
            assert "Анализ текущей версии отсутствует" in page.locator(".publication > .badge").inner_text()
            assert "Найдено фрагментов для проверки: 0" not in page.locator(".publication").inner_text()
            page.unroute("**/data/analysis.json")
            page.route("**/data/analysis.json", lambda route: route.fulfill(status=503, body="unavailable"))
            page.reload()
            page.locator("#error").wait_for(state="visible")
            page.locator('[data-mode="manual"]').click()
            page.locator("#manualTitle").fill(document["title"])
            page.locator("#manualText").fill(document["text"])
            page.locator("#manualSubmit").click()
            page.locator("#manualResult").wait_for(state="visible", timeout=120000)
            assert page.locator("#manualFindings .finding").count() == len(expected["findings"])

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
                              "automatic_filter": "passed", "only_same_origin_get_requests": True}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
