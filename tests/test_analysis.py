import unittest

from media_strazh.analysis import MAX_CHARS, MAX_FINDINGS, SUPPORTED, analyze
from media_strazh.evaluation import evaluate


class AnalysisTests(unittest.TestCase):
    def test_neutral_article(self):
        result = analyze({"title": "Минфин опубликовал отчёт", "text": "Доходы бюджета выросли на 3%. В отчёте указаны период и методика расчёта."})
        self.assertEqual(result["findings"], [])
        self.assertNotIn("score", result)

    def test_emotion_is_candidate_with_exact_span(self):
        text = "Власти приняли возмутительное решение."
        result = analyze({"text": text})
        finding = result["findings"][0]
        evidence = finding["evidence"][0]
        self.assertEqual(finding["category"], "emotional_evaluation")
        self.assertEqual(finding["status"], "needs_review")
        self.assertEqual(text[evidence["start"]:evidence["end"]], "возмутительное")
        self.assertEqual(evidence["quote"], "возмутительное")

    def test_specific_risk_is_not_automatically_fear(self):
        self.assertEqual(analyze({"text": "МЧС предупредило об угрозе пожара и рекомендовало эвакуацию."})["findings"], [])

    def test_inevitability_and_generalization(self):
        result = analyze({"text": "Все знают: нас ждёт неминуемая катастрофа."})
        self.assertEqual(set(result["summary"]["by_category"]), {"fear", "generalization"})

    def test_quote_is_not_author_assertion(self):
        result = analyze({"text": 'Депутат сказал: «Это позорное решение». Редакция описала результаты голосования.'})
        self.assertEqual(result["summary"]["review_candidates"], 0)
        self.assertEqual(result["summary"]["quoted_candidates"], 1)

    def test_nested_and_ascii_quotes(self):
        for text in ('Он сказал: «Это “позорное” решение».', 'Он сказал: "Позорное решение".'):
            with self.subTest(text=text):
                self.assertEqual(analyze({"text": text})["findings"][0]["status"], "quoted_candidate")

    def test_unclosed_quote_is_marked_cautiously(self):
        self.assertEqual(analyze({"text": "Депутат сказал: «Позорное решение"})["findings"][0]["status"], "quoted_candidate")

    def test_negation(self):
        result = analyze({"text": "Не все знают о решении. Это не позорное решение."})
        self.assertEqual(result["summary"]["review_candidates"], 0)
        self.assertEqual(result["summary"]["context_only"], 2)

    def test_negation_does_not_cross_comma(self):
        result = analyze({"text": "Не согласен, все знают о решении."})
        self.assertEqual(result["findings"][0]["status"], "needs_review")

    def test_not_only_is_not_negation(self):
        self.assertEqual(analyze({"text": "Это не только позорное решение."})["findings"][0]["status"], "needs_review")

    def test_metalinguistic_context(self):
        result = analyze({"text": "Выражение все знают следует проверять по контексту."})
        self.assertEqual(result["findings"][0]["status"], "context_only")

    def test_named_expert_not_flagged_merely_for_expertise(self):
        self.assertEqual(analyze({"text": "Экономист Иван Петров из университета объяснил методику расчёта."})["findings"], [])

    def test_vague_source_remains_review_candidate(self):
        result = analyze({"text": "Эксперты считают, что решение изменит рынок. Их имена приведены ниже."})
        self.assertEqual(result["findings"][0]["category"], "vague_source")
        self.assertIn("остальном материале", result["findings"][0]["review_question"])

    def test_headline_gap_has_two_evidence_fields(self):
        result = analyze({"title": "Учёные доказали влияние продукта", "text": "Авторы обнаружили возможную связь на небольшой выборке."})
        finding = result["findings"][0]
        self.assertEqual(finding["rule_id"], "headline.certainty_gap")
        self.assertEqual([e["field"] for e in finding["evidence"]], ["title", "text"])

    def test_headline_certainty_alone_is_not_gap(self):
        self.assertEqual(analyze({"title": "Учёные доказали теорему", "text": "Доказательство опубликовано в журнале."})["findings"], [])

    def test_quoted_caveat_does_not_create_gap(self):
        result = analyze({"title": "Учёные доказали влияние продукта", "text": "Фраза «возможная связь» была удалена из итогового отчёта."})
        self.assertEqual(result["findings"], [])

    def test_unicode_offsets_and_original_text_preserved(self):
        text = "😀\r\nПозорное решение — так его назвал участник."
        result = analyze({"text": text})
        evidence = result["findings"][0]["evidence"][0]
        self.assertEqual(result["document"]["text"], text)
        self.assertEqual(evidence["start"], 3)
        self.assertEqual(text[evidence["start"]:evidence["end"]], evidence["quote"])

    def test_title_and_text_offsets_are_independent(self):
        result = analyze({"title": "Позорное решение", "text": "Весь народ поддерживает изменения."})
        for finding in result["findings"]:
            for evidence in finding["evidence"]:
                field = result["document"][evidence["field"]]
                self.assertEqual(field[evidence["start"]:evidence["end"]], evidence["quote"])

    def test_version_hash_and_result_are_repeatable(self):
        article = {"text": "Все знают о решении.", "source": "Источник А"}
        first = analyze(article)
        self.assertEqual(first, analyze(article))
        # Publisher identity must not influence analysis or text hash.
        other = analyze({**article, "source": "Источник Б"})
        self.assertEqual(first["findings"], other["findings"])
        self.assertEqual(first["document"]["sha256"], other["document"]["sha256"])
        self.assertNotEqual(first["document"]["sha256"], analyze({"text": article["text"] + "!"})["document"]["sha256"])

    def test_unsupported_categories_are_explicit(self):
        coverage = {c["id"]: c["coverage"] for c in analyze({"text": "Нейтральный текст."})["coverage"]}
        self.assertEqual(len(coverage), 12)
        self.assertEqual(coverage["selective_context"], "not_evaluated")

    def test_dense_text_has_bounded_results_and_context(self):
        result = analyze({"text": "Все знают " * (MAX_FINDINGS + 10)})
        self.assertEqual(len(result["findings"]), MAX_FINDINGS)
        self.assertTrue(result["summary"]["findings_truncated"])
        for finding in result["findings"]:
            self.assertLess(len(finding["evidence"][0]["sentence"]["text"]), 500)

    def test_exactly_at_finding_limit_is_not_incomplete(self):
        result = analyze({"text": "Все знают. " * MAX_FINDINGS})
        self.assertFalse(result["summary"]["findings_truncated"])

    def test_validation(self):
        for invalid in (None, [], {}, {"text": " "}, {"text": 2}, {"text": "Текст", "url": None}, {"text": "Текст", "score": 75}, {"text": "я" * (MAX_CHARS + 1)}):
            with self.subTest(document_type=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    analyze(invalid)


class EvaluationTests(unittest.TestCase):
    def test_counts_include_false_positives_and_negatives(self):
        rows = [
            {"id": "a", "fully_annotated": True, "document": {"text": "Позорное решение."}, "labels": ["emotional_evaluation"]},
            {"id": "b", "fully_annotated": True, "document": {"text": "Позорное решение."}, "labels": []},
            {"id": "c", "fully_annotated": True, "document": {"text": "Безоценочное решение."}, "labels": ["emotional_evaluation"]},
        ]
        for row in rows:
            row["annotation_categories"] = sorted(SUPPORTED)
        score = evaluate(rows)["categories"]["emotional_evaluation"]
        self.assertEqual((score["tp"], score["fp"], score["fn"]), (1, 1, 1))
        self.assertEqual(score["precision"], .5)
        self.assertEqual(score["recall"], .5)

    def test_absent_category_is_not_reported_as_perfect(self):
        result = evaluate([{"id": "a", "fully_annotated": True, "annotation_categories": sorted(SUPPORTED), "document": {"text": "Объявлено решение."}, "labels": []}])
        self.assertIsNone(result["categories"]["fear"]["f1"])

    def test_invalid_corpora(self):
        row = {"id": "a", "fully_annotated": True, "annotation_categories": sorted(SUPPORTED), "document": {"text": "Текст статьи."}, "labels": []}
        for rows in ([], [row, row], [{**row, "fully_annotated": False}], [{**row, "labels": ["selective_context"]}], [{**row, "labels": "fear"}]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    evaluate(rows)

    def test_old_five_category_annotation_cannot_be_used_for_nine_categories(self):
        row = {"id": "a", "fully_annotated": True, "document": {"text": "Текст статьи."}, "labels": []}
        for categories in (None, ["fear", "emotional_evaluation", "generalization", "vague_source", "clickbait"]):
            with self.subTest(categories=categories):
                candidate = dict(row)
                if categories is not None:
                    candidate["annotation_categories"] = categories
                with self.assertRaisesRegex(ValueError, "annotation_categories"):
                    evaluate([candidate])

    def test_new_supported_categories_are_evaluated(self):
        row = {"id": "a", "fully_annotated": True, "annotation_categories": sorted(SUPPORTED),
               "document": {"text": "Политик — марионетка. Война как единственный выход."},
               "labels": ["enemy_image", "oversimplification"]}
        result = evaluate([row])
        self.assertEqual(result["categories"]["enemy_image"]["tp"], 1)
        self.assertEqual(result["categories"]["oversimplification"]["tp"], 1)


if __name__ == "__main__":
    unittest.main()
