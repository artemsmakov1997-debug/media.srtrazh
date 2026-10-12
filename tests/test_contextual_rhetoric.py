"""User examples plus counterexamples, never independent corpus accuracy."""

import unittest

from media_strazh.analysis import MAX_CHARS, SUPPORTED, analyze
from media_strazh.rules import RULES


# Supplied by the user: https://t.me/izvestia/253503. The full interview has
# not been located. A printed omission does not establish quote distortion.
BLAHA_TEXT = '''Украина — самая большая угроза безопасности в будущем, заявил депутат Европарламента от Словакии Любош Блаха.

"Когда-нибудь этот конфликт закончится, и тогда всё станет очевидно — как это было на Балканах в 1990-е годы. Там огромное количество головорезов, людей, которые уже готовы убивать. Они вернутся, разочарованные, и это может привести к распространению мафиозных структур и так далее. Это может стать большой проблемой для безопасности", — заявил он.

По словам евродепутата, Европа превратилась в неолиберальную военную машину, а её цели рушатся. Во Франции и Испании "всё разваливается", а сами они "находятся на грани революции".

"Поэтому мы и говорим, что не хотим войны против России. Мы должны договориться с русскими, прекратить вооружаться и нормально развивать экономику. Именно поэтому мы говорим, что хотим мира", — заявил он.

Блаха поставил под сомнение демократию в ЕС и право критиковать россиян. По его словам, очевидно, что у Владимира Путина в РФ есть поддержка, тогда как рейтинги канцлера ФРГ Фридриха Мерца и президента Франции Эммануэля Макрона рухнули.

"И при этом они идут рассуждать о легитимности. На Украине Зеленский уже третий год правит как диктатор, не имея никакого мандата. А мы делаем вид, будто проблема в русских, которые хотели бы, чтобы выборы там прошли. <...> Посмотрите, если бы на Украине состоялись выборы, Зеленский бы их проиграл", — подытожил евродепутат.'''

POSITIVE_CASES = {
    "fear.security_superlative": "Украина — самая большая угроза безопасности в будущем.",
    "fear.predicted_criminal_spread": "Политический кризис может привести к распространению мафиозных структур.",
    "fear.impending_unrest": "Страна находится на грани гражданской войны.",
    "exaggeration.total_collapse": "В Европе всё разваливается.",
    "enemy.militarized_collective": "Европа превратилась в неолиберальную военную машину.",
    "dysphemism.criminal_label": "Политические оппоненты — головорезы.",
    "dysphemism.autocratic_label": "Нынешний президент правит как диктатор.",
    "enemy.nazi_analogy": "Нынешний министр действует как Гитлер.",
    "enemy.nazi_political_label": "Политик — новый Гитлер.",
    "simplification.historical_parallel": "В будущем политический конфликт закончится, как это было на Балканах в 1990-е годы.",
    "generalization.asserted_obviousness": "По словам депутата, очевидно, что правительство ошибается.",
    "simplification.counterfactual_certainty": "Если бы на Украине состоялись выборы, Зеленский бы их проиграл.",
    "simplification.popularity_legitimacy": "Рейтинг президента низкий, значит он нелегитимен.",
    "simplification.peace_war_binary": "Кто не поддерживает этот план, тот хочет войны.",
    "context.quotation_omission": "Депутат сказал: «Мы обсудили <...> расходы».",
}


class ContextualRhetoricTests(unittest.TestCase):
    def findings(self, text, rule_id):
        return [f for f in analyze({"text": text})["findings"] if f["rule_id"] == rule_id]

    def test_every_added_rule_has_positive_exact_unicode_spans_in_both_fields(self):
        ids = {rule.id for rule in RULES}
        for rule_id, text in POSITIVE_CASES.items():
            self.assertIn(rule_id, ids)
            for field in ("title", "text"):
                with self.subTest(rule_id=rule_id, field=field):
                    text_with_emoji = "📰 " + text
                    result = analyze({"text": "Опубликован материал.", field: text_with_emoji})
                    matches = [f for f in result["findings"] if f["rule_id"] == rule_id]
                    self.assertEqual(len(matches), 1)
                    for evidence in matches[0]["evidence"]:
                        self.assertEqual(text_with_emoji[evidence["start"]:evidence["end"]], evidence["quote"])
                        self.assertEqual(evidence["field"], field)

    def test_user_example_covers_phrases_without_assigning_quotes_to_newsroom(self):
        result = analyze({"text": BLAHA_TEXT})
        expected = {
            "fear.security_superlative", "fear.predicted_criminal_spread", "fear.impending_unrest",
            "exaggeration.total_collapse", "enemy.militarized_collective", "dysphemism.criminal_label",
            "dysphemism.autocratic_label", "simplification.historical_parallel",
            "generalization.asserted_obviousness", "simplification.counterfactual_certainty",
            "context.quotation_omission",
        }
        self.assertEqual({f["rule_id"] for f in result["findings"]}, expected)
        self.assertEqual(result["summary"]["review_candidates"], 0)
        self.assertGreater(result["summary"]["candidate_fragments"], 0)
        for f in result["findings"]:
            self.assertEqual(f["status"], "context_only" if f["rule_id"] == "context.quotation_omission" else "quoted_candidate")
            for e in f["evidence"]:
                self.assertEqual(BLAHA_TEXT[e["start"]:e["end"]], e["quote"])

    def test_historical_names_alone_and_literal_contexts_are_not_rhetorical(self):
        cases = [
            "Гитлер возглавил правительство Германии в 1933 году.",
            "Историк сравнил внешнюю политику Гитлера с нацистской Германией.",
            "Историк сегодня рассказал, как Гитлер пришёл к власти.",
            "Депутат сегодня рассказал, как Гитлер пришёл к власти.",
            "Сегодня историки сравнили Германию с нацистской Германией.",
            "Сегодня историк описал нацистский режим Германии.",
            "Депутат сегодня обсуждал диктатора Гитлера.",
            "Гитлер — диктатор, пояснил сегодня депутат.",
            "Премьер Британии в 1938 году сравнил политику с нацистской Германией.",
            "Сталин действовал как Гитлер.",
            "Историк описал нацистский режим в Германии в 1939 году.",
            "Исследователь рассказал о кризисе на Балканах в 1990-е годы.",
            "Архив сохранил сведения о профессии палача при царском правительстве.",
            "Президент посетил выставку. Военная машина оснащена гусеницами и двигателем.",
            "Мэр сообщил: ветхое здание повреждено, всё разваливается.",
            "Парламент посмотрел фильм о головорезах.",
            "МЧС предупредило об угрозе наводнения и сообщило маршруты эвакуации.",
            "Низкий рейтинг правительства указан в опросе: приведены методика и выборка.",
            "Президент заявил, что хочет мира и развития экономики.",
            "В справке перечислены причины начала войны в 1914 году.",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"], [])

    def test_nazi_comparisons_inflections_and_political_sides(self):
        for target in ("Путин", "Трамп", "Зеленский", "Макрон", "Мерц"):
            for anchor in ("Гитлер", "нацистская Германия", "Третий рейх", "Муссолини"):
                text = f"{target} действует как {anchor}."
                with self.subTest(text=text):
                    self.assertEqual(len(self.findings(text, "enemy.nazi_analogy")), 1)
        for text in ("Депутат сравнил нынешнее правительство с нацистской Германией.",
                     "Историк сравнил современное правительство с нацистской Германией.",
                     "Украина действует как нацистская Германия.",
                     "Министр ведёт себя как Гитлер.",
                     "Путин действует подобно Гитлеру.", "Зеленский использует гитлеровские методы.",
                     "Сегодня правительство называют неонацистским режимом."):
            with self.subTest(text=text):
                self.assertTrue(any(f["rule_id"] in {"enemy.nazi_analogy", "enemy.nazi_political_label"}
                                    for f in analyze({"text": text})["findings"]))

    def test_quote_omissions_are_only_notices_and_not_proof_of_distortion(self):
        for marker in ("<...>", "[…]", "(...)", "< … >", "[ ... ]"):
            text = f"Депутат сказал: «Мы обсудили {marker} расходы»."
            with self.subTest(marker=marker):
                result = analyze({"text": text})
                f = result["findings"][0]
                self.assertEqual(f["rule_id"], "context.quotation_omission")
                self.assertEqual(f["status"], "context_only")
                self.assertTrue(f["evidence"][0]["context"]["quotation_edited"])
                self.assertEqual(f["evidence"][0]["quote"], marker)
                self.assertEqual(result["summary"]["candidate_fragments"], 0)
                self.assertNotIn("selective_context", SUPPORTED)
        for text in ("Мы подумали... и решили продолжить.", "Депутат сказал: «Мы подумали… и решили продолжить».",
                     "В шаблоне предусмотрено <...> для ввода.", "Депутат сказал: «Мы обсудили [...> расходы»."):
            self.assertEqual(self.findings(text, "context.quotation_omission"), [])

    def test_speech_attribution_after_statement_and_denials(self):
        text = "Украина — самая большая угроза безопасности в будущем, заявил депутат Европарламента."
        f = self.findings(text, "fear.security_superlative")[0]
        self.assertEqual(f["status"], "quoted_candidate")
        self.assertTrue(f["evidence"][0]["context"]["reported_speech"])
        for pronoun in ("его", "её", "ее", "их"):
            text = f"По {pronoun} словам, очевидно, что правительство ошибается."
            self.assertEqual(self.findings(text, "generalization.asserted_obviousness")[0]["status"], "quoted_candidate")
        for text, rule_id in (
            ("Политические оппоненты не головорезы.", "dysphemism.criminal_label"),
            ("Нынешний министр действует не как Гитлер.", "enemy.nazi_analogy"),
            ("Фраза «всё разваливается» обсуждается в парламенте.", "exaggeration.total_collapse"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.findings(text, rule_id)[0]["status"], "context_only")

    def test_counters_deduplicate_labels_but_include_quoted_candidates(self):
        result = analyze({"text": "Депутат сказал: «Политики опасны без смирительной рубашки»."})
        self.assertEqual(result["summary"]["review_fragments"], 0)
        self.assertEqual(result["summary"]["quoted_candidates"], 2)
        self.assertEqual(result["summary"]["candidate_fragments"], 1)

    def test_publisher_identity_does_not_change_detection(self):
        expected = analyze({"text": BLAHA_TEXT})["findings"]
        for source in ("Известия", "RT", "BBC", "Другой источник"):
            self.assertEqual(analyze({"text": BLAHA_TEXT, "source": source})["findings"], expected)

    def test_bounded_patterns_on_long_near_matches(self):
        # Missing final words must not cause unbounded regex work; also exercised
        # in Wasm parity so pathological cases cannot freeze the manual worker.
        text = "если бы выборы " + "выборы " * ((MAX_CHARS - 100) // 7)
        self.assertEqual(analyze({"text": text})["findings"], [])


if __name__ == "__main__":
    unittest.main()
