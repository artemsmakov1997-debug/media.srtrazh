"""User screenshot regressions and synthetic counterexamples, not a quality score."""

import unittest

from media_strazh.analysis import analyze


SCHOOL_DOCUMENT = {
    "title": 'К 15-летней школьнице из Татарстана пришли с обыском из-за видео с разорванным плакатом "Единой России"',
    "text": 'В Татарстане к 15-летней школьнице Анне (имя изменено) пришли силовики с обыском из-за тиктока, на котором она рвет предвыборный плакат "Единой России".\n\n'
            'Во время беседы силовики начали говорить о том, какой срок может грозить Анне, из-за чего у нее "началась сильная истерика".',
}
INSECTS_DOCUMENT = {
    "title": "Тренера сборной России по гимнастике поселили в номер с клопами в Нидерландах",
    "text": "<...> Они все в крови.\n\nСотрудники метрополитена Бухареста 16 июня рассказали о массовом распространении клопов в нескольких депо и предупредили пассажиров о риске принести насекомых домой после поездки.",
}


class ContextPrecisionTests(unittest.TestCase):
    def findings(self, document, rule_id):
        return [f for f in analyze(document)["findings"] if f["rule_id"] == rule_id]

    def test_screenshot_emotion_is_not_a_political_psychological_label(self):
        result = analyze(SCHOOL_DOCUMENT)
        self.assertFalse([f for f in result["findings"] if f["category"] == "enemy_image"])
        self.assertEqual(result["summary"]["candidate_fragments"], 0)
        self.assertEqual([f["evidence"][0]["quote"] for f in result["findings"]], ["силовики", "силовики"])

    def test_screenshot_insects_are_literal_despite_country_in_title(self):
        result = analyze(INSECTS_DOCUMENT)
        self.assertFalse([f for f in result["findings"] if f["category"] == "enemy_image"])
        self.assertEqual(result["summary"]["candidate_fragments"], 0)

    def test_distress_events_do_not_become_enemy_labels_in_political_reports(self):
        examples = (
            'В России у школьницы "началась сильная истерика" после обыска.',
            'Депутат рассказал, что у неё началась истерика.',
            'Во время обыска у ребёнка случилась истерика, сообщили силовики.',
            'Россия: девочка впала в истерику после задержания матери.',
            'В парламенте школьница расплакалась: её довели до истерики.',
            'У президента началась сильная истерика после известия о гибели сына.',
            'Президент пережил истерику после гибели близкого человека.',
            'Мать рассказала: «У дочери сильная истерика после обыска».',
            'Президент открыл школу. У девочки истеричная реакция на испуг.',
        )
        for text in examples:
            for field in ("title", "text"):
                with self.subTest(text=text, field=field):
                    document = {"text": "Опубликован материал.", field: text}
                    self.assertFalse(self.findings(document, "enemy.political_madness"))

    def test_hostile_psychological_labels_still_respect_attribution(self):
        cases = (
            ("Истеричная реакция главы киевского режима напугала европейцев, пишет Financial Times.", "quoted_candidate"),
            ("Президент закатил истерику из-за решения парламента.", "needs_review"),
            ("Президент — безумец, заявил депутат.", "quoted_candidate"),
            ("Депутат заявил: «Президент — психопат».", "quoted_candidate"),
            ("Президент выступил. Он закатил истерику из-за решения.", "needs_review"),
            ("Политики не безумцы, они обсуждают решение.", "context_only"),
        )
        for text, status in cases:
            with self.subTest(text=text):
                found = self.findings({"text": text}, "enemy.political_madness")
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["status"], status)

    def test_literal_pests_need_no_special_publisher_or_location(self):
        examples = (
            "Президент сообщил: в гостинице обнаружили насекомых и клопов.",
            "В России обнаружили насекомых нового вида.",
            "Депутат предупредил о риске принести насекомых домой после поездки.",
            "Министр сообщил: европейские беспозвоночные обитают в ручьях.",
            "Министр показал насекомых, собранных для исследования.",
            "Путин рассказал о вредителях. Насекомые размножаются в тёплом климате.",
            "В депо обнаружили клопов. Пассажиры могут принести насекомых домой.",
            "Президент сообщил: в гостиничном номере обнаружили вшей и гнид.",
            "Министр сообщил: насекомые повредили посадки.",
            "Путин рассказал, что насекомые могут переносить инфекции.",
            "Власти запретили ввоз насекомых.",
            "Министр обсудил меры против вшей и гнид.",
            "Президент: «Насекомые могут переносить инфекции».",
            "Министр: беспозвоночные обитают в ручьях.",
        )
        for text in examples:
            for field in ("title", "text"):
                with self.subTest(text=text, field=field):
                    document = {"text": "Опубликован материал.", field: text}
                    self.assertFalse(self.findings(document, "enemy.pest_dehumanization"))

    def test_direct_human_metaphor_survives_literal_background(self):
        examples = (
            "В депо обнаружили клопов. Депутат назвал президента беспозвоночным.",
            "В гостинице обнаружили клопов. Политик — тварь.",
            "Президент Зеленский — насекомое, заявил депутат в гостинице.",
            "В зоопарке депутат назвал политиков насекомыми.",
            "Насекомыми назвал депутатов выступавший в гостинице политик.",
            "Министр посетил зоопарк. Люди — не насекомые.",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(self.findings({"text": text}, "enemy.pest_dehumanization"))

    def test_political_prisoner_variants_are_informational_with_exact_offsets(self):
        variants = ("Политзаключённый", "политзаключенный", "политзаключённая", "политзаключённых",
                    "политзаключёнными", "политзэк", "политзек", "политзэка", "политзеки",
                    "политзэков", "политзеками", "политзак", "политзаком",
                    "политический заключённый", "политических заключенных", "политической заключённой")
        for phrase in variants:
            for field in ("title", "text"):
                with self.subTest(phrase=phrase, field=field):
                    value = "📰 " + phrase + " — обозначение в публикации."
                    result = analyze({"text": "Опубликован материал.", field: value})
                    found = result["findings"]
                    self.assertEqual(len(found), 1)
                    f = found[0]
                    self.assertEqual((f["rule_id"], f["category"], f["status"]),
                                     ("terminology.political_prisoner", "actor_terminology", "context_only"))
                    e = f["evidence"][0]
                    self.assertEqual((e["field"], value[e["start"]:e["end"]], e["quote"]), (field, phrase, phrase))
                    self.assertTrue(e["context"]["informational_notice"])
                    for key in ("candidate_fragments", "review_candidates", "quoted_candidates", "review_fragments"):
                        self.assertEqual(result["summary"][key], 0)
                    self.assertEqual(result["summary"]["by_category"], {})
        for text in ("Заключённый прочитал политическую статью.", "Политическое заключение эксперта опубликовано.",
                     "Политзековский жаргон исследуют филологи."):
            self.assertFalse(self.findings({"text": text}, "terminology.political_prisoner"))

    def test_prisoner_notice_preserves_quote_negation_and_real_rhetoric(self):
        for text, flag in (
            ('Автор заявил: «Политзаключённый освобождён».', "in_quotes"),
            ('Его не считают политзэком.', "nearby_negation"),
        ):
            f = self.findings({"text": text}, "terminology.political_prisoner")[0]
            self.assertEqual(f["status"], "context_only")
            self.assertTrue(f["evidence"][0]["context"][flag])
        document = {"text": "Политзэк освобождён. Все знают о решении."}
        result = analyze(document)
        self.assertEqual(result["summary"]["candidate_fragments"], 1)
        for source in ("RT", "Радио Свобода", "Медиазона", "ИноСМИ"):
            self.assertEqual(analyze(dict(document, source=source))["findings"], result["findings"])


if __name__ == "__main__":
    unittest.main()
