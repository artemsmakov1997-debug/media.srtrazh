"""Quantity review cues and counterexamples, not independent accuracy labels."""

import unittest

from media_strazh.analysis import analyze


RADIOSVOBODA_EXCERPT = (
    "С начала полномасштабной войны против Украины в России стали происходить поджоги "
    "военкоматов, административных зданий, релейных шкафов и других объектов. "
    "Зачастую по подозрению в совершении таких преступлений задерживают несовершеннолетних. "
    "Как правило, против обвиняемых возбуждают дела о диверсиях и терроризме, иногда и о "
    "государственной измене. Многие задержанные утверждают, что принимали заказы неизвестных "
    "в интернете ради заработка, случаев поджогов по антивоенным соображениям существенно меньше."
)
QUANTITY_RULES = {
    "generalization.indefinite_prevalence",
    "generalization.vague_event_frequency",
    "exaggeration.unquantified_comparison",
}


class QuantitativeCueTests(unittest.TestCase):
    def quantitative(self, text):
        return [f for f in analyze({"text": text})["findings"] if f["rule_id"] in QUANTITY_RULES]

    def test_user_excerpt_exposes_all_four_quantity_cues(self):
        # https://t.me/radiosvoboda/105417, published 2026-10-13.
        for field in ("title", "text"):
            with self.subTest(field=field):
                value = "📰 " + RADIOSVOBODA_EXCERPT
                result = analyze({"text": "Опубликован материал.", field: value})
                findings = [f for f in result["findings"] if f["rule_id"] in QUANTITY_RULES]
                self.assertEqual([f["evidence"][0]["quote"] for f in findings],
                                 ["Зачастую", "Как правило", "Многие задержанные", "существенно меньше"])
                for f in findings:
                    e = f["evidence"][0]
                    self.assertEqual(e["field"], field)
                    self.assertEqual(value[e["start"]:e["end"]], e["quote"])
                    self.assertTrue(f["explanation"])
                    self.assertTrue(f["review_question"])
                self.assertFalse(any(f["category"] == "euphemism_dysphemism" for f in findings))

    def test_indefinite_group_forms_without_assuming_a_majority(self):
        for text in ("Многие из задержанных утверждают, что получали деньги.",
                     "Большинство опрошенных граждан поддерживают решение.",
                     "Немногие участники заявляют о нарушениях.",
                     "Многие россияне считают решение полезным."):
            with self.subTest(text=text):
                found = self.quantitative(text)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["rule_id"], "generalization.indefinite_prevalence")
                self.assertIn("не обязательно означает большинство", found[0]["explanation"])

    def test_frequency_is_restricted_to_asserted_public_events(self):
        for text in ("Зачастую граждан задерживают после поджогов.",
                     "Как правило, суды осуждают обвиняемых.",
                     "Часто компании увольняют сотрудников.",
                     "В большинстве случаев избиратели голосуют за кандидата."):
            with self.subTest(text=text):
                self.assertEqual([f["rule_id"] for f in self.quantitative(text)],
                                 ["generalization.vague_event_frequency"])

    def test_comparisons_require_a_count_subject_in_the_same_clause(self):
        for text in ("Число поджогов существенно выше.",
                     "Количество задержаний значительно меньше.",
                     "Доля нарушений заметно ниже.",
                     "Случаев гораздо больше, чем годом ранее."):
            with self.subTest(text=text):
                self.assertEqual([f["rule_id"] for f in self.quantitative(text)],
                                 ["exaggeration.unquantified_comparison"])

    def test_direct_quantities_do_not_get_the_unquantified_cue(self):
        texts = (
            "Многие задержанные (18 из 25 опрошенных) утверждают, что получали деньги.",
            "Большинство граждан (60%) поддерживают решение.",
            "Большинство участников опроса поддерживают закон: 57% из 1200 респондентов.",
            "Многие граждане поддерживают решение (60% опрошенных).",
            "Зачастую (в 7 из 10 случаев) граждан задерживают после поджогов.",
            "Число случаев существенно меньше — на 15%.",
            "Число случаев значительно больше: в 2 раза.",
            "Количество случаев существенно меньше (12 против 36).",
            "По данным отчёта, 18 из 25 задержанных сообщили о заказах в интернете.",
            "Согласно исследованию, доля нарушений снизилась с 30% до 12%.",
        )
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(self.quantitative(text), [])

    def test_unrelated_numbers_and_named_sources_do_not_establish_a_basis(self):
        for text in ("В 2026 году многие граждане поддерживают решение.",
                     "Число случаев существенно меньше, чем в 2020 году.",
                     "В зале 30 стульев. Число поджогов существенно выше.",
                     "Многие граждане поддерживают решение, а 57% компаний против.",
                     "По данным ведомства, многие граждане поддерживают решение."):
            with self.subTest(text=text):
                self.assertEqual(len(self.quantitative(text)), 1)

    def test_literals_instructions_and_scale_are_not_automatic_manipulation(self):
        texts = (
            "С начала полномасштабной войны против Украины произошли поджоги.",
            "Полномасштабное исследование охватило все регионы страны.",
            "Армия начала полномасштабные учения.",
            "Как правило, перед запуском программы нажмите кнопку.",
            "Зачастую слово встречается в учебниках русского языка.",
            "Многие книги представлены в библиотеке.",
            "Многие люди любят яблоки.",
            "Гора значительно выше соседнего холма.",
            "Обсудили число поджогов, а башня существенно выше здания.",
            "Температура существенно ниже обычной.",
        )
        for text in texts:
            with self.subTest(text=text):
                findings = analyze({"text": text})["findings"]
                self.assertTrue(all(f["category"] == "event_terminology" and f["status"] == "context_only"
                                    for f in findings))

    def test_quoted_denied_and_discussed_cues_keep_context(self):
        for text, expected in (
            ("Автор заявил: «Многие задержанные утверждают, что получали деньги».", "quoted_candidate"),
            ("Автор заявил: «Как правило, против обвиняемых возбуждают дела».", "quoted_candidate"),
            ("Автор заявил: «Число случаев существенно меньше».", "quoted_candidate"),
            ("Нельзя утверждать, что многие задержанные сообщают о заказах.", "context_only"),
            ("Число случаев не существенно меньше.", "context_only"),
            ("Слово «зачастую» обобщает частоту: граждан задерживают.", "context_only"),
        ):
            with self.subTest(text=text):
                found = self.quantitative(text)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["status"], expected)

    def test_source_identity_does_not_change_quantity_findings(self):
        expected = analyze({"text": RADIOSVOBODA_EXCERPT})["findings"]
        for source in ("Радио Свобода", "RT", "ТАСС", "ИноСМИ", "Неизвестное издание"):
            self.assertEqual(analyze({"text": RADIOSVOBODA_EXCERPT, "source": source})["findings"], expected)


if __name__ == "__main__":
    unittest.main()
