import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_strazh.analysis import analyze
from media_strazh.business import COMPILED_TOPICS, business_snapshot, name_candidates, normalize_name, watchlist_matches
from media_strazh.extraction import FeedEntry
from media_strazh.sources import SOURCES
from media_strazh.storage import Store
from test_collector import page

NOW = "2026-10-15T09:00:00+00:00"


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / "business.sqlite3")

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def save(self, number, text, published_at=NOW, title="Новость медицины"):
        source = SOURCES["ria"]
        url = f"https://ria.ru/news/{number}"
        self.store.discover(source.id, [FeedEntry(url, title, published_at)], NOW)
        article = dict(self.store.db.execute("SELECT * FROM articles WHERE source_id=? AND url=?",
                                            (source.id, url)).fetchone())
        document = {"title": title, "text": text, "source": source.name, "url": url, "published_at": published_at}
        self.store.save(article, {"document": document, "extractor_version": "fixture", "extraction_method": "fixture"},
                        page(source, url, text), analyze(document), NOW, 3600)

    def test_mc21_aliases_need_a_named_medical_entity_or_real_domain(self):
        for value in ('Медицинский центр «XXI век» открыл отделение.', 'Клиника XXI век опубликовала расписание.',
                      'Пациенты центра «21 век» посетили врача.', 'Сайт https://mc21.ru/ сообщил расписание.'):
            with self.subTest(value=value):
                self.assertEqual(watchlist_matches(value)[0], ["mc21"])
        for value in ('Медицина в XXI веке развивается.', 'В XXI веке клиники работают иначе.',
                      'Медицинский центр XXI века — проект будущего.',
                      'Врач представил книгу «XXI век».',
                      'Компания «XXI век» открыла магазин.', 'Посетите https://mc21.ru.evil.example/',
                      'Посетите https://not-mc21.ru/'):
            with self.subTest(value=value):
                self.assertEqual(watchlist_matches(value), ([], None))

    def test_proper_name_candidates_include_body_mentions_and_normalized_legal_names(self):
        names, truncated = name_candidates("Открыто отделение", 'Посетили ООО «Сбербанк». Отделение Медицинский Центр и iPhone работают.')
        self.assertIn("сбербанк", names)
        self.assertIn("iphone", names)
        self.assertFalse(truncated)
        self.assertEqual(normalize_name(' ООО «XXI\u00a0век» '), "xxi век")

    def test_snapshot_includes_neutral_body_mentions_with_real_dates_and_no_full_body(self):
        body = 'Медицинский центр «XXI век», частная клиника, опубликовал расписание. ' + 'длинное описание услуг. ' * 60
        self.save(1, body)
        result = business_snapshot(self.store, NOW)
        self.assertEqual(result["coverage"]["published"], 1)
        record = result["articles"][0]
        self.assertEqual(record["watchlists"], ["mc21"])
        self.assertEqual(record["published_at"], NOW)
        self.assertEqual(record["url"], "https://ria.ru/news/1")
        self.assertIn("medtech:health", record["topics"])
        self.assertNotIn("text", record)
        self.assertNotIn(body, json.dumps(result, ensure_ascii=False))
        self.assertLessEqual(len(record["excerpt"]), 340)
        self.assertNotIn("tone", record)

    def test_dates_exclude_undated_future_and_old_records_without_using_retrieval(self):
        for number, stamp in enumerate((NOW, "", "2026-10-16T09:00:00+00:00", "2020-01-01T00:00:00+00:00"), 1):
            self.save(number, 'Клиника «XXI век» опубликовала новость.', stamp)
        result = business_snapshot(self.store, NOW)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["coverage"]["corpus_total"], 4)
        self.assertEqual(result["coverage"]["undated_excluded"], 1)

    def test_current_revision_is_used_once_and_disappearing_brand_is_not_retained(self):
        self.save(1, 'Клиника «XXI век» опубликовала новость.')
        self.save(1, 'Открыта городская библиотека. Жители посетили читальный зал.')
        result = business_snapshot(self.store, NOW)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["watchlists"], [])

    def test_bounded_sample_is_explicit_and_zero_records_are_not_fabricated(self):
        self.assertEqual(business_snapshot(self.store, NOW)["articles"], [])
        for number in range(1, 4):
            self.save(number, 'Клиника «XXI век» опубликовала новость.')
        with patch("media_strazh.business.MAX_RECORDS", 2):
            result = business_snapshot(self.store, NOW)
        self.assertTrue(result["coverage"]["limited"])
        self.assertEqual(result["coverage"]["published"], 2)
        with patch("media_strazh.business.MAX_BYTES", 1):
            result = business_snapshot(self.store, NOW)
        self.assertEqual(result["articles"], [])
        self.assertTrue(result["coverage"]["limited"])

    def test_hotel_topic_does_not_match_boilers_or_armored_vehicles(self):
        hotels = dict(COMPILED_TOPICS)["hospitality:hotels"]
        self.assertFalse(hotels.search("На заводе изготовили котел и бронированную технику."))
        self.assertTrue(hotels.search("Открыли новый отель и гостиницу."))

    def test_canonical_duplicates_do_not_double_the_publication_count(self):
        self.save(1, 'Клиника «XXI век» опубликовала новость.')
        self.save(2, 'Клиника «XXI век» опубликовала новость.')
        self.store.db.execute("UPDATE revisions SET canonical_url='https://ria.ru/news/1'")
        result = business_snapshot(self.store, NOW)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["coverage"]["duplicates_excluded"], 1)
        self.assertFalse(result["coverage"]["limited"])

    def test_tracked_clinic_is_not_displaced_by_newer_unrelated_news(self):
        self.save(1, 'Клиника «XXI век» опубликовала новость.', '2026-10-10T09:00:00+00:00')
        self.save(2, 'В городе открыта библиотека.')
        with patch("media_strazh.business.MAX_RECORDS", 1):
            result = business_snapshot(self.store, NOW)
        self.assertEqual(result["articles"][0]["watchlists"], ["mc21"])
        self.assertEqual(result["articles"][0]["url"], "https://ria.ru/news/1")
        self.assertTrue(result["coverage"]["limited"])


if __name__ == "__main__":
    unittest.main()
