import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from media_strazh.analysis import VERSION, analyze
from media_strazh.collector import collect_once
from media_strazh.extraction import FeedEntry
from media_strazh.publishing import ROOT, bounded_findings, build_site, snapshot, telegram_display_excerpt
from media_strazh.sources import SOURCES
from media_strazh.storage import Store
from test_collector import BODY, FakeNetwork, NOW, page
from browser_fixtures import runtime_fixture
from test_contextual_rhetoric import BLAHA_TEXT


class PublishingTests(unittest.TestCase):
    def test_bounded_findings_keeps_rare_markers_and_source_order(self):
        findings = analyze({"text": "Возмутительное решение. " * 45 + "Неминуемая катастрофа."})["findings"]
        selected = bounded_findings(findings)
        self.assertEqual(len(selected), 40)
        self.assertEqual({f["category"] for f in selected}, {"emotional_evaluation", "fear"})
        self.assertEqual([f["evidence"][0]["start"] for f in selected],
                         sorted(f["evidence"][0]["start"] for f in selected))
        self.assertEqual(bounded_findings(findings[:12]), findings[:12])
        self.assertEqual(bounded_findings([]), [])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.database = self.path / "corpus.sqlite3"
        self.store = Store(self.database)
        self.network = FakeNetwork()
        self.runtime = runtime_fixture(self.path / "runtime")

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def collect(self):
        return collect_once(self.store, [SOURCES[name] for name in ("rt", "tass", "ria")],
                            client_factory=self.network, now=lambda: NOW)

    def save_item(self, source_id, number, published_at=NOW, source=None):
        source = source or SOURCES[source_id]
        path = f"/{source.channel}/{number}" if source.platform == "telegram" else f"/news/{number}"
        url = f"https://{source.host}{path}"
        document = {"title": "" if source.platform == "telegram" else "Новая библиотека",
                    "text": BODY, "source": source.name,
                    "url": url, "published_at": published_at}
        self.store.discover(source.id, [FeedEntry(url, document["title"], published_at)], NOW)
        article = next(row for row in self.store.due(source.id, NOW, 100) if row["url"] == url)
        self.store.save(article, {"document": document, "extractor_version": "fixture",
                        "extraction_method": "fixture"}, page(source, url), analyze(document), NOW, 3600)

    def test_telegram_display_phrase_removes_forwarding_and_never_truncates(self):
        text = ("Forwarded from Новая-Европа: истории\n"
                "✊ Удары по «Яндексу» оттягивают суверенизацию Рунета, "
                "но на восстановление потребуется много времени. "
                "Это следующее предложение не является заголовком.\n"
                "Продолжение новости.")
        phrase = telegram_display_excerpt(text, forwarded=True)
        self.assertEqual(phrase, "Удары по «Яндексу» оттягивают суверенизацию Рунета, "
                                 "но на восстановление потребуется много времени.")
        self.assertNotIn("Forwarded from", phrase)
        self.assertNotIn("…", phrase)
        self.assertEqual(telegram_display_excerpt(
            "Короткая заметка без завершающей точки", forwarded=False),
            "Короткая заметка без завершающей точки")
        self.assertEqual(telegram_display_excerpt("А" * 500, forwarded=False), "")

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

    def test_automatic_analysis_keeps_quoted_signals_in_published_summary(self):
        source = SOURCES["rt"]
        url = f"https://{source.host}/news/1"
        self.network.responses[url] = page(source, url, text=BLAHA_TEXT)
        collect_once(self.store, [source], client_factory=self.network, now=lambda: NOW)
        item = snapshot(self.store)["articles"][0]
        saved = self.store.article(item["id"])["analysis"]
        self.assertEqual(item["algorithm_version"], VERSION)
        self.assertEqual(item["summary"]["review_fragments"], 0)
        self.assertEqual(item["summary"]["candidate_fragments"], 11)
        self.assertEqual(item["findings"], [{key: f[key] for key in
                         ("category", "label", "rule_id", "status", "explanation", "review_question", "evidence")}
                        for f in saved["findings"]])

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

    def test_current_analysis_is_selected_before_a_newer_unanalyzed_item(self):
        self.save_item("rt", 1, "2026-10-10T08:00:00+00:00")
        self.save_item("rt", 2, "2026-10-10T10:00:00+00:00")
        recent = self.store.articles("rt")[0]
        with self.store.db:
            self.store.db.execute("DELETE FROM analyses WHERE revision_id=?", (recent["revision_id"],))
        result = snapshot(self.store, limit=1)
        self.assertTrue(result["articles"][0]["url"].endswith("/news/1"))
        self.assertIsNotNone(result["articles"][0]["summary"])

    def test_unanalyzed_source_cannot_hide_an_available_current_result(self):
        self.save_item("bbc", 1)
        self.save_item("rt", 1)
        bbc = self.store.articles("bbc")[0]
        with self.store.db:
            self.store.db.execute("DELETE FROM analyses WHERE revision_id=?", (bbc["revision_id"],))
        result = snapshot(self.store, limit=1)
        self.assertEqual(result["articles"][0]["source_id"], "rt")

    def test_bounded_selection_counts_only_displayed_articles(self):
        self.collect()
        result = snapshot(self.store, limit=1)
        self.assertEqual(result["totals"]["displayed"], 1)
        self.assertEqual(sum(source["displayed"] for source in result["sources"]), 1)
        with self.assertRaises(ValueError):
            snapshot(self.store, limit=0)

    def test_older_detected_findings_survive_bounded_snapshot(self):
        source = SOURCES["rt"]
        url = f"https://{source.host}/news/1"
        self.network.responses[url] = page(source, url, text=BODY + " Все знают о решении.")
        collect_once(self.store, [source], client_factory=self.network, now=lambda: NOW)
        self.save_item("rt", 2, NOW)
        report = snapshot(self.store, limit=1)
        self.assertEqual(len(report["articles"]), 1)
        self.assertTrue(report["articles"][0]["url"].endswith("/news/1"))
        self.assertTrue(report["articles"][0]["findings"])

    def test_busy_source_cannot_displace_website_or_telegram_feeds(self):
        for number in range(1, 8):
            self.save_item("rt", number, "2026-10-10T10:00:00+00:00")
        self.save_item("interfax", 1, "2026-10-10T08:00:00+00:00")
        self.save_item("rt_telegram", 1, "2026-10-10T07:00:00+00:00")
        result = snapshot(self.store, limit=3)
        self.assertEqual({row["source_id"] for row in result["articles"]},
                         {"rt", "interfax", "rt_telegram"})
        self.assertEqual([row["source_id"] for row in result["articles"]],
                         ["rt", "interfax", "rt_telegram"])

    def test_every_configured_feed_with_data_can_appear_in_default_pilot_limit(self):
        configured = [source for source in SOURCES.values() if not source.configuration_error]
        for source in configured:
            self.save_item(source.id, 1)
        result = snapshot(self.store, limit=100)
        self.assertEqual({item["source_id"] for item in result["articles"]},
                         {source.id for source in configured})
        self.assertEqual(len(result["sources"]), len(SOURCES))

    def test_public_registry_groups_platforms_and_exposes_unconfigured_channels(self):
        self.save_item("rt", 1)
        self.save_item("rt_telegram", 1)
        result = snapshot(self.store)
        telegram = next(row for row in result["sources"] if row["id"] == "rt_telegram")
        self.assertEqual(telegram["publisher_id"], "rt")
        self.assertEqual(telegram["platform"], "telegram")
        self.assertEqual(telegram["allowed_hosts"], ["t.me"])
        self.assertEqual(telegram["channel"], SOURCES["rt_telegram"].channel)
        self.assertTrue(all(row["publisher_id"] == "rt" for row in result["articles"]))
        for source in SOURCES.values():
            if source.configuration_error:
                metadata = next(row for row in result["sources"] if row["id"] == source.id)
                self.assertEqual(metadata["displayed"], 0)
                self.assertEqual(metadata["configuration_error"], source.configuration_error)

    def test_telegram_url_cannot_point_to_another_channel(self):
        self.save_item("rt_telegram", 1)
        with self.store.db:
            self.store.db.execute("UPDATE revisions SET canonical_url='https://t.me/unrelated_channel/1'")
        with self.assertRaises(ValueError):
            snapshot(self.store)

    def test_telegram_preview_is_bounded_without_inventing_a_headline(self):
        self.save_item("rt_telegram", 1)
        result = snapshot(self.store)
        item = result["articles"][0]
        self.assertEqual(item["title"], "")
        self.assertGreater(len(item["message_preview"]), 0)
        self.assertLessEqual(len(item["message_preview"]), 160)
        self.assertTrue(item["message_preview"].endswith("…"))
        self.assertEqual(item["summary"]["review_fragments"], 0)
        self.assertFalse(item["forwarded"])
        self.assertNotIn(BODY, json.dumps(result, ensure_ascii=False))

    def test_forwarded_telegram_posts_keep_attribution_without_changing_findings(self):
        self.save_item("rt_telegram", 1)
        self.save_item("rt_telegram", 2)
        source = SOURCES["rt_telegram"]
        with self.store.db:
            self.store.db.execute("UPDATE revisions SET extraction_method='telegram-web.forwarded' WHERE canonical_url=?",
                                  (f"https://t.me/{source.channel}/2",))
        result = snapshot(self.store)
        ordinary = next(row for row in result["articles"] if row["url"].endswith("/1"))
        forwarded = next(row for row in result["articles"] if row["url"].endswith("/2"))
        self.assertFalse(ordinary["forwarded"])
        self.assertTrue(forwarded["forwarded"])
        self.assertEqual(forwarded["summary"], ordinary["summary"])
        self.assertEqual(forwarded["findings"], ordinary["findings"])

    def test_stored_first_party_discovery_resolves_channel_without_a_broad_url_allowance(self):
        source = replace(SOURCES["interfax_telegram"], channel="", feed_url="",
                         configuration_error="Официальный канал ещё не подтверждён.")
        discovered = replace(source, channel="official_fixture_channel",
                             feed_url="https://t.me/s/official_fixture_channel", configuration_error="")
        # Only the collector writes this feed URL after first-party confirmation.
        self.store.source_result(discovered, NOW, True)
        self.save_item(source.id, 1, source=discovered)
        with patch.dict(SOURCES, {source.id: source}):
            result = snapshot(self.store)
        metadata = next(row for row in result["sources"] if row["id"] == source.id)
        self.assertEqual(metadata["channel"], discovered.channel)
        self.assertEqual(metadata["configuration_error"], "")
        self.assertEqual(result["articles"][0]["url"], "https://t.me/official_fixture_channel/1")
        with self.store.db:
            self.store.db.execute("UPDATE revisions SET canonical_url='https://t.me/another_fixture_channel/1'")
        with patch.dict(SOURCES, {source.id: source}), self.assertRaises(ValueError):
            snapshot(self.store)

    def test_invalid_stored_discovery_cannot_enable_an_unconfirmed_channel(self):
        self.save_item("rt", 1)
        source = replace(SOURCES["interfax_telegram"], channel="", feed_url="",
                         configuration_error="Официальный канал ещё не подтверждён.")
        forged = replace(source, feed_url="https://evil.t.me/s/official_fixture_channel")
        self.store.source_result(forged, NOW, False, "Invalid discovery")
        with patch.dict(SOURCES, {source.id: source}):
            result = snapshot(self.store)
        metadata = next(row for row in result["sources"] if row["id"] == source.id)
        self.assertEqual(metadata["channel"], "")
        self.assertTrue(metadata["configuration_error"])

    def test_empty_cycle_preserves_previous_output(self):
        target = self.path / "site"
        (target / "data").mkdir(parents=True)
        previous = target / "data" / "analysis.json"
        previous.write_text('{"previous":"successful"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Нет публикаций"):
            build_site(self.store, target, runtime_dir=self.runtime)
        self.assertEqual(previous.read_text(), '{"previous":"successful"}')
        self.assertFalse((target / "index.html").exists())

    def test_public_build_contains_site_assets_but_no_database_or_server_modules(self):
        self.collect()
        target = self.path / "site"
        result = build_site(self.store, target, runtime_dir=self.runtime)
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
        engine = json.loads((target / "data/manual-engine.json").read_text())
        self.assertEqual(set(engine["files"]), {"__init__.py", "analysis.py", "rules.py"})
        self.assertEqual(engine["algorithm_version"], VERSION)
        self.assertTrue((target / "vendor/pyodide/pyodide.asm.wasm").is_file())
        self.assertTrue((target / "vendor/pyodide/LICENSE.txt").is_file())

    def test_private_file_in_runtime_directory_is_not_copied(self):
        self.collect()
        (self.runtime / "corpus.sqlite3").write_text("private corpus")
        target = self.path / "site"
        build_site(self.store, target, runtime_dir=self.runtime)
        self.assertFalse(any(target.rglob("*.sqlite3")))
        build_site(self.store, target, runtime_dir=self.runtime)

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
            build_site(self.store, target, runtime_dir=self.runtime)
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
            build_site(self.store, target, runtime_dir=self.runtime)
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
                   "--output", str(self.path / "site"), "--runtime-dir", str(self.runtime)]
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["totals"]["analyzed"], 3)
        command[command.index("--db") + 1] = str(self.path / "empty.sqlite3")
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Нет публикаций", result.stderr)
        self.assertEqual(json.loads((self.path / "site" / "data" / "analysis.json").read_text())["totals"]["analyzed"], 3)
