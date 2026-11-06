"""Lexicon corpus report on a synthetic database: impact, sample and candidates."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.mining import corpus_report, stem, summary_markdown, write_report
from media_strazh.storage import Store
from test_rating import save_publication


class LexiconReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.store = Store(self.path / "corpus.sqlite3")

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def test_report_separates_lexicon_impact_and_suggests_unknown_words(self):
        texts = [
            "Киевская хунта и узурпаторы снова лгут, заявил депутат Госдумы.",
            "Узурпаторы из киевской хунты сорвали переговоры, считают в Москве.",
            "Хунта и её узурпаторы ввели новые санкции против граждан.",
            "Рашистята опять обстреляли Харьков, сообщили в Киеве.",
            "Рашистята снова атаковали Сумы.",
            "В городе открылась новая библиотека.",
            "Погода в выходные будет тёплой.",
        ]
        for number, text in enumerate(texts, 1):
            save_publication(self.store, number, text=text)
        report = corpus_report(self.store, top=50, samples=10)
        self.assertEqual(report["documents"], 7)
        [outlet] = [item for item in report["publishers"] if item["publisher"] == "rt"]
        self.assertEqual(outlet["documents"], 7)
        self.assertGreater(outlet["share_after"], outlet["share_before"])
        self.assertGreaterEqual(outlet["lexicon_only"], 3)
        self.assertIn("lex.enemy.junta", report["groups"])
        self.assertTrue(all(hit["group"].startswith("lex.") for hit in report["review_sample"]))
        productive = {item["word"].casefold() for item in report["candidates"]["productive"]}
        self.assertIn("рашистята", productive)
        near = {item["stem"] for item in report["candidates"]["near_triggers"]}
        self.assertIn(stem("узурпаторы"), near)

        markdown = summary_markdown(report)
        self.assertIn("| rt | 7 |", markdown)
        self.assertIn("lex.enemy.junta", markdown)
        summary = write_report(report, self.path / "report")
        self.assertEqual(summary["documents"], 7)
        saved = json.loads((self.path / "report" / "lexicon-report.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], "lexicon-report-1.0")
        with (self.path / "report" / "publishers.csv").open(encoding="utf-8-sig") as handle:
            self.assertEqual(next(csv.DictReader(handle))["publisher"], "rt")

    def test_stemmer_groups_case_forms(self):
        self.assertEqual(stem("узурпаторы"), stem("узурпаторами"))
        self.assertEqual(stem("Узурпатором"), stem("узурпаторов"))


if __name__ == "__main__":
    unittest.main()
