"""Political personal labels: symmetric targets, literal and legal counterexamples."""

import unittest

from media_strazh.analysis import analyze


CASES = {
    "dysphemism.performer_label": "Зеленский — клоун.",
    "dysphemism.bloody_epithet": "Путин — кровавый.",
    "dysphemism.murderer_label": "Зеленский — убийца.",
    "dysphemism.autocratic_label": "Путин — диктатор.",
}
DOCUMENT = {"text": "Путин — клоун, кровавый диктатор и убийца.\nЗеленский — клоун, кровавый диктатор и убийца."}


class PersonLabelTests(unittest.TestCase):
    def labels(self, document):
        return [f for f in analyze(document)["findings"] if f["rule_id"] in CASES]

    def test_both_people_fields_and_exact_unicode_offsets(self):
        for who in ("Путин", "Зеленский", "Трамп", "Байден", "депутат"):
            for rule_id, text in CASES.items():
                text = text.replace("Путин", who).replace("Зеленский", who)
                for field in ("title", "text"):
                    with self.subTest(who=who, rule=rule_id, field=field):
                        value = "⚡️ " + text
                        findings = self.labels({"text": "Опубликован материал.", field: value})
                        self.assertEqual([f["rule_id"] for f in findings], [rule_id])
                        self.assertEqual(findings[0]["status"], "needs_review")
                        evidence = findings[0]["evidence"][0]
                        self.assertEqual(evidence["field"], field)
                        self.assertEqual(value[evidence["start"]:evidence["end"]], evidence["quote"])

    def test_inflections_nicknames_and_naming(self):
        for text, rule_id in (
            ("Путина назвали клоуном.", "dysphemism.performer_label"),
            ("Зеленскому дали ярлык: политик — паяц.", "dysphemism.performer_label"),
            ("Этот депутат — шут.", "dysphemism.performer_label"),
            ("Министра называют скоморохом.", "dysphemism.performer_label"),
            ("Депутатов назвали паяцами.", "dysphemism.performer_label"),
            ("Политика называют паяцем.", "dysphemism.performer_label"),
            ("Депутаты — скоморохи.", "dysphemism.performer_label"),
            ("Зеленский — просто клоун.", "dysphemism.performer_label"),
            ("Путин — обычный убийца.", "dysphemism.murderer_label"),
            ("Клоун Владимир Зеленский подписал документ.", "dysphemism.performer_label"),
            ("Кровавый Владимир Путин выступил.", "dysphemism.bloody_epithet"),
            ("Кровавый диктатор Зеленский выступил.", "dysphemism.bloody_epithet"),
            ("Критик осудил кровожадного президента.", "dysphemism.bloody_epithet"),
            ("Политиков назвали убийцами.", "dysphemism.murderer_label"),
            ("Убийца Путин подписал указ.", "dysphemism.murderer_label"),
            ("Убийцей назвали Владимира Зеленского.", "dysphemism.murderer_label"),
            ("Путин — убийца, а суд постановил перенести заседание.", "dysphemism.murderer_label"),
        ):
            with self.subTest(text=text):
                self.assertTrue(any(f["rule_id"] == rule_id for f in self.labels({"text": text})))

    def test_enumeration_keeps_each_label(self):
        for who in ("Путин", "Зеленский"):
            result = self.labels({"text": f"{who} — клоун, кровавый диктатор и убийца."})
            self.assertEqual({f["rule_id"] for f in result}, set(CASES))

    def test_quotes_speech_negation_and_discussion(self):
        for text, rule_id, status, flag in (
            ('Политик заявил: «Путин — клоун».', "dysphemism.performer_label", "quoted_candidate", "in_quotes"),
            ("Байден назвал Путина убийцей.", "dysphemism.murderer_label", "quoted_candidate", "reported_speech"),
            ("Клоуном назвали Зеленского.", "dysphemism.performer_label", "quoted_candidate", "reported_speech"),
            ("Диктатором называют Путина.", "dysphemism.autocratic_label", "quoted_candidate", "reported_speech"),
            ("Путин не клоун.", "dysphemism.performer_label", "context_only", "nearby_negation"),
            ("Зеленский не убийца.", "dysphemism.murderer_label", "context_only", "nearby_negation"),
            ('В адрес Путина использовали слово «клоун».', "dysphemism.performer_label", "context_only", "metalinguistic"),
        ):
            with self.subTest(text=text):
                findings = self.labels({"text": text})
                finding = next(f for f in findings if f["rule_id"] == rule_id)
                self.assertEqual(finding["status"], status)
                self.assertTrue(finding["evidence"][0]["context"][flag])

    def test_literal_professions_injury_crime_and_victim_genitives(self):
        for text in (
            "Путин посетил цирк. Клоун рассмешил детей.",
            "Клоун рассказал президенту о своей профессии.",
            "Депутат сыграл роль клоуна в спектакле.",
            "Депутат — клоун по профессии.",
            "Зеленский — клоун в школьной постановке.",
            "Путин увидел кровавый след на полу.",
            "Президент сообщил о кровавых событиях.",
            "В баре подают Кровавую Мэри.",
            "Путин посетил бар. Ему подали Кровавую Мэри.",
            "Он осудил кровавую политику.",
            "Критик осудил кровавую внешнюю политику Путина.",
            "Кровавое лидерство обсуждается в статье.",
            "На фото Путин — кровавый после ранения.",
            "Президент помиловал убийцу.",
            "Убийца президента задержан.",
            "Убийца Путина задержан.",
            "В статье обсуждается убийца Зеленского.",
            "Суд признал депутата убийцей.",
            "Депутат — убийца, постановил суд.",
            "Прокурор назвал политика убийцей в обвинительной речи.",
            "Президент встретился с осуждённым убийцей.",
            "Историк обсуждает диктатора Гитлера.",
            "В 1939 году президент — кровавый, написано в архивном документе.",
            "Клоун-рыба обитает в море.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.labels({"text": text}), [])

    def test_bounded_nickname_context_without_publisher_features(self):
        for document in (
            {"title": "Зеленский выступил", "text": "Клоун вновь потребовал помощи."},
            {"title": "Путин выступил", "text": "Кровавый подписал указ."},
            {"title": "Путин", "text": "Клоун"},
            {"text": "Зеленский выступил. Клоун вновь потребовал помощи."},
        ):
            with self.subTest(document=document):
                self.assertEqual(len(self.labels(document)), 1)
        for document in (
            {"text": "Клоун вновь потребовал помощи.", "source": "Путин"},
            {"text": "Путин посетил цирк. Клоун заявил о новой программе."},
            {"text": "Зеленский выступил.\nКлоун вновь потребовал помощи."},
            {"text": "Путин выступил. " + "Подробности события. " * 30 + "Клоун вновь потребовал помощи."},
        ):
            with self.subTest(document=document):
                self.assertEqual(self.labels(document), [])

    def test_publisher_and_url_do_not_change_labels(self):
        document = {"text": "Зеленский — клоун, кровавый диктатор и убийца."}
        expected = self.labels(document)
        for source in ("RT", "ТАСС", "Радио Свобода", "Медиазона"):
            self.assertEqual(self.labels({**document, "source": source, "url": "https://example.org/"}), expected)

    def test_existing_specific_insult_is_not_duplicated(self):
        for who in ("Путин", "Зеленский"):
            findings = analyze({"text": f"{who} — политический клоун."})["findings"]
            self.assertEqual([f["rule_id"] for f in findings], ["dysphemism.political_insult"])


if __name__ == "__main__":
    unittest.main()
