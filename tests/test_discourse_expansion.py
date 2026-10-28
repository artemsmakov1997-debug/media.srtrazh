"""Bounded argument structures from literature; development regressions, not accuracy."""

import json
import unittest

from media_strazh.analysis import MAX_FINDINGS, VERSION, analyze
from media_strazh.rules import RULES


DOCUMENTS = {
    'question_deflection': {'text': 'Неважно, куда ушли бюджетные деньги. Главное — наша великая история.'},
    'topic_displacement': {'text': 'Почему выросли цены? — Зато у нашей страны великая история.'},
    'consequence_chain': {'text': 'Разрешим митинг — начнутся беспорядки — страна развалится.'},
    'circular_justification': {'text': 'Это правда, потому что это истина.'},
    'absence_as_concealment': {'text': 'Доказательств нет, значит их скрывают.'},
    'unspecified_measures': {'text': 'Губернатор сообщил, что будут приняты необходимые меры.'},
    'unattributed_decision': {'text': 'Было принято решение о повышении тарифов.'},
}
TARGETS = {key: ('context.' if key in {'unspecified_measures', 'unattributed_decision'} else 'simplification.') +
           ('question_deflection' if key == 'topic_displacement' else key) for key in DOCUMENTS}
NEW_IDS = set(TARGETS.values())


class DiscourseExpansionTests(unittest.TestCase):
    def found(self, text, rule):
        return [f for f in analyze({'text': text})['findings'] if f['rule_id'] == rule]

    def test_all_seven_development_examples_have_the_intended_six_methods(self):
        self.assertEqual(len(NEW_IDS), 6)
        self.assertTrue(NEW_IDS <= {rule.id for rule in RULES})
        for key, document in DOCUMENTS.items():
            with self.subTest(key=key):
                self.assertTrue(self.found(document['text'], TARGETS[key]))

    def test_exact_original_unicode_offsets_and_explanations_in_both_fields(self):
        for key, original in DOCUMENTS.items():
            for field in ('text', 'title'):
                document = {'text': 'Опубликован материал.', field: '🧭 ' + original['text']}
                result = analyze(document)
                hits = [f for f in result['findings'] if f['rule_id'] == TARGETS[key]]
                self.assertEqual(len(hits), 1, (key, field))
                self.assertEqual(result['algorithm_version'], VERSION)
                for finding in hits:
                    self.assertEqual(finding['rating_weight'], 1)
                    self.assertTrue(finding['explanation'] and finding['review_question'])
                    for evidence in finding['evidence']:
                        self.assertEqual(document[field][evidence['start']:evidence['end']], evidence['quote'])
                        s = evidence['sentence']
                        self.assertEqual(document[field][s['start']:s['end']], s['text'])
                json.loads(json.dumps(result, ensure_ascii=False))

    def test_quotation_reported_speech_and_teaching_attribution_are_preserved(self):
        for key in ('question_deflection', 'topic_displacement', 'consequence_chain',
                    'circular_justification', 'absence_as_concealment'):
            text, rule = DOCUMENTS[key]['text'], TARGETS[key]
            self.assertEqual(self.found(text, rule)[0]['status'], 'needs_review')
            self.assertEqual(self.found('Редактор заявил: «' + text + '»', rule)[0]['status'], 'quoted_candidate')
            self.assertEqual(self.found('Фраза «' + text + '»', rule)[0]['status'], 'context_only')

    def test_notices_do_not_claim_obfuscation_or_missing_actor_as_established_facts(self):
        for key in ('unspecified_measures', 'unattributed_decision'):
            f = self.found(DOCUMENTS[key]['text'], TARGETS[key])[0]
            self.assertEqual(f['status'], 'context_only')
            self.assertTrue(f['evidence'][0]['context']['informational_notice'])

    def test_ordinary_related_answers_and_nonpolitical_transitions_do_not_trigger_deflection(self):
        for text in (
            'Почему выросли цены? — Потому что выросла стоимость топлива.',
            'Почему выросли цены? — Зато заработная плата увеличилась.',
            'Неважно, почему пошёл дождь. Главное — взять зонт.',
            'Правительство опубликовало бюджет. Почему герой романа ушёл? — Зато страна великая.',
        ):
            self.assertFalse(self.found(text, 'simplification.question_deflection'), text)

    def test_realistic_causality_and_negated_catastrophes_do_not_trigger_the_chain(self):
        for text in (
            'Если примем закон, то опубликуем правила, затем начнётся регистрация заявлений.',
            'Если пойдёт дождь, то вода поднимется, затем плотина разрушится.',
            'Разрешим митинг — начнутся обсуждения — страна не развалится.',
            'Если примем закон, то правила изменятся, затем катастрофы не будет.',
            'Если примем закон, то правила изменятся, затем получим систему без диктатуры.',
            'Губернатор выступил. Если пойдёт дождь, то вода поднимется, затем плотина разрушится.',
        ):
            self.assertFalse(self.found(text, 'simplification.consequence_chain'), text)
        self.assertFalse([f for f in analyze({'title': 'Заявление правительства',
                         'text': 'Если пойдёт дождь, то вода поднимется, затем плотина разрушится.'})['findings']
                         if f['rule_id'] == 'simplification.consequence_chain'])

    def test_independent_evidence_and_honest_uncertainty_are_not_circular_or_self_sealing(self):
        for text in (
            'Это правда, потому что это подтвердили независимые документы.',
            'Информация верна, потому что опубликована запись заседания.',
            'Доказательств нет, поэтому подтвердить обвинение нельзя.',
            'Доказательств нет, значит их не скрывают.',
            'Нет доказательств, что документы скрывают.',
            'Документы скрывают — об этом свидетельствует опубликованный приказ.',
        ):
            ids = {f['rule_id'] for f in analyze({'text': text})['findings']}
            self.assertFalse(ids & {'simplification.circular_justification', 'simplification.absence_as_concealment'}, text)

    def test_measures_with_nearby_details_and_literal_service_messages_are_not_flagged(self):
        for text in (
            'Губернатор сообщил: будут приняты необходимые меры, а именно выделят средства на ремонт.',
            'Губернатор сообщил, что будут приняты необходимые меры. В частности, опубликуют смету.',
            'Правительство объявило: будут приняты необходимые меры: введут льготный тариф.',
            'Сервисный центр сообщил, что были приняты необходимые меры.',
        ):
            self.assertFalse(self.found(text, 'context.unspecified_measures'), text)

    def test_identified_decision_maker_is_recognised_before_after_and_in_title(self):
        text = 'Было принято решение о повышении тарифов.'
        for document in ({'text': 'Правительством ' + text.lower()},
                         {'text': text + ' Его принял совет муниципалитета.'},
                         {'title': 'Решение правительства', 'text': text}):
            self.assertFalse([f for f in analyze(document)['findings'] if f['rule_id'] == 'context.unattributed_decision'])

    def test_explicit_denial_and_discussion_are_not_reassigned_to_the_author(self):
        for key in ('circular_justification', 'absence_as_concealment'):
            text = 'Неверно утверждать, что ' + DOCUMENTS[key]['text'].lower()
            self.assertEqual(self.found(text, TARGETS[key])[0]['status'], 'context_only')

    def test_publishers_urls_and_publication_dates_are_not_features(self):
        for document in DOCUMENTS.values():
            expected = analyze(document)['findings']
            for source in ('RT', 'Медиазона', 'Неизвестный автор'):
                self.assertEqual(analyze({**document, 'source': source, 'url': 'https://example.org/article',
                                          'published_at': '2026-10-28T12:00:00+03:00'})['findings'], expected)

    def test_bounded_findings_on_repeated_and_long_near_matches(self):
        result = analyze({'text': (DOCUMENTS['circular_justification']['text'] + '\n') * 600})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])
        result = analyze({'text': ('Если принять закон, то ' + 'слово ' * 40) * 700})
        self.assertFalse({f['rule_id'] for f in result['findings']} & NEW_IDS)


if __name__ == '__main__':
    unittest.main()
