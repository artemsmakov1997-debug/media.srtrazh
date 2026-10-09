"""Regression examples and hard negatives, not an independent quality corpus."""

import unittest

from media_strazh.analysis import MAX_CHARS, analyze


class RhetoricTests(unittest.TestCase):
    def assertCandidate(self, text, category, quote):
        result = analyze({"text": text})
        matches = [f for f in result["findings"] if f["category"] == category and f["status"] == "needs_review"]
        self.assertTrue(matches, result)
        self.assertTrue(any(quote in e["quote"] for f in matches for e in f["evidence"]))
        for f in result["findings"]:
            for e in f["evidence"]:
                self.assertEqual(text[e["start"]:e["end"]], e["quote"])

    # Short, attributed excerpts from the article chosen by the user:
    # Андрей Рудалёв, «Утешение войной», RT, 2026-10-08.
    # https://russian.rt.com/opinion/1692015-rudalev-voina-krizis-evropa
    # They are development examples, never a held-out evaluation set.
    def test_rt_generalization(self):
        self.assertCandidate("Но у европейских политиков ответ один: они чихать хотели на мнения, которые расходятся с их догмами.", "generalization", "ответ один")

    def test_rt_slaughter_metaphor(self):
        self.assertCandidate("Зачем ей думать о чаяниях немецкого народа, который тащат на бойню?", "fear", "тащат на бойню")

    def test_rt_destructive_intent(self):
        self.assertCandidate("Судя по всему, хотят существенно проредить и своё население, устроив своеобразную судную ночь или голодные игры.", "enemy_image", "хотят существенно проредить")

    def test_rt_dysphemism(self):
        self.assertCandidate("Не она одна такая в Германии альтернативно одарённая.", "euphemism_dysphemism", "альтернативно одарённая")

    def test_rt_catastrophic_forecast(self):
        self.assertCandidate("Следующий этап европейского политического падения тоже несложно спрогнозировать: тотальная диктатура.", "fear", "тотальная диктатура")

    def test_rt_innate_nature(self):
        self.assertCandidate("Так исторически повелось, что, объединяясь, Европа принималась готовиться в военный поход — таков древний инстинкт.", "generalization", "древний инстинкт")

    def test_new_phrases_not_only_the_development_article(self):
        cases = [
            ("Военные ведут граждан на заклание.", "fear", "на заклание"),
            ("Эти власти — марионетки заокеанских хозяев.", "enemy_image", "марионетки"),
            ("Все американские политики лгут.", "generalization", "Все американские политики лгут"),
            ("Каждый здравомыслящий человек должен поддержать решение.", "generalization", "здравомыслящий человек"),
            ("Правительство захватило всё информационное пространство.", "exaggeration", "всё информационное пространство"),
            ("Либо ты с нами, либо ты предатель.", "oversimplification", "предатель"),
            ("Единственное решение — война.", "oversimplification", "Единственное решение"),
            ("Он принял бессовестное решение.", "emotional_evaluation", "бессовестное"),
            ("Он принял наглое и подлое решение.", "emotional_evaluation", "наглое"),
            ("Его описали как политического клоуна.", "euphemism_dysphemism", "политического клоуна"),
        ]
        for text, category, quote in cases:
            with self.subTest(text=text):
                self.assertCandidate(text, category, quote)

    def test_geography_does_not_change_the_rule(self):
        for adjective in ("европейских", "российских", "американских", "украинских"):
            with self.subTest(adjective=adjective):
                self.assertCandidate(f"У {adjective} политиков ответ один.", "generalization", "ответ один")

    def test_clinical_metaphor_has_two_labels_not_two_distinct_quotes(self):
        result = analyze({"text": "Политики опасны без смирительной рубашки."})
        self.assertEqual(set(result["summary"]["by_category"]), {"enemy_image", "euphemism_dysphemism"})
        self.assertEqual(len({(e["start"], e["end"]) for f in result["findings"] for e in f["evidence"]}), 1)
        self.assertEqual(result["summary"]["review_fragments"], 1)
        self.assertEqual(result["summary"]["review_candidates"], 2)

    def test_literal_medical_biological_and_entertainment_reports(self):
        cases = [
            "Президент посетил больницу. Врач отметил, что пациенты опасны без смирительной рубашки.",
            "Врач подтвердил диагноз у пациента: это генетическое заболевание.",
            "Европейские генетики исследовали заболевание. Это генетическое нарушение.",
            "Мэр сообщил, что биологи обнаружили паразитов у животных.",
            "Работники отправляют скот на бойню.",
            "В парламенте показали фильм «Голодные игры».",
            "Театр представил спектакль о политических марионетках.",
            "Мэр сообщил, что специалисты проводят дератизацию: в здании обнаружены крысы.",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"], [])

    def test_neutral_difficult_words_are_not_loaded_evaluations(self):
        cases = [
            "Архив подтвердил подлинность документа. Он подлежит публикации.",
            "Компостную кучу нельзя наглухо закрывать плёнкой; допустимо укрытие спанбондом.",
            "МЧС предупредило об опасности наводнения и сообщило адреса эвакуации.",
            "Историк рассказал о диктатуре и военных действиях в 1940 году.",
            "Матвиенко, Мерц, Бербок и Зеленский упомянуты в сообщении.",
            "Россия, Украина, США и страны Европы участвовали в переговорах.",
            "Экономист Иван Петров представил данные о росте расходов.",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"], [])

    def test_reported_speech_without_quotes_is_not_assigned_to_author(self):
        result = analyze({"text": "Министр заявил, что решение возмутительное."})
        self.assertEqual(result["summary"]["review_candidates"], 0)
        self.assertEqual(result["summary"]["quoted_candidates"], 1)
        self.assertFalse(result["findings"][0]["evidence"][0]["context"]["in_quotes"])
        self.assertTrue(result["findings"][0]["evidence"][0]["context"]["reported_speech"])

    def test_new_patterns_in_quotes_and_denials(self):
        cases = [
            ('Депутат сказал: «Все политики лгут».', "quoted_candidate"),
            ('Фраза «война как единственный выход» обсуждалась на семинаре.', "context_only"),
            ('Президент отверг тезис «война как единственный выход».', "context_only"),
            ('Власти не хотят уничтожить население.', "context_only"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                result = analyze({"text": text})
                self.assertTrue(result["findings"])
                self.assertEqual(result["summary"]["review_candidates"], 0)
                self.assertTrue(all(f["status"] == expected for f in result["findings"]))

    def test_headline_bait_does_not_fire_on_body_text(self):
        result = analyze({"title": "Вся правда о налогах", "text": "Опубликована новая ставка налога."})
        self.assertEqual(result["findings"][0]["category"], "clickbait")
        self.assertEqual(analyze({"text": "Вся правда о налогах изложена в отчёте."})["findings"], [])

    def test_new_patterns_are_independent_of_publisher(self):
        text = "Политики опасны без смирительной рубашки. Все политики лгут."
        outputs = [analyze({"text": text, "source": source}) for source in ("RT", "РИА", "ТАСС", "Другой источник")]
        for result in outputs[1:]:
            self.assertEqual(result["findings"], outputs[0]["findings"])

    def test_large_unbroken_token_does_not_break_offsets_or_limits(self):
        text = "я" * (MAX_CHARS - 25) + "\nБессовестное решение."
        result = analyze({"text": text})
        self.assertEqual(result["summary"]["review_candidates"], 1)
        e = result["findings"][0]["evidence"][0]
        self.assertEqual(text[e["start"]:e["end"]], "Бессовестное")


if __name__ == "__main__":
    unittest.main()
