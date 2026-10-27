"""Claim-link regressions are synthetic examples, not a detector quality score."""

import unittest

from media_strazh.analysis import analyze


class HeadlineClaimLinkTests(unittest.TestCase):
    title = "Учёные доказали влияние продукта на давление"
    body = "Авторы обнаружили возможную связь продукта с давлением на небольшой выборке."

    def gaps(self, title=None, text=None, **metadata):
        result = analyze({"title": self.title if title is None else title,
                          "text": self.body if text is None else text, **metadata})
        return [f for f in result["findings"] if f["rule_id"] == "headline.certainty_gap"]

    def test_shared_subject_vocabulary_and_inflections(self):
        findings = self.gaps()
        self.assertEqual(len(findings), 1)
        link = findings[0]["claim_link"]
        self.assertEqual(link["method"], "local_lexical_overlap")
        self.assertFalse(link["semantic_equivalence_verified"])
        self.assertTrue({"продукт", "давлен"} <= set(link["shared_anchors"]))

    def test_unrelated_caveat_is_not_a_gap(self):
        self.assertEqual(self.gaps(text="Предварительные данные о температуре океана опубликованы."), [])

    def test_generic_research_words_do_not_link_claims(self):
        self.assertEqual(self.gaps(title="Учёные доказали результат исследования",
                                   text="Авторы исследования представили предварительные данные."), [])

    def test_a_single_shared_subject_does_not_link_different_claims(self):
        self.assertEqual(self.gaps(text="Возможная связь продукта с аллергией требует проверки."), [])

    def test_scan_past_unrelated_and_quoted_caveats(self):
        prefix = 'Предварительные данные о температуре океана опубликованы.\nФраза «возможная связь» обсуждалась.\n'
        finding = self.gaps(text=prefix + self.body)[0]
        self.assertGreaterEqual(finding["evidence"][1]["start"], len(prefix))

    def test_quoted_or_denied_caveat_is_not_asserted(self):
        for text in (
            'Авторы написали: «Возможная связь продукта с давлением требует проверки».',
            'Авторы не подтвердили возможную связь продукта с давлением.',
            'Фраза «возможная связь продукта с давлением» удалена.',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.gaps(text=text), [])

    def test_quoted_and_negated_headline_keep_their_status(self):
        self.assertEqual(self.gaps(title="«Учёные доказали влияние продукта на давление»")[0]["status"],
                         "quoted_candidate")
        self.assertEqual(self.gaps(title="Учёные не доказали влияние продукта на давление")[0]["status"],
                         "context_only")

    def test_uncertain_headline_is_not_categorical(self):
        self.assertEqual(self.gaps(title="Возможно, учёные доказали влияние продукта на давление"), [])

    def test_explicitly_different_years_are_not_linked(self):
        self.assertEqual(len(self.gaps(text=self.body + " В 2025 году опубликован другой отчёт.")), 1)
        self.assertEqual(self.gaps(title=self.title + " в 2024 году",
                                   text="В 2025 году обнаружили возможную связь продукта с давлением."), [])

    def test_different_latin_object_identifiers_are_not_linked(self):
        self.assertEqual(self.gaps(title="Доказали влияние продукта X на давление",
                                   text="Обнаружили возможную связь продукта Y с давлением."), [])
        self.assertEqual(len(self.gaps(title="Доказали влияние продукта X на давление",
                                      text="Обнаружили возможную связь продукта X с давлением.")), 1)

    def test_clause_does_not_borrow_topic_from_neighbour(self):
        self.assertEqual(self.gaps(text="Описано влияние продукта на давление; предварительные данные о климате отсутствуют."), [])
        self.assertEqual(self.gaps(text="Описано влияние продукта на давление, однако предварительные данные о климате отсутствуют."), [])

    def test_original_unicode_coordinates_and_link_spans(self):
        title = "📰 " + self.title
        text = "😀 Другая новость.\r\n" + self.body
        finding = self.gaps(title=title, text=text)[0]
        for evidence in finding["evidence"]:
            original = title if evidence["field"] == "title" else text
            self.assertEqual(original[evidence["start"]:evidence["end"]], evidence["quote"])
        link = finding["claim_link"]
        span = link["text_span"]
        self.assertIn("продукта", text[span["start"]:span["end"]])

    def test_source_does_not_supply_link_and_output_is_repeatable(self):
        first = self.gaps(source="RT")
        self.assertEqual(first, self.gaps(source="BBC"))
        self.assertEqual(first, self.gaps(source="RT"))


if __name__ == "__main__":
    unittest.main()
