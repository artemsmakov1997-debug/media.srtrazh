"""Development cases from public posts and argumentation definitions, not gold labels."""

import unittest

from media_strazh.analysis import analyze
from media_strazh.rules import RULES


POSITIVE_CASES = {
    "fear.alarmist_metaphor": "Ад на пороге: в городе ожидают тяжёлую зиму.",
    "emotion.violent_public_metaphor": "Летающий морг готовят на Украине.",
    "emotion.collective_panic": "Жители Киева в панике бегут из города.",
    "fear.total_destruction_metaphor": "Город Украины сотрут с лица земли, заявил политик.",
    "generalization.exclusive_collective_blame": "Трамп назвал Сомали худшей страной: «Не работают, а только воруют».",
    "clickbait.reader_teaser": "Как работает дежавю — вы удивитесь.",
    "enemy.derisive_communication": "Зеленский выступил с заявлением. Кто-то, кажется, догавкался.",
    "dysphemism.derogatory_group": "В Европе это стало кошмаром для заукраинцев.",
    "dysphemism.expired_politician": "Президент обсудил действия Просроченного.",
    "emotion.corruption_metaphor": "Украина погрязла в коррупции.",
    "emotion.ominous_date": "До зловещей даты остался ровно месяц.",
    "emotion.derisive_emoji": "🤡Министр объявил решение правительства.",
    "fear.frontloaded_disaster": "Президент отверг предложение. Впереди — катастрофа.",
    "generalization.group_mental_state": "Немецкая молодежь не верит государству.",
    "source.unnamed_media": "СМИ сообщают о введении новых ограничений.",
    "simplification.claimed_mind_reading": "Президент выступил. На самом деле он прекрасно понимает, что такое национальный эгоизм.",
    "enemy.personal_attack_as_argument": "Он идиот, поэтому он неправ.",
    "simplification.loaded_question": "Когда вы перестанете лгать народу?",
}


class LatestMediaRhetoricTests(unittest.TestCase):
    def matching(self, text, rule_id):
        return [f for f in analyze({"text": text})["findings"] if f["rule_id"] == rule_id]

    def test_added_rules_have_exact_unicode_evidence_in_both_fields(self):
        ids = {rule.id for rule in RULES}
        for rule_id, text in POSITIVE_CASES.items():
            self.assertIn(rule_id, ids)
            for field in ("title", "text"):
                with self.subTest(rule_id=rule_id, field=field):
                    value = "📰 " + text
                    result = analyze({"text": "Опубликован материал.", field: value})
                    found = [f for f in result["findings"] if f["rule_id"] == rule_id]
                    self.assertEqual(len(found), 1)
                    for evidence in found[0]["evidence"]:
                        self.assertEqual((evidence["field"], value[evidence["start"]:evidence["end"]]),
                                         (field, evidence["quote"]))

    def test_real_development_excerpts_cover_missed_forms(self):
        examples = [
            # https://t.me/inosmichannel/32784
            ("Зеленский заявил о разведданных. Кто-то, кажется, догавкался.", "enemy.derisive_communication", "догавкался"),
            # https://t.me/inosmichannel/32786
            ("Истеричная реакция главы киевского режима напугала европейцев, пишет Financial Times.", "enemy.political_madness", "Истеричная"),
            # https://t.me/inosmichannel/32771
            ("Лидеры европейских стран представляют собой жалкую стайку бумажных тигров.", "enemy.dehumanization", "стайку"),
            # https://t.me/inosmichannel/32777
            ("Зеленский отверг ультиматум Трампа. Впереди — катастрофа.", "fear.frontloaded_disaster", "Впереди — катастрофа"),
            # https://t.me/aifonline/200975
            ("До зловещей даты остался ровно месяц.", "emotion.ominous_date", "зловещей даты"),
        ]
        for text, rule_id, quote in examples:
            with self.subTest(rule_id=rule_id):
                found = self.matching(text, rule_id)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["evidence"][0]["quote"], quote)

    def test_literal_animals_and_technical_expiry_do_not_become_labels(self):
        texts = [
            "Президент посетил приют: собаки гавкают, а кошки отдыхают.",
            "Министр посетил зоопарк. Стая птиц перелетела к озеру.",
            "Мэр сообщил: волки воют по ночам в лесу.",
            "Врач объяснил причины истеричной реакции пациента.",
            "В парламенте показали фильм «Зловещая дата».",
            "Президент посетил цирк 🤡.",
            "Чиновник заменил просроченный паспорт.",
            "Правительство выявило просроченные лекарства.",
            "У депутата просроченный мандат на представительство организации.",
            "Министр обсудил просроченную задолженность по кредитам.",
            "Президент объявил дату переговоров и опубликовал документы.",
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"], [])

    def test_group_quantifiers_and_named_sources_remain_distinct(self):
        for prefix in ("Часть", "Большинство", "Меньшинство", "Некоторые", "Многие", "40%", "40 процентов"):
            text = prefix + " европейцы не верят правительству."
            self.assertEqual(self.matching(text, "generalization.group_mental_state"), [])
        for text in ("РБК сообщает о введении ограничений.", "По данным ФСБ, предотвращена атака.",
                     "Русофобия исследуется в работе по социальной психологии."):
            self.assertEqual(analyze({"text": text})["findings"], [])

    def test_present_tense_and_terminal_attribution_keep_reported_speech(self):
        for text in ("Истеричная реакция президента напугала европейцев, пишет Financial Times.",
                     "Как пишет газета, президент погряз в коррупции.",
                     "Немецкая молодежь не верит государству, признал Мерц."):
            with self.subTest(text=text):
                result = analyze({"text": text})
                self.assertTrue(result["findings"])
                self.assertTrue(all(f["status"] == "quoted_candidate" for f in result["findings"]))
        text = "Это возмутительное решение, но президент сообщает дату заседания."
        self.assertEqual(analyze({"text": text})["findings"][0]["status"], "needs_review")

    def test_quotes_discussion_and_negation_do_not_establish_author_intent(self):
        for text, rule_id, status in (
            ("Министр сказал: «Когда вы перестанете лгать?»", "simplification.loaded_question", "quoted_candidate"),
            ("Политики не гавкают, они обсуждают решение.", "enemy.derisive_communication", "context_only"),
            ("Эмодзи «🤡» используется в политическом обсуждении.", "emotion.derisive_emoji", "context_only"),
            ("Фраза «Впереди — катастрофа» обсуждается в парламенте.", "fear.frontloaded_disaster", "context_only"),
        ):
            with self.subTest(text=text):
                self.assertEqual(self.matching(text, rule_id)[0]["status"], status)

    def test_publisher_is_not_a_feature(self):
        text = "🤡Президент закатил истерику. Впереди — катастрофа."
        expected = analyze({"text": text})["findings"]
        for source in ("Аргументы и факты", "ИноСМИ", "СМОТРИ", "BBC", "RT"):
            self.assertEqual(analyze({"text": text, "source": source})["findings"], expected)

    def test_oct27_real_headlines_and_exact_phrases(self):
        # Development excerpts from the existing public analysis snapshot;
        # these are regression cases, not an independent accuracy benchmark.
        cases = [
            ("Ад на пороге: жители Киева в панике бегут из города в ожидании тяжелейшей зимы",
             "fear.alarmist_metaphor", "Ад на пороге"),  # t.me/inosmichannel/33000
            ("Маск пошел против Киева: скандал со Starlink выбьет последний дух из ВСУ",
             "emotion.violent_public_metaphor", "выбьет последний дух"),
            ("Летающий морг готовят на Украине: элиту из Британии вырежут «Кинжалом»",
             "emotion.violent_public_metaphor", "Летающий морг"),  # t.me/aifonline/201748
            ("Сбой памяти или знак судьбы? Как на самом деле работает дежавю — вы удивитесь",
             "clickbait.reader_teaser", "вы удивитесь"),  # fontanka.ru/2026/10/25/76722264/
            ("Рынок обвалился после провального решения.", "emotion.loaded_word", "провального"),
        ]
        for text, rule, quote in cases:
            with self.subTest(rule=rule):
                finding = self.matching(text, rule)[0]
                self.assertEqual(finding['evidence'][0]['quote'], quote)
                self.assertEqual(finding['status'], 'needs_review')

    def test_new_cues_preserve_quotes_discussion_and_literal_emotions(self):
        for rule, text in (
            ("fear.alarmist_metaphor", "Министр сказал: «Ад на пороге».") ,
            ("emotion.violent_public_metaphor", "Автор написал: «Летающий морг готовят на Украине».") ,
        ):
            self.assertEqual(self.matching(text, rule)[0]['status'], 'quoted_candidate')
        for text in (
            'В кинотеатре показали фильм «Ад на пороге».',
            'Роман «Летающий морг» поступил в продажу.',
            'Врач рассказал, что у школьницы началась истерика.',
            'Девочка была в панике после разговора с сотрудниками.',
            'Житель Киева был в панике после разговора с сотрудниками.',
            'Житель в панике выбежал из квартиры.',
            'Клопы и другие насекомые поселились в номере.',
            'Водители не работают, а только воруют — сцена из комедии.',
            'Статья описывает результаты исследования памяти.',
        ):
            findings = analyze({'text': text})['findings']
            new_rules = {'fear.alarmist_metaphor', 'emotion.violent_public_metaphor',
                         'emotion.collective_panic', 'fear.total_destruction_metaphor',
                         'generalization.exclusive_collective_blame', 'clickbait.reader_teaser'}
            self.assertFalse(any(f['rule_id'] in new_rules for f in findings), text)

    def test_reader_teaser_is_bounded_to_title_or_opening(self):
        self.assertEqual(self.matching('Подробности события. ' * 20 + 'Вы удивитесь.', 'clickbait.reader_teaser'), [])
        self.assertTrue(self.matching('Вы не поверите: раскрыты новые подробности.', 'clickbait.reader_teaser'))


if __name__ == "__main__":
    unittest.main()
