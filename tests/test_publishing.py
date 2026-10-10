import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from media_strazh.analysis import VERSION
from media_strazh.collector import collect_once
from media_strazh.publishing import ROOT, build_site, snapshot
from media_strazh.sources import SOURCES
from media_strazh.storage import Store
from test_collector import BODY, FakeNetwork, NOW, page


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.database = self.path / "corpus.sqlite3"
        self.store = Store(self.database)
        self.network = FakeNetwork()

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def collect(self):
        return collect_once(self.store, client_factory=self.network, now=lambda: NOW)

    def test_report_contains_real_metadata_without_article_bodies_or_raw_html(self):
        self.collect()
        result = snapshot(self.store)
        self.assertEqual(result["algorithm_version"], VERSION)
        self.assertEqual(result["totals"], {"displayed": 3, "analyzed": 3,
                                           "with_review_candidates": 0, "review_fragments": 0})
        self.assertEqual({item["source_id"] for item in result["articles"]}, {"rt", "tass", "ria"})
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(BODY, encoded)
        self.assertNotIn("raw_html_gzip", encoded)
        self.assertNotIn("document", result["articles"][0])
        before = self.store.status()
        snapshot(self.store)
        self.assertEqual(self.store.status(), before)

    def test_quoted_cues_are_separate_from_active_review_fragments(self):
        for source_id, suffix in (("rt", " Все знают о решении."),
                                  ("ria", " «Все знают о решении».")):
            source = SOURCES[source_id]
            url = f"https://{source.host}/news/1"
            self.network.responses[url] = page(source, url, BODY + suffix)
        self.collect()
        result = snapshot(self.store)
        self.assertEqual(result["totals"]["with_review_candidates"], 1)
        self.assertEqual(result["totals"]["review_fragments"], 1)
        ria = next(item for item in result["articles"] if item["source_id"] == "ria")
        self.assertEqual(ria["summary"]["quoted_candidates"], 1)
        self.assertEqual(ria["summary"]["review_fragments"], 0)
        for item in result["articles"]:
            original = self.store.article(item["id"])["document"]
            for finding in item["findings"]:
                for evidence in finding["evidence"]:
                    self.assertEqual(original[evidence["field"]][evidence["start"]:evidence["end"]],
                                     evidence["quote"])

    def test_failed_tass_access_is_visible_without_invented_tass_articles(self):
        self.network.blocked_article_sources.add("tass")
        self.assertFalse(self.collect()["success"])
        result = snapshot(self.store)
        tass = next(source for source in result["sources"] if source["id"] == "tass")
        self.assertEqual(tass["displayed"], 0)
        self.assertIn("403", tass["status"]["last_error"])
        self.assertEqual(result["totals"]["analyzed"], 2)

    def test_missing_current_analysis_is_not_reported_as_zero_findings(self):
        self.collect()
        article = self.store.articles("rt")[0]
        with self.store.db:
            self.store.db.execute("DELETE FROM analyses WHERE revision_id=?", (article["revision_id"],))
        result = snapshot(self.store)
        rt = next(item for item in result["articles"] if item["source_id"] == "rt")
        self.assertIsNone(rt["summary"])
        self.assertIsNone(rt["algorithm_version"])
        self.assertEqual(result["totals"]["analyzed"], 2)
        self.assertEqual(result["totals"]["displayed"], 3)

    def test_bounded_selection_counts_only_displayed_articles(self):
        self.collect()
        result = snapshot(self.store, limit=1)
        self.assertEqual(result["totals"]["displayed"], 1)
        self.assertEqual(sum(source["displayed"] for source in result["sources"]), 1)
        with self.assertRaises(ValueError):
            snapshot(self.store, limit=0)

    def test_empty_cycle_preserves_previous_output(self):
        target = self.path / "site"
        (target / "data").mkdir(parents=True)
        previous = target / "data" / "analysis.json"
        previous.write_text('{"previous":"successful"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Нет публикаций"):
            build_site(self.store, target)
        self.assertEqual(previous.read_text(), '{"previous":"successful"}')
        self.assertFalse((target / "index.html").exists())

    def test_public_build_contains_site_assets_but_no_database_or_python(self):
        self.collect()
        target = self.path / "site"
        result = build_site(self.store, target)
        self.assertTrue((target / "analysis.html").is_file())
        self.assertTrue((target / "analysis.js").is_file())
        self.assertTrue((target / "index.html").is_file())
        self.assertEqual((target / "CNAME").read_bytes(), (ROOT / "CNAME").read_bytes())
        self.assertEqual(result["totals"]["analyzed"], 3)
        self.assertEqual(json.loads((target / "data" / "analysis.json").read_text())["totals"]["displayed"], 3)
        self.assertFalse(any(target.rglob("*.sqlite3")))
        self.assertFalse(any(target.rglob("*.py")))
        self.assertFalse((target / ".git").exists())
        self.assertFalse((target / "exports").exists())
        self.assertFalse((target / "docs").exists())

    def test_site_builder_rejects_writing_over_repository(self):
        with self.assertRaises(ValueError):
            build_site(self.store, ROOT)
        with self.assertRaises(ValueError):
            build_site(self.store, ROOT / "data")

    def test_output_with_unrelated_files_cannot_be_published(self):
        self.collect()
        target = self.path / "site"
        target.mkdir()
        private = target / "corpus.sqlite3"
        private.write_text("retained private data")
        with self.assertRaisesRegex(ValueError, "посторонние файлы"):
            build_site(self.store, target)
        self.assertEqual(private.read_text(), "retained private data")
        self.assertFalse((target / "index.html").exists())

    def test_output_symlink_cannot_redirect_public_data(self):
        self.collect()
        target = self.path / "site"
        target.mkdir()
        other = self.path / "other"
        other.mkdir()
        (target / "data").symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "посторонние файлы"):
            build_site(self.store, target)
        self.assertEqual(list(other.iterdir()), [])

    def test_unsafe_publisher_link_prevents_publication(self):
        self.collect()
        with self.store.db:
            self.store.db.execute("UPDATE revisions SET canonical_url='javascript:alert(1)'")
        with self.assertRaises(ValueError):
            snapshot(self.store)

    def test_cli_builds_site_and_returns_failure_for_empty_corpus(self):
        self.collect()
        command = [sys.executable, "-m", "media_strazh", "build-site", "--db", str(self.database),
                   "--output", str(self.path / "site")]
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["totals"]["analyzed"], 3)
        command[command.index("--db") + 1] = str(self.path / "empty.sqlite3")
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Нет публикаций", result.stderr)
        self.assertEqual(json.loads((self.path / "site" / "data" / "analysis.json").read_text())["totals"]["analyzed"], 3)
