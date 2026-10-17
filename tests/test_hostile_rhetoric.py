"""User-supplied development examples; linked sources do not verify Trump's quote."""

import unittest

from media_strazh.analysis import analyze


# User-supplied links; verification/access evidence is in the review document.
VANNACCI_URL = "https://t.me/inosmichannel/32847"
HOSTILE_URL = "https://t.me/medvedev_telegram/666"

VANNACCI_POST = """«Он нас с банкоматом перепутал»

Лидер итальянской партии «Национальное будущее» Ванначчи возмутился требованием Бутафорного дать еще 70 миллиардов евро.

Политик призвал прекратить отправлять деньги Украине и направить эти средства на помощь европейцам."""

HOSTILE_POST = """Трамп: «Они [украинцы] не будут мириться при Зеленском. Он не хочет мириться. Он говорит, что хочет мириться, но на самом деле не хочет. Я не большой поклонник Зеленского. Он разрушил Украину».

После такого суетливое существо с нелепым именем, почему-то заканчивающимся в английской транскрипции на double «y», должно было бы принять крысиный яд или сожрать лошадиную дозу своего любимого кокса.

Но тварь так труслива, что не решится на подобное. «Человек года» и «новый Черчилль» признан своим бывшим хозяином помехой миру и интересам США. Ведь он до крови укусил кормящую его руку.

Европейские беспозвоночные уговаривают киевскую вошь запастись терпением, не злить дядюшку Джо и дождаться проигрыша республиканцев на выборах в Конгресс. Они ненавидят Трампа не меньше наркотического насекомого. Но и в этом случае киевских членистоногих ждёт обработка ядовитым дустом. Дядя дезинсектор злопамятен и не должен прощать тварь, которая стала одной из важных причин его поражения на выборах.

И тут он будет прав. Ведь чем скорее сдохнут тифозные гниды, тем лучше будет эпидемиологическая ситуация в мире…"""

POSITIVE_CASES = {
    "dysphemism.bogus_nickname": "Политик потребовал ответа от Бутафорного.",
    "enemy.pest_dehumanization": "Европейские беспозвоночные обсуждают решение правительства.",
    "emotion.death_wish": "Президент должен был бы принять крысиный яд.",
    "enemy.extermination_metaphor": "Киевских политиков ждёт обработка ядовитым дустом.",
    "dysphemism.drug_smear": "Президенту предлагают дозу его любимого кокса.",
    "emotion.personal_ridicule": "Политик с нелепым именем объявил решение.",
    "enemy.patron_dependency": "Президент был признан своим бывшим хозяином помехой.",
    "authority.attributed_political_evaluation": "Политик призвал прекратить отправлять деньги Украине.",
}


class HostileRhetoricTests(unittest.TestCase):
    def matching(self, text, rule_id):
        return [f for f in analyze({"text": text})["findings"] if f["rule_id"] == rule_id]

    def test_new_rules_have_exact_unicode_evidence_in_title_and_body(self):
        for rule_id, text in POSITIVE_CASES.items():
            for field in ("title", "text"):
                with self.subTest(rule_id=rule_id, field=field):
                    value = "📰 " + text
                    result = analyze({"text": "Опубликован материал.", field: value})
                    found = [f for f in result["findings"] if f["rule_id"] == rule_id]
                    self.assertEqual(len(found), 1)
                    evidence = found[0]["evidence"][0]
                    self.assertEqual((evidence["field"], value[evidence["start"]:evidence["end"]]),
                                     (field, evidence["quote"]))

    def test_first_user_post_marks_nickname_and_attributed_call_not_proven_editorial_bias(self):
        found = analyze({"text": VANNACCI_POST})["findings"]
        nickname = next(f for f in found if f["rule_id"] == "dysphemism.bogus_nickname")
        self.assertEqual(nickname["evidence"][0]["quote"], "Бутафорного")
        authority = next(f for f in found if f["rule_id"] == "authority.attributed_political_evaluation")
        self.assertEqual(authority["status"], "quoted_candidate")
        self.assertTrue(authority["evidence"][0]["context"]["reported_speech"])
        coverage = {item["id"]: item["coverage"] for item in analyze({"text": VANNACCI_POST})["coverage"]}
        self.assertEqual(coverage["selective_context"], "not_evaluated")

    def test_second_user_post_preserves_each_key_attack_and_quote_status(self):
        result = analyze({"text": HOSTILE_POST})
        found = result["findings"]
        for phrase in ("суетливое существо", "нелепым именем", "принять крысиный яд", "любимого кокса",
                       "тварь", "бывшим хозяином", "кормящую его руку", "Европейские беспозвоночные",
                       "киевскую вошь", "наркотического насекомого", "киевских членистоногих",
                       "обработка ядовитым дустом", "Дядя дезинсектор", "тифозные гниды"):
            with self.subTest(phrase=phrase):
                self.assertTrue(any(phrase in e["quote"] for f in found for e in f["evidence"]), phrase)
        voices = [f for f in found if f["rule_id"] == "authority.attributed_political_evaluation"]
        self.assertGreaterEqual(len(voices), 1)
        self.assertTrue(all(f["status"] == "quoted_candidate" for f in voices))
        self.assertTrue(any(f["status"] == "needs_review" for f in found if f["rule_id"] == "emotion.death_wish"))
        for f in found:
            for e in f["evidence"]:
                self.assertEqual(HOSTILE_POST[e["start"]:e["end"]], e["quote"])

    def test_declensions_and_adjacent_political_reference_are_not_a_fixed_quote_dictionary(self):
        examples = {
            "dysphemism.bogus_nickname": ("Министр обсудил Бутафорного.", "Депутат назвал его Бутафорным."),
            "enemy.pest_dehumanization": ("Министр выступил. Эти гниды трусливы.", "Политик — тварь.",
                                         "Европейских политиков назвали вшами.", "Депутат назвал президента беспозвоночным."),
            "enemy.extermination_metaphor": ("Президент выступил. Дядя дезинсектор всё решит.",),
            "enemy.patron_dependency": ("Президент укусил кормящую его руку.",),
            "emotion.death_wish": ("Чем скорее сдохнут эти политики, тем лучше.",),
        }
        for rule_id, texts in examples.items():
            for text in texts:
                with self.subTest(rule_id=rule_id, text=text):
                    self.assertTrue(self.matching(text, rule_id))

    def test_literal_props_animals_medicine_industry_and_fiction_are_excluded(self):
        examples = (
            "Президент осмотрел бутафорный меч.", "Министр показал бутафорные документы.",
            "Депутат продемонстрировал бутафорную корону.", "Для спектакля подготовили Бутафорного.",
            "Министр посетил зоопарк: биолог показал насекомых и беспозвоночных.",
            "Министр посетил зоопарк. Насекомые живут в специальных условиях.",
            "Президент обсудил санитарные меры. В квартире обнаружили вшей и гнид.",
            "Министр рассказал: дезинсектор провёл обработку ядовитым дустом в подвале.",
            "Министр объявил решение. Дезинсектор провёл обследование.",
            "Депутат встретил бывшего хозяина собаки в приюте.",
            "Президент осмотрел завод: металлург рассказал о качестве любимого кокса.",
            "В романе президент с нелепым именем назван тварью.",
            "Врач рассказал о лечении педикулёза и об уничтожении гнид.",
            "Биолог объяснил, что чем скорее сдохнут вредители, тем лучше для посевов.",
            "Мэр сообщил, что в спектакле герой должен был бы принять крысиный яд.",
            "Лидер компании призвал прекратить отправлять деньги Украине.",
            "Министр сообщил дату заседания правительства.",
            "Президент приехал в музей. Восстановили бутафорный старинный трон.",
        )
        ids = set(POSITIVE_CASES)
        for text in examples:
            with self.subTest(text=text):
                self.assertFalse([f for f in analyze({"text": text})["findings"] if f["rule_id"] in ids])

    def test_attribution_needs_a_political_speaker_and_relevant_claim(self):
        positive = (
            "Путин заявил: «Он разрушил страну».",
            "Трамп: «Он не хочет мириться. Он разрушил Украину».",
            "Депутат предложил прекратить поставлять оружие России.",
        )
        for text in positive:
            with self.subTest(text=text):
                self.assertTrue(self.matching(text, "authority.attributed_political_evaluation"))
        for text in ("Политик сообщил время заседания.", "Он разрушил страну.",
                     "Трамп выступил.\n\nОн разрушил Украину.",
                     "Тренер заявил: «Он разрушил страну»."):
            with self.subTest(text=text):
                self.assertFalse(self.matching(text, "authority.attributed_political_evaluation"))

    def test_quotes_rejection_discussion_and_negation_remain_distinct(self):
        for text, rule_id, status in (
            ("Президент заявил: «Европейские беспозвоночные обсуждают решение».", "enemy.pest_dehumanization", "quoted_candidate"),
            ("Политик не тварь, он участник переговоров.", "enemy.pest_dehumanization", "context_only"),
            ("Слово «Бутафорный» использовали в адрес политика.", "dysphemism.bogus_nickname", "context_only"),
            ("Фраза «обработка ядовитым дустом» обращена к политикам.", "enemy.extermination_metaphor", "context_only"),
            ("Нельзя утверждать, что президент — тварь.", "enemy.pest_dehumanization", "context_only"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.matching(text, rule_id)[0]["status"], status)

    def test_publisher_identity_and_political_direction_do_not_decide_the_match(self):
        expected = analyze({"text": HOSTILE_POST})["findings"]
        for source in ("RT", "BBC", "ИноСМИ", "Медиазона", "Неизвестное издание"):
            self.assertEqual(analyze({"text": HOSTILE_POST, "source": source})["findings"], expected)
        for target in ("Путин", "Байден", "Зеленский", "Макрон"):
            text = target + " — тварь. Он должен был бы принять крысиный яд."
            found = {f["rule_id"] for f in analyze({"text": text})["findings"]}
            self.assertIn("enemy.pest_dehumanization", found)
            self.assertIn("emotion.death_wish", found)

    def test_comparison_and_refusal_to_forgive_do_not_negate_the_epithet(self):
        for text in ("Политики ненавидят Трампа не меньше наркотического насекомого.",
                     "Президент не должен прощать тварь."):
            found = self.matching(text, "enemy.pest_dehumanization")
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["status"], "needs_review")
        result = analyze({"text": HOSTILE_POST})
        self.assertFalse([f for f in result["findings"] if f["rule_id"] in POSITIVE_CASES and f["status"] == "context_only"])

    def test_public_preview_line_spacing_and_source_signature_keep_the_same_cues(self):
        for text, signature in ((VANNACCI_POST, "\n🔸ИноСМИ — главное международное"), (HOSTILE_POST, "")):
            compact = text.replace("\n\n", "\n") + signature
            original = analyze({"text": text})
            preview = analyze({"text": compact})
            cues = lambda result: [(f["rule_id"], f["status"], [e["quote"] for e in f["evidence"]]) for f in result["findings"]]
            self.assertEqual(cues(original), cues(preview))
            self.assertEqual(original["summary"], preview["summary"])


if __name__ == "__main__":
    unittest.main()
