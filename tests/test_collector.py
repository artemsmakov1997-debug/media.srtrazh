import gzip
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from media_strazh.analysis import VERSION, analyze
from media_strazh.collector import collect_once, reanalyze_current, reextract_current, selected_sources, watch
from media_strazh.extraction import FeedEntry, extract_article
from media_strazh.network import FetchError, Response
from media_strazh.server import Handler
from media_strazh.sources import SOURCES
from media_strazh.storage import Store, collection_lock, later

NOW = "2026-10-10T09:00:00.000000+00:00"
# Synthetic pages used only in temporary test databases.
BODY = ("Городская библиотека открыла новый читальный зал. Жители смогут пользоваться "
        "книгами и электронным каталогом. Расписание работы опубликовано на сайте учреждения.")


def page(source, url, text=BODY):
    article = {"@type": "NewsArticle", "url": url, "headline": "Новая библиотека",
               "articleBody": text, "datePublished": "2026-10-10T12:00:00+03:00"}
    html = '<script type="application/ld+json">' + json.dumps(article, ensure_ascii=False) + '</script>'
    return Response(url, html.encode(), "text/html", "utf-8")


class FakeNetwork:
    def __init__(self):
        self.responses, self.calls = {}, []
        self.blocked_article_sources = set()
        for source in SOURCES.values():
            url = f"https://{source.host}/news/1"
            feed = f'<rss><channel><item><title>Новая библиотека</title><link>{url}</link></item></channel></rss>'
            self.responses[source.feed_url] = Response(source.feed_url, feed.encode(), "application/rss+xml")
            self.responses[url] = page(source, url)
    def __call__(self, source):
        network = self
        class Client:
            robots_error = FetchError("robots.txt HTTP 403") if source.id in network.blocked_article_sources else None
            def get_feed(self):
                return self.get(source.feed_url)
            def get(self, url):
                network.calls.append(url)
                result = network.responses[url]
                if isinstance(result, Exception):
                    raise result
                return result
        return Client()


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "articles.sqlite3"
        self.store = Store(self.path)
        self.network = FakeNetwork()
    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()
    def collect(self, when=NOW, sources=None, limit=5):
        return collect_once(self.store, sources, limit=limit, client_factory=self.network, now=lambda: when)

    def test_all_three_sources_collected_analyzed_and_persisted(self):
        result = self.collect()
        self.assertTrue(result["success"])
        status = self.store.status()
        self.assertEqual((status["articles_collected"], status["revisions"], status["analyses"]), (3, 3, 3))
        items = self.store.articles()
        self.assertEqual({item["source_id"] for item in items}, {"rt", "tass", "ria"})
        detail = self.store.article(items[0]["id"])
        self.assertEqual(detail["revision_id"], items[0]["revision_id"])
        self.assertEqual(detail["document"]["text"], BODY)
        self.assertEqual(detail["analysis"]["summary"]["review_candidates"], 0)
        raw = self.store.db.execute("SELECT raw_html_gzip FROM revisions LIMIT 1").fetchone()[0]
        self.assertIn(b'NewsArticle', gzip.decompress(raw))

    def test_second_cycle_fetches_feeds_but_not_recent_articles(self):
        self.collect()
        first_calls = len(self.network.calls)
        result = self.collect(later(NOW, 300))
        self.assertEqual(len(self.network.calls) - first_calls, 3)
        self.assertEqual(sum(row["fetched"] for row in result["sources"].values()), 0)
        self.assertEqual(self.store.status()["revisions"], 3)

    def test_unchanged_revisit_does_not_duplicate_versions_or_analyses(self):
        self.collect()
        result = self.collect(later(NOW, 3601))
        self.assertEqual(sum(row["unchanged"] for row in result["sources"].values()), 3)
        self.assertEqual(self.store.status()["analyses"], 3)

    def test_changed_article_gets_new_version_and_updated_analysis(self):
        self.collect()
        rt = SOURCES["rt"]
        url = f"https://{rt.host}/news/1"
        self.network.responses[url] = page(rt, url, BODY + " Все знают о решении.")
        self.collect(later(NOW, 3601))
        self.assertEqual(self.store.status()["revisions"], 4)
        article = self.store.articles("rt")[0]
        detail = self.store.article(article["id"])
        self.assertEqual(detail["analysis"]["summary"]["by_category"], {"generalization": 1})
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM revisions WHERE article_id=?", (article["id"],)).fetchone()[0], 2)

    def test_failed_source_does_not_stop_other_sources_and_has_backoff(self):
        self.network.responses[SOURCES["tass"].feed_url] = FetchError("HTTP 429", retry_after=7200)
        result = self.collect()
        self.assertFalse(result["success"])
        self.assertEqual(self.store.status()["articles_collected"], 2)
        source = next(row for row in self.store.status()["sources"] if row["source_id"] == "tass")
        self.assertIsNone(source["last_success_at"])
        self.assertEqual(source["next_attempt_at"], later(NOW, 7200))
        self.network.calls.clear()
        second = self.collect(later(NOW, 300))
        self.assertNotIn(SOURCES["tass"].feed_url, self.network.calls)
        self.assertEqual(second["sources"]["tass"]["deferred_until"], later(NOW, 7200))

    def test_failed_article_retry_is_not_reset_by_rediscovery(self):
        source = SOURCES["ria"]
        url = f"https://{source.host}/news/1"
        self.network.responses[url] = FetchError("Timeout")
        result = self.collect(sources=[source])
        self.assertEqual(result["sources"]["ria"]["failed"], 1)
        self.network.calls.clear()
        self.collect(later(NOW, 60), [source])
        self.assertNotIn(url, self.network.calls)
        self.network.responses[url] = page(source, url)
        self.collect(later(NOW, 301), [source])
        self.assertEqual(self.store.status()["articles_collected"], 1)

    def test_public_feed_discovery_does_not_attempt_blocked_article_pages(self):
        source = SOURCES["tass"]
        self.network.blocked_article_sources.add(source.id)
        result = self.collect(sources=[source])
        self.assertTrue(result["sources"]["tass"]["feed_ok"])
        self.assertFalse(result["success"])
        self.assertEqual(self.store.status()["pending"], 1)
        self.assertEqual(result["sources"]["tass"]["failed"], 0)
        self.assertNotIn(f"https://{source.host}/news/1", self.network.calls)

    def test_short_preview_is_not_analyzed(self):
        source = SOURCES["ria"]
        url = f"https://{source.host}/news/1"
        self.network.responses[url] = Response(url, b'<div class="article__text">Preview</div>', "text/html")
        result = self.collect(sources=[source])
        self.assertFalse(result["success"])
        self.assertEqual(self.store.status()["analyses"], 0)
        self.assertEqual(self.store.status()["pending"], 1)

    def test_saved_article_survives_a_failed_update(self):
        source = SOURCES["rt"]
        self.collect(sources=[source])
        self.network.responses[f"https://{source.host}/news/1"] = FetchError("Temporary failure")
        self.collect(later(NOW, 3601), [source])
        detail = self.store.article(self.store.articles("rt")[0]["id"])
        self.assertEqual(detail["document"]["text"], BODY)
        self.assertEqual(detail["last_error"], "Temporary failure")

    def test_restart_preserves_state_and_retry_schedule(self):
        self.collect()
        with Store(self.path) as reopened:
            result = collect_once(reopened, client_factory=self.network, now=lambda: later(NOW, 300))
            self.assertEqual(reopened.status()["articles_collected"], 3)
            self.assertEqual(sum(row["fetched"] for row in result["sources"].values()), 0)

    def make_old_analyses(self):
        self.collect()
        rows = list(self.store.db.execute("SELECT revision_id,result_json FROM analyses"))
        with self.store.db:
            self.store.db.execute("DELETE FROM analyses")
            for row in rows:
                result = json.loads(row["result_json"])
                result["algorithm_version"] = "rules-0.1.0"
                self.store.db.execute("INSERT INTO analyses VALUES (?,?,?,?)",
                                      (row["revision_id"], "rules-0.1.0", NOW, json.dumps(result)))

    def test_reanalyze_adds_version_without_downloads_or_provenance_changes(self):
        self.make_old_analyses()
        before = [tuple(row) for row in self.store.db.execute("SELECT * FROM articles ORDER BY id")]
        revisions = [tuple(row) for row in self.store.db.execute("SELECT * FROM revisions ORDER BY id")]
        old_results = [tuple(row) for row in self.store.db.execute("SELECT * FROM analyses ORDER BY revision_id")]
        calls = list(self.network.calls)
        result = reanalyze_current(self.store, now=lambda: later(NOW, 100))
        self.assertEqual((result["processed"], result["new_analyses"]), (3, 3))
        self.assertEqual(self.network.calls, calls)
        self.assertEqual(before, [tuple(row) for row in self.store.db.execute("SELECT * FROM articles ORDER BY id")])
        self.assertEqual(revisions, [tuple(row) for row in self.store.db.execute("SELECT * FROM revisions ORDER BY id")])
        self.assertEqual(old_results, [tuple(row) for row in self.store.db.execute("SELECT * FROM analyses WHERE algorithm_version='rules-0.1.0' ORDER BY revision_id")])
        self.assertEqual(self.store.articles()[0]["algorithm_version"], VERSION)
        repeat = reanalyze_current(self.store, now=lambda: later(NOW, 200))
        self.assertEqual((repeat["processed"], repeat["new_analyses"]), (0, 0))

    def test_reanalyze_source_filter_and_invalid_source(self):
        self.make_old_analyses()
        result = reanalyze_current(self.store, ["rt"], now=lambda: later(NOW, 100))
        self.assertEqual(result["new_analyses"], 1)
        self.assertIsNotNone(self.store.articles("rt")[0]["analysis_summary"])
        self.assertIsNone(self.store.articles("ria")[0]["analysis_summary"])
        with self.assertRaises(ValueError):
            reanalyze_current(self.store, ["unknown"])

    def test_cli_reanalyze_uses_persisted_text(self):
        self.make_old_analyses()
        command = ["python3", "-m", "media_strazh", "reanalyze", "--db", str(self.path)]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["new_analyses"], 3)
        repeat = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(repeat.stdout)["new_analyses"], 0)

    def test_limit_keeps_unprocessed_links_for_next_cycle(self):
        source = SOURCES["ria"]
        urls = [f"https://{source.host}/news/{index}" for index in (1, 2)]
        feed = '<rss><channel>' + ''.join(f'<item><title>Title</title><link>{url}</link></item>' for url in urls) + '</channel></rss>'
        self.network.responses[source.feed_url] = Response(source.feed_url, feed.encode(), "application/xml")
        self.network.responses[urls[1]] = page(source, urls[1])
        self.collect(sources=[source], limit=1)
        self.assertEqual(self.store.status()["pending"], 1)
        self.collect(later(NOW, 300), [source], limit=1)
        self.assertEqual(self.store.status()["pending"], 0)

    def test_unannotated_export_cannot_be_confused_with_gold_labels(self):
        self.collect()
        exported = list(self.store.export_corpus())
        self.assertEqual(len(exported), 3)
        self.assertFalse(exported[0]["fully_annotated"])
        self.assertIsNone(exported[0]["labels"])
        self.assertNotIn("sha256", exported[0]["document"])
        self.assertEqual(analyze(exported[0]["document"])["document"]["sha256"], exported[0]["provenance"]["sha256"])

    def test_single_collector_lock_and_release(self):
        with collection_lock(self.path):
            with self.assertRaises(ValueError):
                with collection_lock(self.path):
                    pass
        with collection_lock(self.path):
            pass

    def test_retry_now_after_access_correction(self):
        source = SOURCES["tass"]
        good = self.network.responses[source.feed_url]
        self.network.responses[source.feed_url] = FetchError("Access denied")
        self.collect(sources=[source])
        self.network.responses[source.feed_url] = good
        self.store.retry_now([source.id], later(NOW, 10))
        self.assertTrue(self.collect(later(NOW, 10), [source])["success"])

    def test_feed_overrides_are_scoped_to_selected_publishers(self):
        selected = selected_sources(["ria"], {"ria": "https://ria.ru/export/rss2/index.xml"})
        self.assertEqual(selected[0].feed_url, "https://ria.ru/export/rss2/index.xml")
        with self.assertRaises(ValueError):
            selected_sources(["rt"], {"rt": "https://example.org/rss"})
        with self.assertRaises(ValueError):
            selected_sources(["rt"], {"ria": SOURCES["ria"].feed_url})

    def test_cli_status_and_export_from_persisted_database(self):
        self.collect()
        result = subprocess.run(["python3", "-m", "media_strazh", "status", "--db", str(self.path)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["articles_collected"], 3)
        output = Path(self.directory.name) / "corpus.jsonl"
        command = ["python3", "-m", "media_strazh", "export-corpus", "--db", str(self.path), "--output", str(output)]
        subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(len(output.read_text().splitlines()), 3)
        repeat = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(repeat.returncode, 2)
        self.assertEqual(len(output.read_text().splitlines()), 3)

    def test_reextract_fixes_retained_text_without_claiming_a_new_download(self):
        source = SOURCES["rt"]
        url = f"https://{source.host}/news/1"
        lead = "Вводный абзац с описанием события."
        response = Response(url, f'<div class="article__summary">{lead}</div><div class="article__text">{BODY}</div>'.encode(), "text/html")
        self.store.discover(source.id, [FeedEntry(url, "Новость")], NOW)
        article = self.store.due(source.id, NOW, 1)[0]
        old = {"document": {"title": "Новость", "text": BODY, "source": source.name, "url": url, "published_at": ""},
               "extractor_version": "html-0.1.0", "extraction_method": "html.publisher_body"}
        self.store.save(article, old, response, analyze(old["document"]), NOW, 3600)
        summary = reextract_current(self.store, now=lambda: later(NOW, 100))
        self.assertEqual(summary["new_revisions"], 1)
        detail = self.store.article(article["id"])
        self.assertEqual(detail["document"]["text"], lead + "\n" + BODY)
        self.assertEqual(detail["retrieved_at"], NOW)
        self.assertEqual(detail["last_fetched_at"], NOW)
        self.assertEqual(self.store.db.execute("SELECT next_attempt_at FROM articles").fetchone()[0], later(NOW, 3600))

    def test_watcher_runs_repeated_cycles_and_releases_lock(self):
        import threading
        from unittest.mock import patch
        class StopAfterTwo(threading.Event):
            def __init__(self): super().__init__(); self.cycles = 0
            def wait(self, timeout=None):
                self.cycles += 1
                if self.cycles == 2: self.set()
                return self.is_set()
        event = StopAfterTwo()
        with patch("builtins.print"):
            watch(self.path, [SOURCES["rt"]], interval=60, client_factory=self.network, stop_event=event)
        self.assertEqual(event.cycles, 2)
        self.assertEqual(self.store.status()["last_run"]["id"], 2)
        self.assertEqual(self.store.status()["articles_collected"], 1)
        with collection_lock(self.path): pass


class CollectionAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / "test.sqlite3"
        with Store(cls.path) as store:
            collect_once(store, client_factory=FakeNetwork(), now=lambda: NOW)
        class QuietHandler(Handler):
            def log_message(self, *args): pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.server.db_path = cls.path
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.directory.cleanup()
    def get(self, route):
        with urlopen(self.base + route, timeout=5) as response:
            return json.load(response)
    def test_list_filter_status_and_detail(self):
        items = self.get("/api/v1/articles?source=ria")["items"]
        self.assertEqual(len(items), 1)
        detail = self.get("/api/v1/articles/" + str(items[0]["id"]))
        self.assertEqual(detail["analysis"]["document"]["text"], BODY)
        self.assertEqual(self.get("/api/v1/collection/status")["articles_collected"], 3)
    def test_bad_parameters_and_missing_article(self):
        for route in ("/api/v1/articles?limit=0", "/api/v1/articles?source=unknown", "/api/v1/articles?offset=-1"):
            with self.assertRaises(HTTPError) as caught:
                self.get(route)
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/v1/articles/999999")
        self.assertEqual(caught.exception.code, 404)
    def test_archive_form_served(self):
        with urlopen(self.base + "/articles") as response:
            self.assertIn("Собранные публикации", response.read().decode())


if __name__ == "__main__":
    unittest.main()
