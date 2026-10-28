"""Aggregation contracts on synthetic publications, independent of detector accuracy."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.analysis import VERSION, analyze
from media_strazh.extraction import FeedEntry
from media_strazh.network import Response
from media_strazh.publishing import build_site, snapshot
from media_strazh.rating import rating_level, rating_snapshot
from media_strazh.sources import SOURCES
from media_strazh.storage import Store
from browser_fixtures import runtime_fixture

END = "2026-10-25T12:00:00+00:00"
START = "2026-10-24T12:00:00+00:00"


def save_publication(store, number, source_id="rt", published=END, findings=None, version=VERSION, text=None):
    source = SOURCES[source_id]
    path = f"/{source.channel}/{number}" if source.platform == "telegram" else f"/news/{number}"
    url = f"https://{source.host}{path}"
    document = {"title": "Проверочная публикация", "text": text or f"Синтетический материал номер {number}.",
                "source": source.name, "url": url, "published_at": published}
    store.discover(source_id, [FeedEntry(url, document["title"], published)], END)
    article = dict(store.db.execute("SELECT * FROM articles WHERE url=?", (url,)).fetchone())
    result = analyze(document)
    if findings is not None:
        result["findings"] = findings
    result["algorithm_version"] = version
    saved = store.save(article, {"document": document, "extractor_version": "fixture", "extraction_method": "fixture"},
                       Response(url, b"<p>synthetic fixture</p>", "text/html"), result, END, 3600)
    return article, saved


def finding(category="fear", status="needs_review", notice=False):
    return {"id": "fixture", "rule_id": "fixture." + category, "category": category, "status": status,
            "rating_weight": 1, "label": "Проверочный тип", "explanation": "Синтетический пример агрегации.",
            "review_question": "Проверочный вопрос.",
            "evidence": [{"field": "text", "start": 0, "end": 13, "quote": "Синтетический",
                          "sentence": {"start": 0, "end": 13, "text": "Синтетический", "truncated": True},
                          "context": {"informational_notice": notice}}]}


def browser_rating_fixture():
    """The same backend-generated report consumed by browser checks."""
    with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "rating.sqlite3") as store:
        for index in range(1, 5):
            saved_at = (datetime.fromisoformat(END) - timedelta(hours=24 - index * 5)).isoformat()
            save_publication(store, index, published=saved_at, findings=[finding()] if index == 1 else [])
        for index in range(1, 3):
            save_publication(store, index, source_id="tass", findings=[finding(status="quoted_candidate")] if index == 1 else [])
        save_publication(store, 1, source_id="ria", findings=[finding(), finding("enemy_image")])
        save_publication(store, 1, source_id="mediazona_telegram", findings=[finding("actor_terminology", "context_only", True)])
        # A contextual marker now contributes one vote out of five. Retain
        # neutral items so the desktop's three-card layout still includes RT.
        for index in range(2, 6):
            save_publication(store, index, source_id="mediazona_telegram", findings=[])
        save_publication(store, 1, source_id="kommersant", findings=[])
        return rating_snapshot(store, END)


class RatingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.store = Store(self.path / "corpus.sqlite3")

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def outlet(self, identifier="rt"):
        return next(row for row in rating_snapshot(self.store, END)["publishers"] if row["id"] == identifier)

    def test_exact_method_thresholds_include_25_and_50_in_yellow(self):
        for flagged, count, expected in ((0, 0, None), (0, 4, "green"), (1, 5, "green"),
                                         (1, 4, "yellow"), (1, 2, "yellow"), (3, 5, "red"),
                                         (499999, 2000000, "green"), (1000001, 2000000, "red")):
            self.assertEqual(rating_level(flagged, count), expected)

    def test_formula_uses_publications_once_and_counts_quoted_types(self):
        save_publication(self.store, 1, findings=[finding(), finding("enemy_image"), finding()])
        save_publication(self.store, 2, findings=[finding(status="quoted_candidate")])
        save_publication(self.store, 3, findings=[])
        save_publication(self.store, 4, findings=[finding("actor_terminology", "context_only", True)])
        item = self.outlet()
        self.assertEqual((item["collected"], item["analyzed"], item["flagged"], item["score_percent"], item["level"]),
                         (4, 4, 3, 75, "red"))
        self.assertEqual(item["by_type"], {"fear": 2, "enemy_image": 1, "actor_terminology": 1})

    def test_information_denial_discussion_and_omission_notices_now_create_votes(self):
        rows = [finding("territory_terminology", "context_only", True), finding("rhetorical_context", "context_only", True),
                finding("event_terminology", "context_only", True), finding("selective_context", "context_only"),
                finding("fear", "context_only"), finding("fear", "needs_review", True)]
        for number, marker in enumerate(rows, 1):
            save_publication(self.store, number, findings=[marker])
        self.assertEqual(self.outlet()["flagged"], len(rows))
        self.assertEqual(self.outlet()["score_percent"], 100)
        formula = rating_snapshot(self.store, END)["formula"]
        self.assertEqual(formula["marker_weight"], 1)
        self.assertTrue(formula["context_only_counted"])
        self.assertTrue(formula["informational_notices_counted"])

    def test_territory_example_is_counted_but_unmatched_publication_stays_zero(self):
        article, _ = save_publication(self.store, 1, text='Режим прекращения огня в оккупированных Олешках продлится до ночи 1 ноября.')
        save_publication(self.store, 2, text='В городе открылась библиотека.')
        result = self.store.article(article["id"])["analysis"]
        self.assertEqual(result["summary"]["candidate_fragments"], 0)
        self.assertEqual(result["summary"]["marker_fragments"], 1)
        self.assertEqual(result["findings"][0]["rating_weight"], 1)
        self.assertEqual(result["findings"][0]["status"], 'context_only')
        item = self.outlet()
        self.assertEqual((item["collected"], item["flagged"], item["score_percent"]), (2, 1, 50))
        self.assertEqual(item["by_type"], {'territory_terminology': 1})
        self.assertEqual(item["series"][-1]["score_percent"], 50)

    def test_new_rhetoric_rules_count_real_findings_without_changing_denominator(self):
        save_publication(self.store, 1, text='Летающий морг готовят на Украине.')
        save_publication(self.store, 2, text='Министр заявил: «Ад на пороге».')
        save_publication(self.store, 3, text='Открылась городская библиотека.')
        save_publication(self.store, 4, text='Житель в панике выбежал из квартиры.')
        item = self.outlet()
        self.assertEqual((item['collected'], item['flagged'], item['score_percent'], item['level']), (4, 2, 50, 'yellow'))
        self.assertEqual(item['by_type'], {'emotional_evaluation': 1, 'fear': 1})

    def test_book_numeric_checks_count_once_per_publication_and_match_chart(self):
        daily = 'В 2025 году в среднем 100 аварий в день — всего 10 тысяч аварий за год.'
        row, _ = save_publication(self.store, 1, text=daily)
        save_publication(self.store, 2, text='По данным опроса, большинство участников (37%) поддержали решение.')
        save_publication(self.store, 3, text='100 аварий в день — всего 36 500 аварий за год.')
        result = self.store.article(row['id'])['analysis']
        self.assertEqual(result['summary']['marker_fragments'], 2)
        self.assertEqual(result['summary']['marker_count'], 1)
        self.assertEqual(result['findings'][0]['rating_weight'], 1)
        item = self.outlet()
        self.assertEqual((item['collected'], item['flagged'], item['score_percent']), (3, 2, 66.666667))
        self.assertEqual(item['series'][-1]['cumulative_flagged'], 2)
        self.assertEqual(item['series'][-1]['score_percent'], item['score_percent'])
        self.assertEqual(item['by_type'], {'rhetorical_context': 2})

    def test_literature_candidates_and_notices_update_one_publication_vote_and_the_chart(self):
        save_publication(self.store, 1, text='Губернатор столько сделал для вас, что вы обязаны проголосовать за него.')
        save_publication(self.store, 2, text='97,3% жителей поддержали решение правительства.')
        save_publication(self.store, 3, text='Заявление собрало 200 000 репостов за сутки.')
        repeated = 'Новый закон вернёт нам спокойствие.\n' * 3
        save_publication(self.store, 4, text=repeated)
        item = self.outlet()
        self.assertEqual((item['collected'], item['analyzed'], item['flagged'], item['score_percent']), (4, 4, 3, 75))
        self.assertEqual(item['by_type'], {'emotional_evaluation': 1, 'rhetorical_context': 2})
        self.assertEqual(item['series'][-1]['cumulative_flagged'], 3)
        self.assertEqual(item['series'][-1]['score_percent'], 75)

    def test_time_window_uses_publication_date_and_handles_offsets_microseconds_and_future(self):
        inside = ["2026-10-24T12:00:00.000001+00:00", END, "2026-10-25T15:00:00+03:00"]
        outside = [START, "2026-10-25T12:00:00.000001+00:00", "2026-10-23T12:00:00+00:00", "", "not a date", "2026-10-25T11:00:00"]
        for number, value in enumerate(inside + outside, 1):
            save_publication(self.store, number, published=value, findings=[finding()])
        item = self.outlet()
        self.assertEqual((item["collected"], item["flagged"]), (len(inside), len(inside)))
        self.assertEqual(item["series"][-1]["score_percent"], 100)

    def test_pending_or_stale_analysis_cannot_become_a_green_zero(self):
        save_publication(self.store, 1, findings=[], version="rules-old")
        save_publication(self.store, 2, findings=[finding()])
        item = self.outlet()
        self.assertEqual((item["collected"], item["analyzed"], item["flagged"], item["pending_analysis"]), (2, 1, 1, 1))
        self.assertEqual(item["rating_state"], "analysis_pending")
        self.assertIsNone(item["score_percent"])
        self.assertIsNone(item["level"])
        self.assertIsNone(item["series"][-1]["score_percent"])

    def test_no_publications_means_no_score_and_all_configured_outlets_remain_visible(self):
        result = rating_snapshot(self.store, END)
        self.assertEqual({item["id"] for item in result["publishers"]}, {source.publisher for source in SOURCES.values()})
        self.assertEqual(result["totals"]["rated_publishers"], 0)
        self.assertTrue(all(item["level"] is None and item["score_percent"] is None for item in result["publishers"]))

    def test_website_and_channel_group_by_publisher_but_different_messages_count_separately(self):
        save_publication(self.store, 1, findings=[finding()])
        save_publication(self.store, 1, source_id="rt_telegram", text="Отдельное сообщение канала.", findings=[])
        save_publication(self.store, 1, source_id="oldlentach_telegram", findings=[finding()])
        self.assertEqual((self.outlet()["collected"], self.outlet()["flagged"]), (2, 1))
        self.assertEqual(self.outlet("oldlentach")["collected"], 1)
        self.assertEqual(self.outlet("lenta")["collected"], 0)

    def test_latest_revision_is_counted_once_and_missing_bodies_are_not_denominators(self):
        save_publication(self.store, 1, findings=[finding()])
        article, saved = save_publication(self.store, 1, findings=[], text="Обновлённый синтетический материал.")
        self.store.discover("rt", [FeedEntry("https://russiatoday.ru/news/99", "Без текста", END)], END)
        item = self.outlet()
        self.assertEqual((item["collected"], item["flagged"]), (1, 0))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0], 2)
        self.store.db.execute("DELETE FROM analyses WHERE revision_id=?", (saved["revision_id"],))
        self.store.db.commit()
        self.assertIsNone(self.outlet()["score_percent"])

    def test_chart_is_cumulative_and_ends_at_exact_card_totals(self):
        for number, hours, markers in ((1, 22, []), (2, 15, [finding()]), (3, 1, [finding()])):
            at = (datetime.fromisoformat(END) - timedelta(hours=hours)).isoformat()
            save_publication(self.store, number, published=at, findings=markers)
        item = self.outlet()
        series = item["series"]
        self.assertEqual(len(series), 24)
        self.assertIsNone(series[0]["score_percent"])
        self.assertEqual([series[i]["score_percent"] for i in (2, 9, 23)], [0, 50, item["score_percent"]])
        self.assertEqual((sum(p["collected"] for p in series), sum(p["flagged"] for p in series)), (3, 2))
        self.assertEqual((series[-1]["cumulative_collected"], series[-1]["cumulative_flagged"]), (3, 2))
        self.assertEqual((series[0]["start_at"], series[-1]["end_at"]), (START, END))

    def test_full_corpus_is_used_even_when_public_analysis_is_limited_to_one(self):
        for number in range(1, 41):
            save_publication(self.store, number, findings=[finding()] if number <= 10 else [])
        self.assertEqual(len(snapshot(self.store, 1)["articles"]), 1)
        item = self.outlet()
        self.assertEqual((item["collected"], item["flagged"], item["score_percent"]), (40, 10, 25))

    def test_source_errors_describe_partial_coverage_without_changing_observed_ratio(self):
        save_publication(self.store, 1, findings=[finding()])
        self.store.source_result(SOURCES["rt"], END, False, "HTTP 403")
        item = self.outlet()
        self.assertEqual(item["score_percent"], 100)
        self.assertFalse(item["coverage_complete"])
        self.assertTrue(item["collection_states"].get("partial"))

    def test_sidecar_is_public_aggregate_only_and_survives_rebuild(self):
        save_publication(self.store, 1, findings=[])
        runtime = runtime_fixture(self.path / "runtime")
        output = self.path / "site"
        build_site(self.store, output, limit=1, runtime_dir=runtime)
        build_site(self.store, output, limit=1, runtime_dir=runtime)
        result = json.loads((output / "data/rating.json").read_text())
        self.assertEqual(result["schema_version"], "rating-snapshot-1.0")
        self.assertNotIn("Синтетический материал", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("findings", json.dumps(result))
        self.assertEqual(len(list(output.glob("data/rating.json"))), 1)

    def test_as_of_requires_a_timezone(self):
        for value in ("2026-10-25T12:00:00", "not a date"):
            with self.assertRaises(ValueError):
                rating_snapshot(self.store, value)

