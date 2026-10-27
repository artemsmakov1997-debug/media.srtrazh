"""Local numeric consistency hypotheses from Kara-Murza; no truth/intent labels."""
import json
import unittest

from media_strazh.analysis import MAX_FINDINGS, analyze
from media_strazh.rating import publication_types


MAJORITY = 'context.majority_percentage'
DAILY = 'context.daily_year_total'
NUMERIC_IDS = {MAJORITY, DAILY}
DOCUMENTS = {
    'numeric_majority': {'text': 'По данным опроса, большинство участников (37%) поддержали инициативу.'},
    'numeric_daily': {'text': 'В течение всего 2025 года в среднем фиксировали 100 аварий в день — всего 10 тысяч аварий за год.'},
}


class NumericConsistencyTests(unittest.TestCase):
    def findings(self, text, rule=None, **fields):
        return [f for f in analyze({'text': text, **fields})['findings']
                if f['rule_id'] == rule or rule is None and f['rule_id'] in NUMERIC_IDS]

    def test_two_previously_unmarked_book_development_probes_are_recognised(self):
        for key, rule in (('numeric_majority', MAJORITY), ('numeric_daily', DAILY)):
            self.assertEqual(len(self.findings(DOCUMENTS[key]['text'], rule)), 1)

    def test_percentages_and_bounded_ranges_directly_defining_a_majority(self):
        for phrase in ('Большинство участников (37%)', 'Большинство — 37% опрошенных',
                       'большинство — 37%',
                       '37% участников — большинство', 'Большая часть участников: 37%',
                       'Подавляющее число участников (30–48%)', 'Большинство (от 30 до 48%)',
                       'Большинство, то есть 37%', 'Большинство участников (49,9%)',
                       'Большинство участников (49.9%)', 'Большинство участников (0%)'):
            with self.subTest(phrase=phrase):
                self.assertEqual(len(self.findings(phrase + '.', MAJORITY)), 1)

    def test_majority_and_plurality_are_not_interchangeable(self):
        for phrase in ('Большинство участников (51%) поддержали инициативу.',
                       'Большинство участников (50%) поддержали инициативу.',
                       '37% опрошенных составили крупнейшую из пяти групп.',
                       '37% участников — относительное большинство.',
                       'Относительное большинство участников (37%) поддержало решение.',
                       'Большинство участников (37–80%) поддержали решение.'):
            self.assertFalse(self.findings(phrase, MAJORITY), phrase)

    def test_majority_scope_denominators_and_partial_answers_are_guarded(self):
        for phrase in ('Большинство определившихся — 37% всех опрошенных.',
                       'Большинство взрослых — 37% всего населения.',
                       'Большинство сторонников — 37% жителей.',
                       'Большинство акционеров — 37% населения.',
                       'Большинство участников — 37% избирателей.',
                       'Большинство участников поддержали решение; 37% полностью согласны.',
                       'Большинство участников поддержали решение, в том числе 37% полностью.',
                       'Большинство участников (60%) согласны, 37% не согласны.',
                       'Большинство (37%) полностью поддержали решение.',
                       'Большинство участников: 37% роста доходов.',
                       'Большинство пришедших — 37% всех участников.',
                       'Большинство коалиции (37% голосов) осталось на местах.'):
            self.assertFalse(self.findings(phrase, MAJORITY), phrase)

    def test_negation_approximate_percentages_and_invalid_domains_are_not_the_majority_rule(self):
        for phrase in ('Это не большинство (37%).', 'Не подавляющее большинство (37%).',
                       'Большинство (около 49,9%) поддержали решение.',
                       'Большинство примерно (49,9%) поддержали решение.',
                       'Большинство — от 37% опрошенных.',
                       'Большинство (48–30%) поддержали решение.',
                       'Большинство (137%) поддержали решение.',
                       '-37% участников — большинство.'):
            self.assertFalse(self.findings(phrase, MAJORITY), phrase)

    def test_survey_method_details_do_not_cancel_a_text_internal_question(self):
        text = DOCUMENTS['numeric_majority']['text'] + ' Опрос проводил ВЦИОМ, методика опубликована, выборка — 1000 человек.'
        self.assertEqual(len(self.findings(text, MAJORITY)), 1)

    def test_percent_and_group_need_a_direct_local_link(self):
        for phrase in ('Большинство участников поддержали решение. 37% не поддержали.',
                       'Большинство участников поддержали решение, а 37% предложили поправки.',
                       'Большинство участников выступили за инициативу, рейтинг вырос на 37%.',
                       'Большинство участников закончили опрос — 37% ещё заполняют анкету.',
                       'Большинство жителей поддержали инициативу — 37% отказались.',
                       'Рейтинг вырос на 37%. Большинство участников поддержали инициативу.'):
            self.assertFalse(self.findings(phrase, MAJORITY), phrase)

    def test_day_year_mismatch_and_elided_annual_measure(self):
        for phrase in ('100 событий в день — всего 10 тысяч событий в год.',
                       '100 событий в день — 10 тысяч за год.',
                       '100 событий в день — всего 10 тысяч в год.',
                       'В среднем 100 случаев в сутки, то есть 10 тысяч случаев за год.',
                       '13 тысяч событий ежедневно — всего 6 миллионов событий за год.',
                       '1,3 тыс. событий в день — всего 0,6 млн событий за год.',
                       '1.3 тыс. событий в день — всего 0.6 млн событий за год.',
                       '100 аварий каждый день, итого 10 тысяч аварий за год.'):
            with self.subTest(phrase=phrase):
                self.assertEqual(len(self.findings(phrase, DAILY)), 1)

    def test_decimal_scales_and_unicode_grouping_preserve_exact_evidence(self):
        for space in (' ', '\u00a0', '\u202f'):
            text = f'🧭 13{space}000 событий в день — всего 6{space}000{space}000 событий за год.'
            result = self.findings(text, DAILY)[0]
            self.assertEqual(result['evidence'][0]['context']['daily_number'], '13000')
            self.assertEqual(result['evidence'][0]['context']['stated_annual'], '6000000')
            for evidence in result['evidence']:
                self.assertEqual(text[evidence['start']:evidence['end']], evidence['quote'])

    def test_consistent_rates_and_coarse_rounding_are_not_flagged(self):
        for phrase in ('100 событий в день — всего 36 500 событий за год.',
                       '100 событий в день — всего 36 тысяч событий за год.',
                       '100 событий в день — всего 37 тысяч событий за год.',
                       '100 событий в день — всего 36,5 тыс. событий за год.',
                       'В среднем 1 событие в день — всего 365 событий за год.',
                       'В среднем 1,5 события в день — всего 548 событий за год.',
                       'В среднем 0 событий в день — всего 100 событий за год.'):
            self.assertFalse(self.findings(phrase, DAILY), phrase)

    def test_leap_year_is_read_from_text_not_publication_metadata(self):
        for year, nominal in ((2024, '36600'), (2025, '36500'), (2000, '36600'), (1900, '36500')):
            text = f'В {year} году 100 событий в день — всего 10 тысяч событий за год.'
            evidence = self.findings(text, DAILY)[0]['evidence'][0]['context']
            self.assertEqual(evidence['nominal_annual'], [nominal])
            self.assertEqual(evidence['days_considered'], [int(nominal) // 100])
        result = self.findings('100 событий в день — всего 10 тысяч событий за год.', DAILY)[0]
        self.assertEqual(result['evidence'][0]['context']['days_considered'], [365, 366])

    def test_mathematically_consistent_conversions_across_counts_and_scales(self):
        for year, days in ((2024, 366), (2025, 365)):
            for rate in (1, 2, 7, 23, 100, 999, 13000):
                text = f'В {year} году {rate} событий в день — всего {rate * days} событий за год.'
                self.assertFalse(self.findings(text, DAILY), text)
        for text in ('1 тыс. рублей в день — всего 365 тыс. рублей за год.',
                     '1,5 тыс. событий в день — всего 547,5 тыс. событий за год.',
                     '0 событий в день — всего 0 событий за год.'):
            self.assertFalse(self.findings(text, DAILY), text)

    def test_explicit_exactness_and_rounding_have_distinct_intervals(self):
        text = 'В 2024 году ровно 100 событий в день — всего ровно 36500 событий за год.'
        self.assertEqual(len(self.findings(text, DAILY)), 1)
        # An integer *average* of 100 may round a true average of 99.73.
        self.assertFalse(self.findings(text.replace('ровно ', ''), DAILY))
        self.assertFalse(self.findings('Ровно 100 событий в день — всего ровно 36500 событий за год.', DAILY))

    def test_different_units_groups_periods_and_workdays_are_not_annualised(self):
        for text in ('100 человек в день — всего 10 тысяч рублей за год.',
                     '100 аварий в день — всего 10 тысяч погибших за год.',
                     '100 событий в день в России — всего 10 тысяч событий за год в Европе.',
                     '100 событий в день, а в Европе всего 10 тысяч событий за год.',
                     'В одной стране 100 случаев в день — всего 6 миллионов случаев за год в другой стране.',
                     '100 случаев в день — всего 6 миллионов случаев за год среди детей.',
                     'В рабочие дни 100 событий в день — всего 10 тысяч событий за год.',
                     'В январе 100 событий в день — всего 10 тысяч событий за год.',
                     'В 2025 году 100 событий в день — всего 10 тысяч событий за 2024 год.',
                     'С 2024 по 2025 год 100 событий в день — всего 10 тысяч событий за год.',
                     'В 2024–2025 годах 100 событий в день — всего 10 тысяч событий за год.',
                     'В прошлом году 100 событий в день — всего 10 тысяч событий за год.',
                     'В пик сезона 100 событий в день — всего 10 тысяч событий за год.',
                     'Прогноз: 100 событий в день — всего 10 тысяч событий за год.',
                     '100 событий в день, кроме выходных — всего 10 тысяч событий за год.'):
            self.assertFalse(self.findings(text, DAILY), text)

    def test_approximate_bounded_negative_and_increment_rates_are_not_asserted_totals(self):
        for text in ('До 100 событий в день — всего 10 тысяч событий за год.',
                     'Более 100 событий в день — всего 10 тысяч событий за год.',
                     '100 событий в день — всего около 10 тысяч событий за год.',
                     '-100 событий в день — всего 10 тысяч событий за год.',
                     '100 событий в день — всего -10 тысяч событий за год.',
                     'Рост на 100 событий в день — всего 10 тысяч событий за год.',
                     '13 00 событий в день — всего 6 миллионов событий за год.'):
            self.assertFalse(self.findings(text, DAILY), text)
        for text in ('1_000 событий в день — всего 365 тысяч событий за год.',
                     '1,000 событий в день — всего 365 тысяч событий за год.',
                     '1.000 событий в день — всего 365 тысяч событий за год.'):
            self.assertFalse(self.findings(text, DAILY), text)

    def test_do_not_link_arbitrary_numbers_or_cross_sentence_boundaries(self):
        for text in ('100 событий в день. За год поступило 10 тысяч заявок.',
                     '100 событий в день. Всего 10 тысяч событий за год.',
                     '100 событий в день, рядом работают 10 тысяч человек.',
                     '100 событий в день, после ремонта 300 событий в день — всего 10 тысяч событий за год.',
                     '100 событий в день — всего 10 тысяч в 2024 году и 30 тысяч в 2025 году.'):
            self.assertFalse(self.findings(text, DAILY), text)

    def test_findings_are_informational_weight_one_and_json_serialisable(self):
        for document in DOCUMENTS.values():
            result = analyze(document)
            json.dumps(result, ensure_ascii=False)
            for finding in self.findings(document['text']):
                self.assertEqual(finding['status'], 'context_only')
                self.assertEqual(finding['rating_weight'], 1)
                self.assertTrue(finding['explanation'] and finding['review_question'])
                self.assertTrue(publication_types([finding]))
                self.assertTrue(all(e['context']['informational_notice'] for e in finding['evidence']))
                self.assertTrue(all(e['context']['truth_checked'] is False for e in finding['evidence']))

    def test_quotes_and_teaching_context_keep_their_attribution(self):
        for document in DOCUMENTS.values():
            quoted = self.findings('Депутат заявил: «' + document['text'] + '»')[0]
            self.assertTrue(all(e['context']['in_quotes'] for e in quoted['evidence']))
            discussed = self.findings('Фраза «' + document['text'] + '»')[0]
            self.assertTrue(all(e['context']['metalinguistic'] for e in discussed['evidence']))

    def test_title_and_body_have_independent_unmodified_unicode_coordinates(self):
        title = '📰 Большинство участников (37%) поддержали решение.'
        text = '🧭 ' + DOCUMENTS['numeric_daily']['text']
        result = analyze({'title': title, 'text': text})
        self.assertEqual({e['field'] for f in result['findings'] for e in f['evidence']}, {'title', 'text'})
        for finding in result['findings']:
            for evidence in finding['evidence']:
                source = result['document'][evidence['field']]
                self.assertEqual(source[evidence['start']:evidence['end']], evidence['quote'])
                sentence = evidence['sentence']
                self.assertEqual(source[sentence['start']:sentence['end']], sentence['text'])

    def test_publisher_url_and_publication_date_never_change_findings(self):
        for document in DOCUMENTS.values():
            expected = analyze(document)['findings']
            for name in ('RT', 'Медиазона', 'Неизвестный источник'):
                other = analyze({**document, 'source': name, 'url': 'https://example.org/2024/',
                                 'published_at': '2024-02-29T23:00:00+00:00'})
                self.assertEqual(other['findings'], expected)

    def test_long_text_and_finding_limits_remain_bounded(self):
        text = 'Большинство участников (37%) поддержали инициативу. ' * (MAX_FINDINGS + 3)
        result = analyze({'text': text})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])
