"""Territorial descriptions are contextual notices, not manipulation verdicts."""

import unittest

from media_strazh.analysis import MAX_FINDINGS, SUPPORTED, TAXONOMY, analyze
from media_strazh.evaluation import evaluate


HEADLINE = "В аннексированном Крыму произошло масштабное отключение электроэнергии"
CASES = {
    "terminology.annexed_territory": HEADLINE,
    "terminology.occupied_territory": "В оккупированном городе отключили электричество.",
    "terminology.liberated_territory": "В освобождённом городе восстановили электроснабжение.",
}


class TerritoryTerminologyTests(unittest.TestCase):
    def notices(self, document):
        return [f for f in analyze(document)["findings"] if f["category"] == "territory_terminology"]

    def test_user_headline_both_fields_and_unicode_offsets(self):
        for rule_id, text in CASES.items():
            for field in ("title", "text"):
                with self.subTest(rule=rule_id, field=field):
                    value = "⚡️ " + text
                    findings = self.notices({"text": "Подробности события.", field: value})
                    self.assertEqual(len(findings), 1)
                    finding = findings[0]
                    self.assertEqual(finding["rule_id"], rule_id)
                    self.assertEqual(finding["label"], "Обозначение территории")
                    self.assertEqual(finding["status"], "context_only")
                    evidence = finding["evidence"][0]
                    self.assertEqual(evidence["field"], field)
                    self.assertEqual(value[evidence["start"]:evidence["end"]], evidence["quote"])
                    self.assertTrue(evidence["context"]["informational_notice"])

    def test_full_short_and_inflected_forms(self):
        cases = (
            ("аннексированную территорию", "annexed"),
            ("аннексированные земли", "annexed"),
            ("Территория аннексирована", "annexed"),
            ("Крым был аннексирован", "annexed"),
            ("Острова аннексированы", "annexed"),
            ("оккупированных населённых пунктов", "occupied"),
            ("оккупированного Херсона", "occupied"),
            ("Город Бахмут был оккупирован", "occupied"),
            ("Территории были временно оккупированы", "occupied"),
            ("освобождённая область", "liberated"),
            ("освобожденными районами", "liberated"),
            ("освобождённый российскими войсками город", "liberated"),
            ("Освобождённые украинскими силами территории", "liberated"),
            ("Район был освобожден", "liberated"),
            ("Территория Херсонской области была освобождена", "liberated"),
            ("Области освобождены", "liberated"),
            ("В городе, который был освобождён, открыли больницу", "liberated"),
            ("В освобождённых сёлах открыли школы", "liberated"),
        )
        for text, kind in cases:
            with self.subTest(text=text):
                self.assertEqual([f["rule_id"] for f in self.notices({"text": text})],
                                 [f"terminology.{kind}_territory"])

    def test_no_country_or_publisher_restriction(self):
        for text in (
            "В оккупированной Газе отключили электричество.",
            "Обсудили аннексированные Голанские высоты.",
            "В освобождённом населённом пункте Неведомый открыли школу.",
            "В 1945 году освобождённый город восстановили.",
        ):
            expected = self.notices({"text": text})
            self.assertEqual(len(expected), 1)
            for source in ("RT", "Радио Свобода", "ТАСС", "Медиазона"):
                with self.subTest(text=text, source=source):
                    self.assertEqual(self.notices({"text": text, "source": source}), expected)
        for source in ("Крым", "RT", "Украина"):
            self.assertEqual(self.notices({"text": "Освобождённый", "source": source}), [])

    def test_literal_release_and_nearby_place_do_not_supply_a_target(self):
        texts = (
            "В Крыму освобождённый заключённый встретился с семьёй.",
            "В Крыму освобождён заключённый.",
            "Освобождённый заключённый Крыма вернулся домой.",
            "В Крыму освобождённый из плена вернулся домой.",
            "Освобождённый сел в поезд до Крыма.",
            "В Крыму освобождённый сотрудник дал интервью.",
            "В Крыму освобождённое парковочное место заняла машина.",
            "Город освобождён от уплаты налогов.",
            "Район освобождён от снега.",
            "Освобождённый от долгов город получил субсидию.",
            "В Крыму оккупированный офис освободили.",
            "Освобождённый из плена военнослужащий вернулся в освобождённую от снега деревню.",
            "Обсудили аннексированный документ.",
            "Освобождённый посетил город.",
            "Крым. Освобождённый сотрудник дал интервью.",
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(self.notices({"text": text}), [])

    def test_no_cross_field_or_distant_context(self):
        for document in (
            {"title": "Крым", "text": "Освобождённый"},
            {"title": "Освобождённый", "text": "Крым"},
            {"text": "Освобождённый. Территория восстановлена."},
            {"text": "Крым.\n" + "Опубликован материал. " * 30 + "Освобождённый."},
            {"text": "Освобождённый " + "небольшой " * 30 + "город"},
        ):
            with self.subTest(document=document):
                self.assertEqual(self.notices(document), [])

    def test_quotes_reported_speech_negation_and_discussion_stay_contextual(self):
        for text, flag in (
            ('Автор заявил: «Город освобождён».', "in_quotes"),
            ("Автор заявил, что территория оккупирована.", "reported_speech"),
            ("Город не оккупирован, утверждает автор.", "nearby_negation"),
            ('В документе использована формулировка «освобождённый город».', "metalinguistic"),
        ):
            with self.subTest(text=text):
                findings = self.notices({"text": text})
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0]["status"], "context_only")
                self.assertTrue(findings[0]["evidence"][0]["context"][flag])

    def test_not_rhetorical_counts_or_evaluation_labels(self):
        document = {"text": "\n".join(CASES.values())}
        result = analyze(document)
        self.assertEqual(len(result["findings"]), 3)
        self.assertEqual(result["summary"]["context_only"], 3)
        for key in ("review_candidates", "review_fragments", "candidate_fragments", "quoted_candidates"):
            self.assertEqual(result["summary"][key], 0)
        self.assertEqual(result["summary"]["by_category"], {})
        self.assertEqual(len(TAXONOMY), 12)
        self.assertEqual(len(SUPPORTED), 10)
        self.assertNotIn("territory_terminology", SUPPORTED)
        self.assertEqual(next(c for c in result["coverage"] if c["id"] == "territory_terminology")["coverage"],
                         "context_notices")
        row = {"id": "territory", "fully_annotated": True, "annotation_categories": sorted(SUPPORTED),
               "document": document, "labels": []}
        self.assertTrue(all(c["fp"] == 0 for c in evaluate([row])["categories"].values()))

    def test_terminology_preserves_real_rhetoric_and_does_not_exhaust_budget(self):
        result = analyze({"text": HEADLINE + ". Все знают о решении."})
        self.assertEqual(result["summary"]["candidate_fragments"], 1)
        self.assertTrue(any(f["rule_id"] == "generalization.universal_claim" for f in result["findings"]))
        dense = analyze({"title": (HEADLINE + "\n") * (MAX_FINDINGS + 2), "text": "Все знают о решении."})
        self.assertEqual(len(dense["findings"]), MAX_FINDINGS)
        self.assertTrue(dense["summary"]["findings_truncated"])
        self.assertTrue(any(f["rule_id"] == "generalization.universal_claim" for f in dense["findings"]))


if __name__ == "__main__":
    unittest.main()
