"""Development regressions and counterexamples; not measured corpus accuracy."""

import unittest

from media_strazh.analysis import MAX_CHARS, MAX_FINDINGS, analyze
from media_strazh.rules import RULES


POSITIVE_CASES = {
    "fear.existential_threat": "Это угроза самому существованию нашей страны.",
    "fear.conditional_destruction": "Если мы не поддержим этот закон, нас уничтожат.",
    "fear.last_chance": "Это последний шанс спасти нашу страну.",
    "emotion.contempt_phrase": "Политики с пеной у рта защищают решение.",
    "emotion.moral_condemnation": "Началась грязная игра вокруг бюджета.",
    "emotion.flag_waving": "Каждый настоящий патриот должен поддержать решение.",
    "emotion.political_slogan": "Ни шагу назад — наш принцип в споре о правительстве.",
    "emotion.glittering_virtue": "Только наше правительство принесёт мир.",
    "emotion.exalted_leader": "Гениальный президент спасёт страну.",
    "enemy.traitor_label": "В парламенте заседают враги народа.",
    "enemy.group_animalization": "Политические оппоненты — свора.",
    "enemy.hidden_plot": "Закулисные кукловоды управляют правительством.",
    "enemy.criminal_regime": "Этот преступный режим должен уйти.",
    "enemy.guilt_by_association": "Он дружит с противником, значит он тоже предатель.",
    "enemy.insinuated_coincidence": "Министр сменил позицию после встречи. Совпадение? Не думаю.",
    "enemy.questioned_independence": "Якобы независимые эксперты защищают решение.",
    "generalization.bandwagon": "Все это одобряют, поэтому ты должен согласиться.",
    "generalization.asserted_consensus": "Это очевидно каждому: программу следует принять.",
    "generalization.invariable_group": "Политики всегда лгут.",
    "exaggeration.absolute_evil": "Для правительства это полный и окончательный провал.",
    "exaggeration.minimized_casualties": "Подумаешь, несколько жертв.",
    "exaggeration.dismissed_harm": "Погибли люди, но это всего лишь инцидент.",
    "source.indeterminate_report": "По некоторым данным, заседание перенесли.",
    "authority.unquestionable_words": "Слова президента не подлежат сомнению.",
    "authority.status_as_proof": "Это верно, потому что президент так сказал.",
    "authority.forbidden_judgment": "Не нам критиковать решения лидера.",
    "simplification.no_alternative": "Правительство должно принять закон: другого выхода нет.",
    "simplification.binary_survival": "Либо мы примем закон, либо нас уничтожат.",
    "simplification.single_cause": "Все наши проблемы из-за этого правительства.",
    "simplification.discussion_killer": "Нечего тут думать, поддержите решение.",
    "simplification.nature_as_answer": "Так было всегда и всегда будет.",
    "simplification.whataboutism_cue": "Прежде чем нас критиковать, посмотрите на себя.",
    "simplification.hypocrisy_dismissal": "Вы сами нарушаете закон, поэтому не вправе нас критиковать.",
    "simplification.strawman_cue": "Значит, вы хотите разрушить государство.",
    "dysphemism.people_as_material": "Солдаты — расходный материал.",
    "dysphemism.political_disgust": "В парламенте сидят политические проститутки.",
    "clickbait.forbidden_revelation": "Прочитайте это пока не удалили",
}


class ExpandedRhetoricTests(unittest.TestCase):
    def test_each_new_rule_has_an_exact_span_regression(self):
        rules = {rule.id: rule for rule in RULES}
        for rule_id, text in POSITIVE_CASES.items():
            with self.subTest(rule_id=rule_id):
                rule = rules[rule_id]
                document = {"title": text, "text": "Опубликован материал."} if rule.fields == ("title",) else {"text": text}
                result = analyze(document)
                matches = [finding for finding in result["findings"] if finding["rule_id"] == rule_id]
                self.assertTrue(matches, result)
                self.assertTrue(all(finding["status"] == "needs_review" for finding in matches), result)
                for finding in result["findings"]:
                    for evidence in finding["evidence"]:
                        original = document.get(evidence["field"], "")
                        self.assertEqual(original[evidence["start"]:evidence["end"]], evidence["quote"])

    def test_ordinary_sources_values_and_choices_are_not_techniques(self):
        texts = [
            "Эксперт Иван Петров представил данные и объяснил методику расчёта.",
            "Президент сообщил, что отчёт опубликован на сайте.",
            "Большинство участников опроса поддерживают закон: 57% из 1200 респондентов.",
            "Миллионы людей приняли участие в выборах.",
            "Министерство разработало программу патриотического воспитания.",
            "Патриотизм и свобода обсуждались на лекции.",
            "Два варианта доставки: либо поезд, либо самолёт.",
            "Парламент рассмотрел два законопроекта и отложил голосование.",
            "В работе рассмотрены причины инфляции и ограничения прогноза.",
            "МЧС сообщило об угрозе пожара, перечислив адреса эвакуации.",
            "Пожарные спасли семью, пострадавших нет.",
            "Из резервуара вытекло немного воды: это небольшой инцидент.",
            "Проекту нужно несколько жертвователей для оплаты аренды.",
            "Наблюдатели изучили сведения о финансировании организации.",
            "Историк представил документы о правительстве Германии в 1939 году.",
            "Это совпадение последовательностей в генетическом анализе.",
            "Власти сообщили о дератизации: в здании обнаружены тараканы.",
            "Биолог описал поведение своры собак.",
            "Для лечения необходим расходный материал: врач назвал стоимость бинтов.",
            "Граждане купили расходные материалы для принтеров.",
            "Нас интересует расходный материал для новой мастерской.",
            "Народ обсуждает проект бюджета. Биомасса на заводе используется как топливо.",
            "Граждане пришли на открытие выставки. Свора собак пробежала по двору.",
            "Фильм о президенте называется «Ни шагу назад».",
            "Страна увеличила расходы на поддержку семей.",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"], [])

    def test_authority_popularity_and_national_feeling_require_argument_cues(self):
        self.assertEqual(analyze({"text": "Президент прав в этом случае: в документе приведены расчёты."})["findings"], [])
        self.assertEqual(analyze({"text": "Большинство это поддерживает, но результат зависит от расходов."})["findings"], [])
        self.assertEqual(analyze({"text": "Настоящий патриот может не поддерживать отдельные решения."})["findings"], [])
        self.assertEqual(analyze({"text": "Только наше правительство опубликовало статистику расходов."})["findings"], [])

    def test_positive_and_negative_valuations_both_have_cues(self):
        for text in ("Гениальный президент.", "Началась грязная игра."):
            result = analyze({"text": text})
            self.assertIn("emotional_evaluation", result["summary"]["by_category"])
        self.assertEqual(analyze({"text": "Спасатели помогли людям, подарив надежду."})["findings"], [])

    def test_people_targets_and_literal_material_are_distinguished(self):
        for text, rule_id in (("Политические оппоненты — тараканы.", "enemy.group_animalization"),
                              ("Граждан считают расходным материалом.", "dysphemism.people_as_material"),
                              ("Журналисты — расходный материал для правительства.", "dysphemism.people_as_material"),
                              ("Политические оппоненты — биомасса, пригодная лишь на топливо.", "enemy.group_animalization"),
                              ("Эти политики — кошмар и свора.", "enemy.group_animalization")):
            with self.subTest(text=text):
                self.assertTrue(any(finding["rule_id"] == rule_id for finding in analyze({"text": text})["findings"]))

    def test_political_actors_supply_context_but_literal_animals_do_not(self):
        for actor in ("Оппозиционеры", "Парламент", "Сенаторы", "Конгрессмены", "Губернаторы", "Мэры"):
            with self.subTest(actor=actor):
                result = analyze({"text": f"{actor} — крысы."})
                self.assertTrue(any(finding["rule_id"] == "enemy.dehumanization" and finding["status"] == "needs_review"
                                    for finding in result["findings"]))
                for literal in (f"{actor} обсудили бюджет.\nБиологи исследовали грызунов: крысы живут группами.",
                                f"{actor} обсудили бюджет.\nСвора собак пробежала по двору."):
                    self.assertEqual(analyze({"text": literal})["findings"], [])

    def test_quotes_and_new_report_verbs_keep_attribution(self):
        phrase = "Это верно, потому что президент так сказал"
        for text in (f'Он написал: «{phrase}».', f"Автор сообщения написал, что {phrase.lower()}.",
                     "Министр пояснил, что каждый настоящий патриот должен поддержать закон."):
            with self.subTest(text=text):
                result = analyze({"text": text})
                self.assertTrue(result["findings"])
                self.assertEqual(result["summary"]["review_candidates"], 0)
                self.assertTrue(all(finding["status"] == "quoted_candidate" for finding in result["findings"]))

    def test_discussion_denial_and_negation_are_context(self):
        for text in ("Фраза «Это верно, потому что президент так сказал» обсуждалась на уроке.",
                     "Министр отверг тезис «Все наши проблемы из-за этого правительства».",
                     "Нельзя считать, что президент всегда прав.",
                     "Автор опроверг утверждение, будто политики всегда обманывают.",
                     "Не каждый настоящий патриот должен поддержать это решение.",
                     "Лозунг «Ни шагу назад» вошёл в политическую историю."):
            with self.subTest(text=text):
                result = analyze({"text": text})
                self.assertTrue(result["findings"])
                self.assertEqual(result["summary"]["review_candidates"], 0)
                self.assertTrue(all(finding["status"] == "context_only" for finding in result["findings"]))

    def test_internal_negation_in_a_rhetorical_phrase_is_not_external_denial(self):
        for text in ("Миллионы людей не могут ошибаться.", "Это не обсуждается, точка.", "Не нам судить слова президента."):
            with self.subTest(text=text):
                self.assertGreater(analyze({"text": text})["summary"]["review_candidates"], 0)

    def test_html_emoji_and_line_breaks_do_not_change_offsets(self):
        text = "😀\r\n<b>Гениальный президент</b>.\nПрежде чем нас критиковать, посмотрите на себя."
        result = analyze({"text": text})
        self.assertEqual(result["document"]["text"], text)
        self.assertEqual(result["findings"][0]["evidence"][0]["start"], 6)
        for finding in result["findings"]:
            for evidence in finding["evidence"]:
                self.assertEqual(text[evidence["start"]:evidence["end"]], evidence["quote"])

    def test_publisher_does_not_change_new_rules(self):
        text = "Только наше правительство принесёт мир. Прежде чем нас критиковать, посмотрите на себя."
        baseline = analyze({"text": text})
        for source in ("RT", "Telegram", "Коммерсантъ", "Неизвестный источник"):
            result = analyze({"text": text, "source": source})
            self.assertEqual(result["findings"], baseline["findings"])
            self.assertEqual(result["document"]["sha256"], baseline["document"]["sha256"])

    def test_new_headline_cue_is_limited_to_title(self):
        phrase = "Прочитайте это пока не удалили"
        self.assertEqual(analyze({"text": phrase})["findings"], [])
        result = analyze({"title": phrase, "text": "Сообщение о публикации документа."})
        self.assertEqual(result["findings"][0]["rule_id"], "clickbait.forbidden_revelation")

    def test_dense_new_cues_are_bounded(self):
        result = analyze({"text": "Нечего тут думать. " * (MAX_FINDINGS + 10)})
        self.assertEqual(len(result["findings"]), MAX_FINDINGS)
        self.assertTrue(result["summary"]["findings_truncated"])

    def test_adversarial_long_prefixes_remain_valid(self):
        prefix = "если мы не " * ((MAX_CHARS - 50) // 11)
        text = prefix + "\nГениальный президент."
        result = analyze({"text": text})
        self.assertEqual(len(result["findings"]), 1)
        evidence = result["findings"][0]["evidence"][0]
        self.assertEqual(text[evidence["start"]:evidence["end"]], "Гениальный президент")


if __name__ == "__main__":
    unittest.main()
