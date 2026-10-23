"""Structural regression examples; these are development cases, not a score."""

import unittest

from media_strazh.analysis import MAX_CHARS, MAX_FINDINGS, analyze


CURRENT_STATEMENT = ('⚡️Путин: Киеву неуместно говорить о территориальных потерях, поскольку '
                     '"это не их территория, а территория исторической России", '
                     'Киев направил пушки и самолёты против наших людей.')
HISTORICAL_STATEMENTS = (
    'В феврале 1938 года Гитлер заявил, что немцев в Судетах надо спасать, '
    'поскольку чехословацкое правительство пытается их уничтожить.',
    'В сентябре 1938 года Гитлер заявил, что судетские немцы должны вернуться '
    'на "историческую Родину" вместе с территориями, на которых они проживают.',
    'В сентябре 1939 года, уже после аннексии Судет, Гитлер заявил, что это было '
    'необходимо для восстановления исторической справедливости и воссоединения народа.',
)
USER_TEXT = '\n\n'.join((CURRENT_STATEMENT,) + HISTORICAL_STATEMENTS)
RULE = 'simplification.historical_juxtaposition'


class HistoricalJuxtapositionTests(unittest.TestCase):
    def matches(self, document):
        return [f for f in analyze(document)['findings'] if f['rule_id'] == RULE]

    def test_user_example_links_statements_without_claiming_historical_accuracy(self):
        result = analyze({'text': USER_TEXT})
        self.assertEqual(len(result['findings']), 1)
        finding = result['findings'][0]
        self.assertEqual((finding['rule_id'], finding['category'], finding['label'], finding['status']),
                         (RULE, 'oversimplification', 'Историческая аналогия', 'needs_review'))
        self.assertEqual([e['quote'] for e in finding['evidence']],
                         [CURRENT_STATEMENT, *HISTORICAL_STATEMENTS])
        self.assertEqual(result['summary']['review_candidates'], 1)
        self.assertEqual(result['summary']['candidate_fragments'], 4)
        self.assertIn('даже без слова «как»', finding['explanation'])
        self.assertIn('не доказывает', finding['explanation'])
        self.assertIn('даты', finding['review_question'])
        self.assertNotIn('enemy_image', result['summary']['by_category'])
        for item in finding['evidence']:
            self.assertEqual(USER_TEXT[item['start']:item['end']], item['quote'])
            self.assertTrue(item['context']['historical_analogy'])

    def test_formatting_and_reverse_order_keep_original_unicode_offsets(self):
        for text in (USER_TEXT.replace('\n\n', ' '), USER_TEXT.replace('\n', '\r\n'),
                     '**' + USER_TEXT + '**',
                     '\n\n'.join(HISTORICAL_STATEMENTS + (CURRENT_STATEMENT,))):
            with self.subTest(text=text[:50]):
                finding = self.matches({'text': text})[0]
                self.assertEqual(len(finding['evidence']), 4)
                for item in finding['evidence']:
                    self.assertEqual(text[item['start']:item['end']], item['quote'])

    def test_current_heading_and_historical_body_are_linked(self):
        document = {'title': CURRENT_STATEMENT, 'text': '\n\n'.join(HISTORICAL_STATEMENTS)}
        finding = self.matches(document)[0]
        self.assertEqual([e['field'] for e in finding['evidence']], ['title', 'text', 'text', 'text'])
        for item in finding['evidence']:
            self.assertEqual(document[item['field']][item['start']:item['end']], item['quote'])

    def test_source_and_current_political_side_do_not_determine_detection(self):
        for actor in ('Путин', 'Зеленский', 'Трамп', 'Макрон', 'Мерц'):
            text = USER_TEXT.replace('Путин:', actor + ':', 1)
            expected = self.matches({'text': text})
            self.assertEqual(len(expected), 1)
            for source in ('RT', 'Радио Свобода', 'BBC', 'Медиазона', 'Неизвестное СМИ'):
                self.assertEqual(self.matches({'text': text, 'source': source}), expected)

    def test_historical_names_alone_and_one_shared_topic_do_not_trigger(self):
        negatives = (
            '\n\n'.join(HISTORICAL_STATEMENTS),
            'Путин посетил архив.\n\n' + '\n\n'.join(HISTORICAL_STATEMENTS),
            'Путин выступил о территориальных границах.\n\n' + HISTORICAL_STATEMENTS[1],
            'В 1938 году премьер говорил об исторической Родине и территории.\n\n' + HISTORICAL_STATEMENTS[1],
            CURRENT_STATEMENT + '\n\nИсторик прочитал доклад о Гитлере.',
            CURRENT_STATEMENT + '\n\nСталинград находится на исторической территории России.',
            CURRENT_STATEMENT + '\n\nВ фильме Гитлер требует вернуть территории на историческую Родину.',
        )
        for text in negatives:
            with self.subTest(text=text[:80]):
                self.assertEqual(self.matches({'text': text}), [])

    def test_matching_justifications_cover_other_historical_actors_and_future_tense(self):
        for actor in ('Гитлер', 'Сталин', 'Наполеон', 'Муссолини'):
            text = CURRENT_STATEMENT + '\n\n' + (
                f'{actor} заявил, что в будущем территории вернутся на историческую Родину.')
            with self.subTest(actor=actor):
                self.assertEqual(len(self.matches({'text': text})), 1)

    def test_unrelated_current_story_and_distant_passages_are_boundaries(self):
        negatives = (
            CURRENT_STATEMENT + '\n\nМакрон открыл выставку.\n\n' + HISTORICAL_STATEMENTS[1],
            CURRENT_STATEMENT + '\n\n' + 'Нейтральная заметка.\n' * 6 + HISTORICAL_STATEMENTS[1],
            CURRENT_STATEMENT + '\n\n' + 'Нейтральное описание ' * 120 + '.\n\n' + HISTORICAL_STATEMENTS[1],
        )
        for text in negatives:
            self.assertEqual(self.matches({'text': text}), [])

    def test_editorial_arrangement_is_distinct_from_a_quoted_comparison(self):
        quoted = 'Автор написал: «' + USER_TEXT + '»'
        self.assertEqual(self.matches({'text': quoted})[0]['status'], 'quoted_candidate')
        # Individual reported statements do not attribute the arrangement to
        # either speaker. The finding concerns the relationship between passages.
        self.assertEqual(self.matches({'text': USER_TEXT})[0]['status'], 'needs_review')

    def test_rejected_analogy_is_a_context_notice(self):
        for suffix in ('Такое сравнение некорректно.', 'Нельзя проводить исторические параллели.',
                       'Это учебный пример исторической аналогии.'):
            finding = self.matches({'text': USER_TEXT + '\n\n' + suffix})[0]
            self.assertEqual(finding['status'], 'context_only')

    def test_existing_explicit_nazi_comparison_is_not_duplicated(self):
        text = 'Путин требует вернуть территории на историческую Родину, как Гитлер.'
        result = analyze({'text': text})
        self.assertEqual([f['rule_id'] for f in result['findings']], ['enemy.nazi_analogy'])

    def test_shared_finding_budget_and_long_nonmatching_passage(self):
        result = analyze({'text': 'Все знают.\n' * MAX_FINDINGS + USER_TEXT})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])
        self.assertEqual(self.matches({'text': 'Путин ' + 'территории ' * ((MAX_CHARS - 10) // 11)}), [])


if __name__ == '__main__':
    unittest.main()
