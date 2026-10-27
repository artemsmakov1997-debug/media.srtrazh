"""Informational terminology notices; no inference of manipulation or truth."""

import unittest

from media_strazh.analysis import MAX_FINDINGS, SUPPORTED, TAXONOMY, analyze
from media_strazh.evaluation import evaluate


CASES = {
    "terminology.full_scale_war": "Полномасштабная война России против Украины продолжается.",
    "terminology.full_scale_invasion": "С начала полномасштабного вторжения России в Украину прошло время.",
    "terminology.special_operation": "Россия объявила специальную военную операцию на Украине.",
    "terminology.svo": "Российские ветераны СВО получили помощь.",
}


class EventTerminologyTests(unittest.TestCase):
    def notices(self, document):
        return [f for f in analyze(document)["findings"] if f["category"] == "event_terminology"]

    def test_both_fields_and_inflections_preserve_unicode_offsets(self):
        for rule_id, text in CASES.items():
            for field in ("title", "text"):
                with self.subTest(rule_id=rule_id, field=field):
                    value = "📰 " + text
                    document = {"text": "Опубликован материал.", field: value}
                    found = self.notices(document)
                    self.assertEqual(len(found), 1)
                    self.assertEqual(found[0]["rule_id"], rule_id)
                    self.assertEqual(found[0]["status"], "context_only")
                    e = found[0]["evidence"][0]
                    self.assertEqual((e["field"], value[e["start"]:e["end"]]), (field, e["quote"]))
                    self.assertTrue(e["context"]["informational_notice"])

    def test_all_four_terms_are_information_not_rhetorical_counts(self):
        result = analyze({"text": "\n".join(CASES.values())})
        self.assertEqual(len(result["findings"]), 4)
        self.assertEqual(result["summary"]["context_only"], 4)
        for key in ("review_candidates", "review_fragments", "candidate_fragments", "quoted_candidates"):
            self.assertEqual(result["summary"][key], 0)
        self.assertEqual(result["summary"]["by_category"], {})

    def test_cross_field_context_is_bounded_and_does_not_change_evidence(self):
        for document in (
            {"title": "Полномасштабная война", "text": "Россия и Украина продолжают военные действия."},
            {"title": "СВО", "text": "Российские военнослужащие получили помощь."},
            {"title": "Война России против Украины", "text": "Обсудили полномасштабное вторжение."},
        ):
            with self.subTest(document=document):
                self.assertEqual(len(self.notices(document)), 1)
        far_context = "Открыта библиотека.\n" * 50 + "Россия и Украина обсуждают войну."
        self.assertEqual(self.notices({"title": "Полномасштабная война", "text": far_context}), [])

    def test_attribution_and_denial_flags_survive_informational_status(self):
        for text, flag in (
            ("Президент России заявил: «Специальная военная операция продолжается».", "in_quotes"),
            ("Президент России заявил, что специальная военная операция продолжается.", "reported_speech"),
            ("Россия обсуждает войну. Фраза «полномасштабная война» упомянута в документе.", "metalinguistic"),
            ("На Украине не полномасштабная война, утверждает автор.", "nearby_negation"),
        ):
            with self.subTest(text=text):
                found = self.notices({"text": text})
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["status"], "context_only")
                self.assertTrue(found[0]["evidence"][0]["context"][flag])

    def test_other_wars_literals_and_acronyms_do_not_use_this_frame(self):
        texts = (
            "Полномасштабная война в Ираке обсуждается на встрече России и Украины.",
            "Россия обсуждала полномасштабное вторжение в Афганистан в 1979 году.",
            "В 1941 году началась полномасштабная война на территории Украины.",
            "Россия провела специальную военную операцию в Сирии.",
            "Полномасштабное вторжение произошло в романе об Украине.",
            "Специальная операция полиции России завершена.",
            "Российский компьютер использует систему водяного охлаждения (СВО).",
            "В России совет ветеранов организации (СВО) организовал встречу.",
            "Полномасштабное исследование охватило Украину.",
            "Российские ветераны получили свою выплату.",
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(self.notices({"text": text}), [])
        self.assertEqual(self.notices({"title": "СВО", "text": "Российская система водяного охлаждения обновлена."}), [])

    def test_coverage_adds_a_layer_without_changing_methodology_or_evaluation(self):
        result = analyze({"text": CASES["terminology.full_scale_war"]})
        self.assertEqual(len(TAXONOMY), 12)
        self.assertEqual(len(SUPPORTED), 10)
        self.assertNotIn("event_terminology", SUPPORTED)
        self.assertEqual(next(c for c in result["coverage"] if c["id"] == "event_terminology")["coverage"],
                         "context_notices")
        row = {"id": "notice", "fully_annotated": True, "annotation_categories": sorted(SUPPORTED),
               "document": {"text": result["document"]["text"]}, "labels": []}
        score = evaluate([row])
        self.assertTrue(all(category["fp"] == 0 for category in score["categories"].values()))

    def test_real_rhetoric_is_not_suppressed_by_terminology(self):
        result = analyze({"text": CASES["terminology.full_scale_war"] + " Все знают о решении."})
        self.assertTrue(any(f["category"] == "generalization" and f["status"] == "needs_review"
                            for f in result["findings"]))
        self.assertEqual(result["summary"]["candidate_fragments"], 1)
        self.assertEqual(len([f for f in result["findings"] if f["category"] == "event_terminology"]), 1)

    def test_information_does_not_exhaust_budget_before_body_rhetoric(self):
        result = analyze({"title": "Доказали влияние продукта на давление. " + (CASES["terminology.full_scale_war"] + "\n") * (MAX_FINDINGS + 2),
                          "text": "Все знают о решении. Возможная связь продукта с давлением требует проверки."})
        ids = {f["rule_id"] for f in result["findings"]}
        self.assertIn("generalization.universal_claim", ids)
        self.assertIn("headline.certainty_gap", ids)
        self.assertEqual(len(result["findings"]), MAX_FINDINGS)
        self.assertTrue(result["summary"]["findings_truncated"])

    def test_publisher_names_do_not_supply_context_or_determine_findings(self):
        for source in ("RT", "Радио Свобода", "Медиазона", "ТАСС"):
            self.assertEqual(self.notices({"text": "Полномасштабная война продолжается.", "source": source}), [])
        expected = analyze({"text": CASES["terminology.special_operation"]})["findings"]
        for source in ("RT", "Радио Свобода", "Медиазона", "ТАСС"):
            self.assertEqual(analyze({"text": CASES["terminology.special_operation"], "source": source})["findings"], expected)


if __name__ == "__main__":
    unittest.main()
