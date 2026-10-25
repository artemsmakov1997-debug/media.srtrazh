"""User regressions and counterexamples, not independent accuracy estimates.

Public message excerpts retrieved 2026-10-25. These tests establish detection
behaviour, not the authenticity of the historical quote or either ranking.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.analysis import analyze
from media_strazh.collector import reanalyze_current, reextract_current
from media_strazh.extraction import FeedEntry
from media_strazh.network import Response
from media_strazh.sources import SOURCES
from media_strazh.storage import SCHEMA_VERSION, Store
from media_strazh.telegram import extract_post


HISTORICAL_TEXT = (
    '⚡️Я чисто ради интереса решил почитать речь Гитлера перед вторжением в Польшу:\n'
    '"Я решил освободить германские границы от элементов неуверенности, постоянной угрозы гражданской войны. '
    'Я добьюсь, чтобы на восточной границе воцарился мир, такой же, как на остальных наших границах.\n'
    'Для этого я предприму необходимые меры, не противоречащие предложениям, сделанным мною в Рейхстаге '
    'для всего мира, то есть, я не буду воевать против женщин и детей. '
    'Я приказал, чтобы мои воздушные силы ограничились атаками на военные цели."'
)
COMPARISON_TEXT = (
    '⚡️Финляндия уже восьмой год подряд занимает первое место в рейтинге самых счастливых стран от World Happiness Report.\n'
    'При этом некогда отжатая у Финляндии Карелия возглавила рейтинг самых депрессивных регионов РФ.\n'
    'Напасть на счастливую страну, положить двести тысяч жизней в зимнем лесу, отхватить кусок и превратить его '
    'в вонючую депрессивную помойку – в этом и есть вся суть совка.'
)
HISTORY = 'context.historical_reference'
COMPARISON = 'context.evaluative_comparison'
VISUAL = 'context.visual_comparison'
NEW_RHETORIC = {'dysphemism.degrading_place_metaphor', 'dysphemism.sovok_label', 'generalization.essentialist_reduction'}


class ComparativeFramingTests(unittest.TestCase):
    def findings(self, document, *ids):
        return [f for f in analyze(document)['findings'] if f['rule_id'] in ids]

    def test_selected_historical_quote_is_a_notice_without_an_invented_modern_target(self):
        result = analyze({'text': HISTORICAL_TEXT})
        self.assertEqual([f['rule_id'] for f in result['findings']], [HISTORY])
        finding = result['findings'][0]
        self.assertEqual((finding['label'], finding['status']), ('Историческая отсылка', 'context_only'))
        self.assertFalse(finding['evidence'][0]['context']['modern_target_identified'])
        self.assertIn('не проверена', finding['explanation'])
        self.assertEqual(result['summary']['candidate_fragments'], 0)
        self.assertEqual(result['summary']['review_candidates'], 0)
        for source in ('RT', 'Радио Свобода', 'Ватное болото'):
            self.assertEqual(analyze({'text': HISTORICAL_TEXT, 'source': source,
                                      'published_at': '2022-02-26T13:33:33+00:00'})['findings'], result['findings'])
        for actor in ('Черчилля', 'Рузвельта', 'Сталина', 'Наполеона'):
            self.assertTrue(self.findings({'text': HISTORICAL_TEXT.replace('Гитлера', actor)}, HISTORY))

    def test_historical_name_reading_report_and_unquoted_archive_are_not_enough(self):
        for text in ('Гитлер заявил, что границы нужно изменить.',
                     HISTORICAL_TEXT.split('\n', 1)[1],
                     'Я решил почитать речь Гитлера перед вторжением в Польшу.',
                     HISTORICAL_TEXT.replace('ради интереса', 'на уроке истории'),
                     HISTORICAL_TEXT.replace('ради интереса', 'в архиве')):
            with self.subTest(text=text[:80]):
                self.assertEqual(self.findings({'text': text}, HISTORY), [])

    def test_explicit_analogies_are_extended_but_not_duplicated_by_a_reference_notice(self):
        for actor in ('Путин', 'Зеленский', 'Байден', 'Макрон'):
            for verb in ('напоминает', 'копирует', 'повторяет методы'):
                document = {'text': f'{actor} {verb} Гитлера.'}
                self.assertTrue(self.findings(document, 'enemy.nazi_analogy'))
                self.assertFalse(self.findings(document, HISTORY))
            for name in ('Черчилль', 'Рузвельт', 'Сталин', 'Наполеон', 'Перл-Харбор'):
                self.assertTrue(self.findings({'text': f'{actor} действует так же, как {name}.'}, 'simplification.historical_parallel'))
        for text in ('Историк рассказал, как Гитлер пришёл к власти.',
                     'В 1938 году политик действовал как Сталин.'):
            self.assertFalse(self.findings({'text': text}, 'enemy.nazi_analogy', 'simplification.historical_parallel'))

    def test_ranking_opposition_is_not_declared_invalid_and_needs_no_known_publisher(self):
        document = {'text': COMPARISON_TEXT}
        result = analyze(document)
        ids = {f['rule_id'] for f in result['findings']}
        self.assertTrue(NEW_RHETORIC <= ids)
        self.assertIn(COMPARISON, ids)
        self.assertNotIn(VISUAL, ids)  # Text alone does not establish attachments.
        finding = self.findings(document, COMPARISON)[0]
        self.assertEqual(len(finding['evidence']), 2)
        self.assertEqual(finding['status'], 'context_only')
        self.assertIn('может быть обоснованным', finding['explanation'])
        for source in ('Ватное болото', 'RT', 'Радио Свобода', 'Медиазона', 'Неизвестное издание'):
            self.assertEqual(analyze({**document, 'source': source, 'url': 'https://example.org/'})['findings'], result['findings'])

    def test_swapping_sides_preserves_the_same_comparison_and_loaded_labels(self):
        text = COMPARISON_TEXT.replace('Финляндия', 'Карелия').replace('Карелия возглавила', 'Финляндия возглавила')
        ids = {f['rule_id'] for f in analyze({'text': text})['findings']}
        self.assertTrue(NEW_RHETORIC | {COMPARISON} <= ids)

    def test_nearby_opposites_need_a_comparative_frame_and_social_objects(self):
        for text in ('Финляндия возглавила рейтинг счастливых стран. Карелия возглавила рейтинг депрессивных регионов.',
                     'Финляндия возглавила рейтинг счастливых стран.\n' + 'Новая заметка.\n' * 4 +
                     'При этом Карелия возглавила рейтинг депрессивных регионов.',
                     'Финляндия возглавила рейтинг счастливых стран. ' + 'Подробное описание ' * 40 +
                     'При этом Карелия возглавила рейтинг депрессивных регионов.',
                     'Один пациент счастливый, при этом другой — депрессивный.',
                     'В городе нашли красивый камень, при этом соседний был разрушенный.'):
            with self.subTest(text=text[:80]):
                self.assertFalse(self.findings({'text': text}, COMPARISON, VISUAL))

    def test_media_observation_enables_visual_notice_without_claiming_image_analysis(self):
        document = {'text': COMPARISON_TEXT, 'media': {'image_count': 2}}
        result = analyze(document)
        finding = self.findings(document, VISUAL)[0]
        self.assertEqual(finding['status'], 'context_only')
        self.assertIn('не анализировал', finding['explanation'])
        self.assertTrue(all(e['context']['images_analyzed'] is False for e in finding['evidence']))
        self.assertTrue(all(e['context']['image_count'] == 2 for e in finding['evidence']))
        self.assertEqual(result['document']['media'], document['media'])
        self.assertEqual(result['summary']['candidate_fragments'], analyze({'text': COMPARISON_TEXT})['summary']['candidate_fragments'])
        for count in (0, 1):
            self.assertFalse(self.findings({**document, 'media': {'image_count': count}}, VISUAL))
        self.assertFalse(self.findings({'text': 'В городе открылась библиотека.', 'media': {'image_count': 2}}, VISUAL))

    def test_explicit_photo_comparison_can_be_flagged_in_plain_text(self):
        text = 'На первом фото — центр Финляндии. На втором фото — окраина Карелии.'
        finding = self.findings({'text': text}, VISUAL)[0]
        self.assertEqual(len(finding['evidence']), 2)
        self.assertNotIn('image_count', finding['evidence'][0]['context'])
        self.assertFalse(self.findings({'text': 'Я нашёл второе фото в архиве.'}, VISUAL))

    def test_literal_scoops_waste_and_report_summaries_do_not_become_political_labels(self):
        for text in ('В Карелии купили совок для уборки мусора.',
                     'Купил совок.', 'Совок лежит на столе.', 'Продают совки с длинной ручкой.',
                     'Совком собрали песок в песочнице.', 'Город вывез отходы с помойки.',
                     'В городе у контейнера нашли вонючую помойку с мусором.',
                     'В этом и есть вся суть доклада о политике.',
                     'В этом вся суть задачи.', 'У него вся суть характера в улыбке.'):
            self.assertFalse(self.findings({'title': 'Политика России', 'text': text}, *NEW_RHETORIC))

    def test_impersonal_opinion_distinguishes_named_experiencer_and_nonpolitical_usage(self):
        for prefix in ('Считается', 'Принято считать', 'Представляется'):
            self.assertTrue(self.findings({'text': f'{prefix}, что политика правительства эффективна.'}, 'source.impersonal_opinion'))
        for text in ('Мне представляется, что политика правительства эффективна.',
                     'По мнению Иванова, считается, что политика правительства эффективна.',
                     'Согласно исследованию, считается, что политика правительства эффективна.',
                     'Считается, что сумма равна пяти.'):
            self.assertFalse(self.findings({'text': text}, 'source.impersonal_opinion'))

    def test_quotes_negation_exact_offsets_and_metadata_hash_remain_auditable(self):
        for text in (COMPARISON_TEXT, '**' + COMPARISON_TEXT + '**', COMPARISON_TEXT.replace('\n', '\r\n'),
                     'Автор написал: «' + COMPARISON_TEXT + '»'):
            for f in analyze({'text': text})['findings']:
                for e in f['evidence']:
                    self.assertEqual(text[e['start']:e['end']], e['quote'])
        for f in self.findings({'text': 'Автор написал: «' + COMPARISON_TEXT + '»'}, *NEW_RHETORIC):
            self.assertEqual(f['status'], 'quoted_candidate')
        self.assertEqual(self.findings({'text': 'Россию нельзя считать вонючей помойкой.'}, 'dysphemism.degrading_place_metaphor')[0]['status'], 'context_only')
        original = {'text': COMPARISON_TEXT, 'media': {'image_count': 2}}
        before = copy.deepcopy(original)
        result = analyze(original)
        self.assertEqual(before, original)
        self.assertNotEqual(result['document']['sha256'], analyze({'text': COMPARISON_TEXT})['document']['sha256'])
        original['media']['image_count'] = 1
        self.assertEqual(result['document']['media']['image_count'], 2)

    def test_media_schema_is_small_and_rejects_untrusted_content_and_wrong_types(self):
        for media in (None, [], 2, {}, {'url': 'https://example.org/'}, {'image_count': True},
                      {'image_count': -1}, {'image_count': 101}, {'image_count': '2'},
                      {'image_count': 2, 'images_analyzed': True}):
            with self.subTest(media=media), self.assertRaises(ValueError):
                analyze({'text': 'Текст публикации.', 'media': media})


class ComparisonCollectionTests(unittest.TestCase):
    def test_preview_album_counts_survive_storage_migration_and_reanalysis(self):
        source = SOURCES['rt_telegram']
        url = 'https://t.me/rt_russian/42'
        photo = '<a class="tgme_widget_message_photo_wrap" href="https://t.me/rt_russian/{}?single"></a>'
        html = ('<div data-post="rt_russian/42"><img src="avatar.jpg">' + photo.format(42) + photo.format(43) + photo.format(42)
                + '<a class="tgme_widget_message_photo_wrap" href="https://t.me/other_channel/4?single"></a>'
                + '<a class="tgme_widget_message_photo_wrap" href="https://t.me/rt_russian/99?unsafe=1"></a>'
                + '<div class="tgme_widget_message_link_preview">' + photo.format(44) + '</div>'
                + '<div data-post="rt_russian/45">' + photo.format(45) + '</div>'
                + '<div class="tgme_widget_message_text">' + COMPARISON_TEXT + '</div></div>')
        entry = FeedEntry(url, '')
        extracted = extract_post(html, url, source, entry)
        self.assertEqual(extracted['document']['media'], {'image_count': 2})
        now = '2026-10-25T10:00:00+00:00'
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'corpus.sqlite3'
            with Store(database) as store:
                store.discover(source.id, [entry], now)
                article = store.due(source.id, now, 1)[0]
                old = {**extracted, 'extractor_version': 'html-0.5.0',
                       'document': {k: v for k, v in extracted['document'].items() if k != 'media'}}
                store.save(article, old, Response(url, html.encode(), 'text/html'), analyze(old['document']), now, 3600)
                store.db.execute('DROP TABLE revision_media')
                store.db.execute('PRAGMA user_version=1')
                store.db.commit()
            with Store(database) as store:
                self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
                self.assertNotIn('media', store.article(article['id'])['document'])
                refresh = reextract_current(store, outdated_only=True)
                self.assertTrue(refresh['success'])
                self.assertEqual(refresh['new_revisions'], 1)
                revision_id = store.article(article['id'])['revision_id']
                self.assertEqual(store.article(article['id'])['document'], extracted['document'])
                self.assertEqual(next(store.export_corpus())['document']['media'], {'image_count': 2})
                store.db.execute('DELETE FROM analyses WHERE revision_id=?', (revision_id,))
                store.db.commit()
                self.assertEqual(next(store.pending_analyses())['document']['media'], {'image_count': 2})
                self.assertTrue(reanalyze_current(store)['success'])
                result = store.article(article['id'])['analysis']
                self.assertIn(VISUAL, {f['rule_id'] for f in result['findings']})
                self.assertEqual(result, analyze(extracted['document']))

    def test_benchmark_identity_preserves_media_without_selecting_on_predictions(self):
        from media_strazh.benchmark import prepare_benchmark, evaluate_benchmark
        from test_benchmark import record, Records
        rows = [record(i) for i in range(1, 5)]
        for row in rows:
            row['document']['media'] = {'image_count': 2}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'review'
            prepare_benchmark(Records(rows), output, size=3)
            records = [json.loads(line) for file in ('development.jsonl', 'holdout.jsonl')
                       for line in (output / file).read_text().splitlines()]
            for row in records:
                self.assertEqual(row['provenance']['sha256'], analyze(row['document'])['document']['sha256'])
            self.assertEqual(evaluate_benchmark(records)['status'], 'awaiting_human_review')

