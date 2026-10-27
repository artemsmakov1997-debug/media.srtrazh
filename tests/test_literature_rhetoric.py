"""Literature-derived development regressions, not independent accuracy labels."""

import json
from pathlib import Path
import unittest

from media_strazh.analysis import MAX_FINDINGS, VERSION, analyze
from media_strazh.rating import publication_types


PROBES = json.loads((Path(__file__).resolve().parents[1] /
                    'docs/research/literature-probes-2026-10-27.json').read_text())
TARGETS = {
    'burden_of_proof': 'simplification.burden_of_proof',
    'inaccessible_evidence': 'source.inaccessible_evidence',
    'guilt_pressure': 'emotion.guilt_pressure',
    'loyalty_test': 'generalization.loyalty_test',
    'reciprocity_pressure': 'emotion.reciprocity_pressure',
    'precision_without_method': 'context.percent_basis',
    'relative_without_baseline': 'context.relative_risk_basis',
    'loaded_question_variant': 'simplification.loaded_question',
    'popularity_as_truth': 'generalization.popularity_as_truth',
    'unbounded_promise': 'exaggeration.unbounded_promise',
    'non_superiority_claim': 'exaggeration.unqualified_superiority',
    'join_majority': 'generalization.bandwagon',
    'repeated_slogan': 'context.repeated_thesis',
    'anecdote_to_group': 'generalization.anecdotal_group_inference',
    'commercial_cues': 'context.commercial_call',
    'scientific_veneer': 'authority.scientific_veneer',
    'urgent_call': 'fear.deadline_pressure',
    'false_dilemma_plural_variant': 'simplification.false_dilemma',
}
DOCUMENTS = {row['id']: row['document'] for row in PROBES}
NEW_IDS = set(TARGETS.values())


class LiteratureRhetoricTests(unittest.TestCase):
    def found(self, document, rule_id):
        return [finding for finding in analyze(document)['findings'] if finding['rule_id'] == rule_id]

    def test_all_eighteen_previously_unmarked_development_probes_now_have_the_intended_rule(self):
        for key, target in TARGETS.items():
            with self.subTest(key=key):
                self.assertTrue(self.found(DOCUMENTS[key], target))

    def test_six_plain_news_controls_stay_unmarked(self):
        for row in PROBES:
            if row['group'] == 'negative_control':
                with self.subTest(key=row['id']):
                    self.assertEqual(analyze(row['document'])['findings'], [])

    def test_new_findings_keep_unicode_spans_explanations_and_unit_rating_weight(self):
        for key in TARGETS:
            document = {'title': '📰 Проверочный пример', 'text': '🧭 ' + DOCUMENTS[key]['text']}
            result = analyze(document)
            self.assertEqual(result['algorithm_version'], VERSION)
            self.assertTrue(publication_types(result['findings']))
            for finding in result['findings']:
                self.assertEqual(finding['rating_weight'], 1)
                self.assertTrue(finding['explanation'] and finding['review_question'])
                for evidence in finding['evidence']:
                    self.assertEqual(document[evidence['field']][evidence['start']:evidence['end']], evidence['quote'])
                    sentence = evidence['sentence']
                    self.assertEqual(document[evidence['field']][sentence['start']:sentence['end']], sentence['text'])

    def test_quotes_and_metalinguistic_examples_are_not_reassigned_to_the_editor(self):
        for key, target in TARGETS.items():
            if target.startswith('context.'):
                continue
            phrase = DOCUMENTS[key]['text']
            with self.subTest(key=key):
                direct = self.found({'text': phrase}, target)[0]
                quoted = self.found({'text': 'Депутат заявил: «' + phrase + '»'}, target)[0]
                discussed = self.found({'text': 'Фраза «' + phrase + '»'}, target)[0]
                self.assertEqual(direct['status'], 'needs_review')
                self.assertEqual(quoted['status'], 'quoted_candidate')
                self.assertEqual(discussed['status'], 'context_only')

    def test_denial_of_a_proposition_is_preserved(self):
        phrase = DOCUMENTS['burden_of_proof']['text'].split('. ', 1)[1]
        findings = self.found({'text': 'Нельзя утверждать, что ' + phrase}, TARGETS['burden_of_proof'])
        self.assertEqual(findings[0]['status'], 'context_only')
        self.assertTrue(findings[0]['evidence'][0]['context']['nearby_negation'])

    def test_source_and_url_are_never_detection_features(self):
        for key in ('loyalty_test', 'precision_without_method', 'repeated_slogan'):
            expected = analyze(DOCUMENTS[key])['findings']
            for source in ('RT', 'Медиазона', 'Неизвестный автор'):
                self.assertEqual(analyze({**DOCUMENTS[key], 'source': source,
                                          'url': 'https://example.org/2026/10/27'})['findings'], expected)

    def test_dilemma_pronouns_and_punctuation_variants(self):
        for person in ('ты', 'вы', 'мы', 'они'):
            for separator in (', ', ' — ', ' '):
                for conjunction in ('Либо', 'Или'):
                    text = f'{conjunction} {person} с нами{separator}{conjunction.lower()} {person} против нас.'
                    self.assertTrue(self.found({'text': text}, 'simplification.false_dilemma'), text)
        for text in ('Оплатите картой либо наличными.', 'Либо завтра, либо в пятницу.',
                     'Они с нами обсудили вопрос, а против нас никто не выступал.'):
            self.assertFalse(self.found({'text': text}, 'simplification.false_dilemma'))

    def test_loaded_question_needs_an_accusation_and_question_not_a_normal_schedule(self):
        for text in ('Когда депутат вернёт украденные у города деньги?',
                     'Почему они не перестанут воровать?'):
            self.assertTrue(self.found({'text': text}, 'simplification.loaded_question'))
        for text in ('Когда депутат вернёт документы в архив?',
                     'Когда министр вернёт украденные деньги, их передадут владельцам.'):
            self.assertFalse(self.found({'text': text}, 'simplification.loaded_question'))

    def test_guilt_secrecy_and_gratitude_without_coerced_assent_are_not_the_new_patterns(self):
        controls = (
            'После аварии пострадавший испытывал чувство вины и сильную тревогу.',
            'На вашей совести осталось невыполненное обещание.',
            'Доказательства засекречены. Редакция не может проверить утверждение.',
            'Документы недоступны, поэтому вывод пока делать нельзя.',
            'Документы не засекречены. Поэтому сомневаться нельзя.',
            'Никто не опроверг эти сведения, но они нуждаются в проверке.',
            'Никто не опроверг эти сведения, следовательно, это ещё не доказанная правда.',
            'Если вы откажетесь поддержать эту партию, последствия не будут на вашей совести.',
            'Губернатор столько сделал для города, что жители поблагодарили его.',
            'По договору вы обязаны вернуть полученный аванс.',
        )
        for text in controls:
            with self.subTest(text=text):
                self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS)

    def test_popularity_is_distinct_from_proof_and_from_measured_audience(self):
        for amount in ('200000', '200 000', 'двести тысяч', 'миллионы'):
            self.assertTrue(self.found({'text': f'{amount} репостов, значит, это правда.'},
                                      'generalization.popularity_as_truth'))
        for text in ('Заявление собрало 200 000 репостов за сутки.',
                     'Заявление собрало 200 000 репостов, но это не доказывает его истинность.',
                     '200000 репостов, следовательно, это не правда.'):
            self.assertFalse(self.found({'text': text}, 'generalization.popularity_as_truth'))

    def test_scientific_source_and_bounded_forecast_are_not_vague_approval_or_eternal_guarantee(self):
        for text in ('Методику проверили в рандомизированном исследовании с контрольной группой.',
                     'Врачи обсуждают результаты исследования.',
                     'По прогнозу министерства новый закон может снизить риск кризиса к 2028 году.',
                     'Новый закон гарантированно не избавит страну от кризисов навсегда.',
                     'Гарантированная договором выплата составляет 8% в год.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS)

    def test_numeric_observations_remain_informational_and_count_in_rating(self):
        for key in ('precision_without_method', 'relative_without_baseline'):
            result = analyze(DOCUMENTS[key])
            finding = self.found(DOCUMENTS[key], TARGETS[key])[0]
            self.assertEqual(finding['status'], 'context_only')
            self.assertTrue(finding['evidence'][0]['context']['informational_notice'])
            self.assertFalse(finding['evidence'][0]['context']['truth_checked'])
            self.assertEqual(result['summary']['candidate_fragments'], 0)
            self.assertEqual(result['summary']['marker_fragments'], 1)
            self.assertEqual(publication_types(result['findings']), ['rhetorical_context'])

    def test_survey_basis_anywhere_in_full_input_suppresses_missing_basis_notice(self):
        claim = DOCUMENTS['precision_without_method']['text']
        for basis in ('В опросе участвовали 1200 респондентов.', 'Методика приведена по ссылке.',
                      'По данным опроса института N.', 'Сведения опубликовал ВЦИОМ.'):
            for document in ({'title': claim, 'text': 'Подробности. ' * 200 + basis},
                             {'text': claim + '\n' + 'Подробности. ' * 200 + basis}):
                self.assertFalse(self.found(document, 'context.percent_basis'))
        for text in ('97,3% влаги испарилось.', 'Поддержка составила пять процентов.'):
            self.assertFalse(self.found({'text': text}, 'context.percent_basis'))

    def test_absolute_risk_values_and_explicit_limitations_suppress_relative_notice(self):
        claim = DOCUMENTS['relative_without_baseline']['text']
        for basis in ('Показатель изменился с 1% до 4%.', 'Число случаев выросло с 1 до 4.',
                      'Абсолютный риск указан в таблице.', 'Один случай из 1000.'):
            self.assertFalse(self.found({'text': claim + '\n' + 'Детали. ' * 100 + basis},
                                       'context.relative_risk_basis'))
        self.assertFalse(self.found({'text': 'Цены выросли на 5% за месяц.'}, 'context.relative_risk_basis'))

    def test_commercial_notice_requires_a_call_with_promocode_and_never_asserts_hidden_payment(self):
        finding = self.found(DOCUMENTS['commercial_cues'], 'context.commercial_call')[0]
        self.assertFalse(finding['evidence'][0]['context']['hidden_payment_established'])
        for text in ('В статье обсуждаются промокоды.', 'Запишитесь к участковому врачу.',
                     'Опубликована новость о медицинском центре «XXI век».'):
            self.assertFalse(self.found({'text': text}, 'context.commercial_call'))
        self.assertTrue(self.found({'text': 'Реклама. Купите книгу по промокоду КНИГА.'},
                                   'context.commercial_call'))  # Observable even when disclosed.

    def test_repetition_keeps_three_original_spans_and_requires_distinct_paragraphs(self):
        result = analyze(DOCUMENTS['repeated_slogan'])
        finding = next(f for f in result['findings'] if f['rule_id'] == 'context.repeated_thesis')
        self.assertEqual(len(finding['evidence']), 3)
        self.assertEqual(result['summary']['marker_fragments'], 3)
        self.assertEqual(finding['evidence'][0]['context']['occurrences'], 3)
        self.assertEqual(finding['evidence'][0]['context']['distinct_paragraphs'], 3)
        text = DOCUMENTS['repeated_slogan']['text'].replace('вернёт', 'вернет', 1)
        self.assertTrue(self.found({'text': text}, 'context.repeated_thesis'))
        phrase = 'Новый закон вернёт нам спокойствие.'
        for document in ({'text': ' '.join([phrase] * 3)},
                         {'title': phrase, 'text': phrase + '\n' + phrase},
                         {'text': 'У пациента болит голова.\n' * 3},
                         {'title': 'Разбор повторения', 'text': '\n'.join([phrase] * 3)},
                         {'text': 'В романе герой говорит:\n' + '\n'.join([phrase] * 3)}):
            self.assertFalse(self.found(document, 'context.repeated_thesis'))

    def test_deadline_and_anecdote_need_the_whole_relation_not_isolated_cue_words(self):
        for text in ('Приём заявлений завершится сегодня в 18:00.',
                     'Срочно эвакуируйтесь: по прогнозу метеослужбы приближается ураган.',
                     'Один чиновник опоздал на встречу. Другие прибыли вовремя.',
                     'Этот случай доказывает вину конкретного обвиняемого.',
                     'Ни одна партия не получила больше 50% голосов.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS)

    def test_new_structural_observations_obey_the_global_result_budget(self):
        result = analyze({'text': '97,3% жителей поддержали решение.\n' * 600})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])


if __name__ == '__main__':
    unittest.main()
