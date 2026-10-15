import unittest

from media_strazh.analysis import analyze


class OctoberRhetoricTests(unittest.TestCase):
    def test_silovik_is_an_informational_noun_not_an_automatic_insult(self):
        for word in ("Силовик", "силовики", "силовика", "силовиков", "силовикам", "силовиками"):
            with self.subTest(word=word):
                result = analyze({"text": word + " провёл задержание."})
                found = result["findings"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["rule_id"], "terminology.law_enforcement_actor")
                self.assertEqual(found[0]["status"], "context_only")
                self.assertEqual(result["summary"]["candidate_fragments"], 0)
        self.assertEqual(analyze({"text": "Провели силовой эксперимент."})["findings"], [])

    def test_unnamed_official_is_a_source_only_when_supplying_information(self):
        cases = (
            "Один из европейских чиновников сообщил о решении.",
            "По словам одного из высокопоставленных европейских чиновников, решение принято.",
            "Анонимный европейский чиновник заявил о переговорах.",
            "Издание сообщило об этом, сославшись на одного из европейских чиновников.",
            "Решение принято, сообщил один из европейских чиновников.",
            "Один из европейских чиновников: «Решение принято».",
        )
        for field in ("text", "title"):
            for text in cases:
                with self.subTest(field=field, text=text):
                    value = "📰 " + text
                    result = analyze({"text": "Опубликован материал.", field: value})
                    f = next(f for f in result["findings"] if f["rule_id"] == "source.unnamed_official")
                    e = f["evidence"][0]
                    self.assertEqual(value[e["start"]:e["end"]], e["quote"])
        for text in (
            "Один из европейских чиновников, Иван Петров, сообщил о решении.",
            "Иван Петров, один из европейских чиновников, сообщил о решении.",
            "John Smith, один из европейских чиновников, сообщил о решении.",
            "Один из европейских чиновников попал в больницу.",
        ):
            self.assertFalse(any(f["rule_id"] == "source.unnamed_official" for f in analyze({"text": text})["findings"]))

    def test_regime_phrase_handles_the_reported_typo_and_cases(self):
        for text in ("Неонацисткий режим объявил решение.", "Неонацистский режим объявил решение.",
                     "Представители неонацистского режима сделали заявление."):
            found = analyze({"text": text})["findings"]
            self.assertTrue(any(f["rule_id"] == "dysphemism.neo_nazi_regime" for f in found))
        for text in ("В 1941 году историк описал неонацистский режим.",
                     "Архив описывает неонацистский режим прошлого.",
                     "В романе показан неонацистский режим."):
            self.assertFalse(any(f["rule_id"] == "dysphemism.neo_nazi_regime" for f in analyze({"text": text})["findings"]))
        result = analyze({"text": "Автор заявил: «Неонацисткий режим принял решение»."})
        self.assertTrue(all(f["status"] == "quoted_candidate" for f in result["findings"]))


if __name__ == "__main__":
    unittest.main()
