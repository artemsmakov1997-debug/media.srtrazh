"""Morphological lexicon (rules-0.18.0): forms, combinations, scope and guards."""

import re
import unittest

from media_strazh.analysis import COMPILED_RULES, analyze
from media_strazh.lexicon import CLASSES, GROUPS, LEXICON_RULES, form, inventory
from media_strazh.rating import publication_types


def lexicon_hits(text, title=""):
    return [(f["rule_id"], f["evidence"][0]["quote"]) for f in analyze({"title": title, "text": text})["findings"]
            if f["rule_id"].startswith("lex.")]


def flagged(text, title=""):
    return bool(publication_types(analyze({"title": title, "text": text})["findings"]))


class MorphologyTests(unittest.TestCase):
    def test_every_class_compiles_and_matches_its_paradigm(self):
        paradigms = {
            ("враг", "m"): "враг врага врагу врагом враге враги врагов врагам врагами врагах",
            ("карател", "m_soft"): "каратель карателя карателю карателем карателе каратели карателей карателям карателями карателях",
            ("бандеров", "m_ets"): "бандеровец бандеровца бандеровцу бандеровцем бандеровце бандеровцы бандеровцев бандеровцам бандеровцами бандеровцах",
            ("вырод", "m_ok"): "выродок выродка выродку выродком выродке выродки выродков выродкам выродками выродках",
            ("хунт", "f"): "хунта хунты хунте хунту хунтой хунтою хунтам хунтами хунтах",
            ("русн", "f_ya"): "русня русни русне русню русней",
            ("мраз", "f_soft"): "мразь мрази мразью мразей мразям мразями мразях",
            ("пыточн", "adj"): "пыточная пыточной пыточную пыточные пыточных пыточными пыточного пыточном",
        }
        for (stem, cls), forms in paradigms.items():
            pattern = re.compile(r"^" + form(stem, cls) + r"$", re.I)
            for word in forms.split():
                with self.subTest(word=word):
                    self.assertRegex(word, pattern)
        self.assertEqual(set(CLASSES) - {cls for _, cls in paradigms}, {"n"})

    def test_yo_and_hyphen_variants(self):
        for text in ("Живодёры из ВСУ снова обстреляли Донецк.", "Живодеры из ВСУ снова обстреляли Донецк.",
                     "Укронацисты обстреляли школу.", "Укро-нацисты обстреляли школу.",
                     "Укро нацисты обстреляли школу.", "Русофашисты нанесли удар по Одессе."):
            with self.subTest(text=text):
                self.assertTrue(lexicon_hits(text))

    def test_case_forms_of_user_examples_are_found(self):
        cases = (
            "Мы не отдадим землю врагу, заявил губернатор.",
            "О врагах России говорили на заседании Госдумы.",
            "Депутат назвал президента убийцей.",
            "Задержанного избивали силовые структуры.",
            "Его допрашивали в пыточной СБУ.",
            "Активиста отправили в застенки ФСБ.",
            "Карателями назвали бойцов батальона на Донбассе.",
            "Протест против киевской хунты прошёл в Москве.",
            "Командир рассказал о бандеровцах под Курском.",
            "Обращение к рашистам опубликовал Киев.",
            "Удар по оркам нанесли ВСУ.",
            "Решение кровавого киевского режима осудили в Москве.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(flagged(text), analyze({"text": text})["findings"])


class CombinationTests(unittest.TestCase):
    def test_modifier_head_matrix_and_genitive_labels(self):
        for text, quote in (("Кровавый режим продолжает террор.", "Кровавый режим"),
                            ("Преступная хунта опять лжёт.", "Преступная хунта"),
                            ("Людоедская власть ввела новые запреты.", "Людоедская власть"),
                            ("Это режим убийц и воров.", "режим убийц"),
                            ("Банда террористов захватила город.", "Банда террористов")):
            with self.subTest(text=text):
                self.assertIn(quote, [q for _, q in lexicon_hits(text)])

    def test_country_labels_and_leader_regime(self):
        self.assertTrue(lexicon_hits("Страна-террорист снова атаковала порт."))
        self.assertTrue(lexicon_hits("Государство-изгой отвергло переговоры."))
        self.assertTrue(lexicon_hits("Режим Зеленского ввёл новые санкции."))
        self.assertTrue(lexicon_hits("Режим Путина ввёл новые ограничения."))


class SymmetryTests(unittest.TestCase):
    def test_labels_of_both_sides_are_detected(self):
        pairs = (("Рашисты обстреляли Харьков.", "Укронацисты обстреляли Донецк."),
                 ("Орки снова наступают у Бахмута.", "Бандеровцы снова наступают у Курска."),
                 ("Кацапы опять угрожают.", "Хохлы опять угрожают."),
                 ("Москали атакуют Одессу.", "Укропы атакуют Белгород."))
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertTrue(flagged(left))
                self.assertTrue(flagged(right))


class OtherCategoryTests(unittest.TestCase):
    def test_new_category_examples(self):
        for text, category in (
            ("Все мигранты нарушают закон, заявил депутат.", "generalization"),
            ("В доме на Ленина произошёл хлопок газа.", "euphemism_dysphemism"),
            ("Компании объявили об оптимизации штата.", "euphemism_dysphemism"),
            ("Войска совершили жест доброй воли под Херсоном.", "euphemism_dysphemism"),
            ("Как сообщил источник, знакомый с ситуацией, сделка сорвётся.", "vague_source"),
            ("Британские учёные доказали, что это вредно.", "appeal_to_authority"),
            ("Во всём виноват Запад, считает политолог.", "oversimplification"),
            ("Политик пригрозил превратить Европу в радиоактивный пепел.", "fear"),
            ("Это беспрецедентное давление на Россию.", "exaggeration"),
            ("Людоедские законы Кремля обсудили в Брюсселе.", "emotional_evaluation"),
        ):
            with self.subTest(text=text):
                categories = {f["category"] for f in analyze({"text": text})["findings"]}
                self.assertIn(category, categories)

    def test_clickbait_is_title_only(self):
        self.assertTrue(lexicon_hits("Подробности в материале.", title="ШОК! Вы не поверите, что скрывают власти"))
        self.assertFalse(lexicon_hits("Вся правда о налогах изложена в отчёте."))


class ScopeAndGuardTests(unittest.TestCase):
    NEUTRAL = (
        "В Москве в субботу ожидается до +5 градусов и небольшой дождь.",
        "Косатка (орка) выпрыгнула из воды у берегов Камчатки.",
        "В новом фильме по Толкину орки штурмуют крепость.",
        "Добавьте укроп и петрушку в салат.",
        "В 1943 году нацисты сожгли деревню, напомнил историк.",
        "Главный враг здоровья — сахар, считают диетологи.",
        "Хлопок подорожал на мировых рынках.",
        "В зоопарке звери получили новые вольеры.",
        "Сборная выиграла матч со счётом 3:1.",
        "Убийца задержан полицией в Подмосковье.",
        "Суд приговорил убийцу к 15 годам.",
        "ФСБ задержала террориста в Ставрополе.",
        "Силовые тренировки полезны для сердца.",
        "Учёные доказали теорему Ферма.",
        "Биомасса на заводе используется как топливо.",
        "Историк описал нацистский режим в Германии в 1939 году.",
        "Мясорубку и фарш купили для кухни.",
        "Начинающим кликать по ссылке не нужно.",
        # lexicon-1.1: false positives found in the corpus report (2026-11-06)
        "** Лицо, признанное экстремистом и террористом на территории РФ",
        "* — внесен в перечень террористов и экстремистов Росфинмониторинга",
        "Верховный суд сослался на преступления членов общины по террористическим статьям.",
        "Удар был направлен против террористических целей, говорится в пресс-релизе.",
        "Экспозиция расположена в «Доме Раши».",
        "По данным издания «Агентство», из США выслали россиянина.",
        "Компании обязаны предоставлять эти сведения уполномоченным органам.",
        "Партии призвали к демонстрации против расизма, фашизма и империализма.",
        "Главным фаворитом аналитики единодушно называют Кейна.",
        "В дилогии писательницы царит тотальный холод.",
        "«Мы просим Конгресс остановить это варварское злоупотребление властью».",
        "Сёстры слышат крики друг друга во время пыток, рассказали правозащитники.",
        "Главарь банды задержан в Подмосковье.",
        "Замочите фасоль на ночь.",
        "Из России тоже можно, в два клика.",
        "«Каратель» от Netflix был одной из лучших экранизаций комиксов.",
        "Убийца скрылся, следствие по уголовному делу приостановлено, сообщил губернатор.",
    )

    def test_literal_and_neutral_texts_are_not_flagged_by_lexicon(self):
        for text in self.NEUTRAL:
            with self.subTest(text=text):
                self.assertEqual(lexicon_hits(text), [])

    def test_quotation_and_negation_keep_engine_statuses(self):
        quoted = analyze({"text": "«Киевская хунта лжёт», — заявил депутат."})["findings"]
        self.assertEqual([f["status"] for f in quoted if f["rule_id"].startswith("lex.")], ["quoted_candidate"])
        discussed = analyze({"text": "Слово «рашисты» лингвисты относят к ярлыкам."})["findings"]
        self.assertEqual([f["status"] for f in discussed if f["rule_id"].startswith("lex.")], ["context_only"])

    def test_lexicon_does_not_relabel_fragment_of_older_rule(self):
        findings = analyze({"text": "Путин — убийца."})["findings"]
        self.assertEqual([f["rule_id"] for f in findings], ["dysphemism.murderer_label"])

    def test_lexicon_marks_never_overlap_existing_marks(self):
        # The interface cannot draw nested highlights (browser check, person labels).
        for text in ("Путин — клоун, кровавый диктатор и убийца.", "Кровавый режим продолжает террор.",
                     "Людоедская власть ввела новые запреты.", "Путин продолжает кровавую расправу с украинцами."):
            with self.subTest(text=text):
                spans = sorted((e["start"], e["end"]) for f in analyze({"text": text})["findings"]
                               if f["rule_id"].startswith("lex.") for e in f["evidence"])
                others = [(e["start"], e["end"]) for f in analyze({"text": text})["findings"]
                          for e in f["evidence"]]
                for start, end in spans:
                    overlapping = [span for span in others if span[0] < end and start < span[1]]
                    self.assertEqual(overlapping, [(start, end)])


class CorpusCandidateTests(unittest.TestCase):
    def test_words_added_from_corpus_report(self):
        for text, quote in (("Термин русофобия стал частью риторики Кремля.", "русофобия"),
                            ("В этот раз главарь киевского режима перегнул палку.", "главарь"),
                            ("Путин продолжает кровавую расправу с украинцами.", "кровавую расправу"),
                            ("«Жалкая стайка бумажных тигров»: европейцы утешают Зеленского.", "бумажных тигров"),
                            ("Укровские вояки бегут из Курской области.", "Укровские"),
                            ("Будем мочить их в сортире, заявил президент.", "мочить их"),
                            ("Охранота в Госдуме снова требует запретов.", "Охранота"),
                            ("Правящая клика в Киеве снова лжёт.", "Правящая клика")):
            with self.subTest(text=text):
                self.assertIn(quote, [q for _, q in lexicon_hits(text)])


class RegistryTests(unittest.TestCase):
    def test_groups_are_registered_after_handwritten_rules(self):
        ids = [rule.id for rule, _ in COMPILED_RULES]
        self.assertEqual(ids[-len(LEXICON_RULES):], [rule.id for rule in LEXICON_RULES])
        self.assertEqual(len({group.id for group in GROUPS}), len(GROUPS))
        supported = {"fear", "emotional_evaluation", "enemy_image", "exaggeration", "generalization",
                     "appeal_to_authority", "vague_source", "oversimplification", "clickbait", "euphemism_dysphemism"}
        self.assertEqual({item["category"] for item in inventory()}, supported)
        for group in GROUPS:
            with self.subTest(group=group.id):
                re.compile(group.pattern, re.I)
                self.assertIn(group.scope, {"any", "public"})
                self.assertTrue(group.explanation and group.question and group.label)


if __name__ == "__main__":
    unittest.main()
