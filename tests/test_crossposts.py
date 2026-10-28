"""Content copies across platforms; similarity of a news event is insufficient."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.analysis import VERSION
from media_strazh.business import business_snapshot
from media_strazh.crossposts import group_publications
from media_strazh.publishing import snapshot
from media_strazh.rating import rating_snapshot
from media_strazh.storage import Store
from test_rating import END, START, finding, save_publication


BODY = 'В городе открылась новая библиотека для детей и взрослых. Читальный зал работает каждый день.'
FLAGGED = BODY + ' Все знают о решении правительства.'


def row(number, source='rt', text=BODY, title='', date=END):
    return {'id': number, 'source_id': source, 'title': title, 'text': text, 'published_at': date,
            'retrieved_at': END, 'url': 'https://example.org/' + str(number),
            'analyzed': True, 'finding_count': 0}


class CrosspostTests(unittest.TestCase):
    def test_same_text_merges_only_across_platforms_of_the_same_publisher(self):
        rows = [row(1), row(2, 'rt_telegram'), row(3, 'ria'), row(4, 'ria_telegram'), row(5, 'rt')]
        before = deepcopy(rows)
        groups = group_publications(rows)
        self.assertEqual(sorted(sorted(r['id'] for r in g.members) for g in groups), [[1, 2], [3, 4], [5]])
        self.assertEqual(rows, before)

    def test_typographic_quotes_spaces_line_breaks_and_service_footer(self):
        text = 'Редактор сообщил: «Новая библиотека для детей и взрослых откроется завтра утром».'
        copy = '⚡️ РЕДАКТОР сообщил: "Новая\u00a0библиотека для детей\nи взрослых откроется завтра утром".\n\nПодписывайтесь на наш канал'
        groups = group_publications([row(1, text=text), row(2, 'rt_telegram', copy)])
        self.assertEqual(len(groups), 1)

    def test_a_headline_can_be_added_but_the_complete_body_must_match(self):
        title = 'В городе открылась библиотека с новым читальным залом'
        for site_text in (BODY, title + '\n' + BODY):
            with self.subTest(site_text=site_text):
                groups = group_publications([row(1, title=title, text=site_text),
                                             row(2, 'rt_telegram', title + '\n' + BODY)])
                self.assertEqual(len(groups), 1)
        for teaser in (title, title + '\n' + BODY.split('. ')[0] + '.', BODY.split('. ')[0] + '.'):
            self.assertEqual(len(group_publications([row(1, title=title), row(2, 'rt_telegram', teaser)])), 2)
        # The headline can share words with the first sentence without being
        # a separate heading that may be removed from the complete text.
        self.assertEqual(len(group_publications([
            row(1, title='В городе', text=BODY), row(2, 'rt_telegram', BODY.removeprefix('В городе '))])), 2)

    def test_changed_numbers_negation_names_punctuation_and_updates_remain_separate(self):
        text = 'Комиссия сообщила: Иванов подтвердил, что в городе открылись 12 новых библиотек для детей.'
        variants = [text.replace('12', '13'), text.replace('подтвердил', 'не подтвердил'),
                    text.replace('Иванов', 'Петров'), text + ' Позже сообщение было опровергнуто.',
                    text.replace('подтвердил,', 'подтвердил:')]
        for changed in variants:
            with self.subTest(changed=changed):
                self.assertEqual(len(group_publications([row(1, text=text), row(2, 'rt_telegram', changed)])), 2)

    def test_a_common_quote_or_similar_event_does_not_merge_articles(self):
        quote = '«Работы завершены, новая библиотека откроется для детей и взрослых в следующий понедельник».'
        for other in ('В другом городе открылась новая библиотека для детей и взрослых.',
                      'Мэр говорил о бюджете. ' + quote,
                      BODY.replace('каждый день', 'по выходным')):
            self.assertEqual(len(group_publications([row(1, text=BODY + ' ' + quote),
                                                    row(2, 'rt_telegram', other)])), 2)

    def test_empty_missing_naive_far_dates_and_transitive_copies_are_not_merged(self):
        for text in ('', '...', ' '):
            self.assertEqual(len(group_publications([row(1, text=text), row(2, 'rt_telegram', text)])), 2)
        for date in ('', 'not a date', '2026-10-25T12:00:00', '2026-10-22T12:00:00+00:00'):
            self.assertEqual(len(group_publications([row(1), row(2, 'rt_telegram', date=date)])), 2)
        groups = group_publications([row(1), row(2, 'rt_telegram'), row(3, 'rt_telegram')])
        self.assertEqual(sorted(len(g.members) for g in groups), [1, 2])

    def test_identical_short_complete_messages_are_copies_too(self):
        for text in ('Президент подписал указ о повышении пенсий.', 'В городе открылась библиотека.'):
            self.assertEqual(len(group_publications([row(1, text=text), row(2, 'rt_telegram', text)])), 1)

    def test_timezone_equivalence_and_order_independence(self):
        rows = [row(1), row(2, 'rt_telegram', date='2026-10-25T15:00:00+03:00')]
        self.assertEqual(len(group_publications(rows)), 1)
        self.assertEqual(group_publications(rows)[0].key, group_publications(reversed(rows))[0].key)


class CrosspostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / 'copies.sqlite3')

    def tearDown(self):
        self.store.__exit__()
        self.directory.cleanup()

    def publisher(self):
        return next(p for p in rating_snapshot(self.store, END)['publishers'] if p['id'] == 'rt')

    def copies(self):
        first, _ = save_publication(self.store, 1, text=FLAGGED, findings=[finding()])
        second, _ = save_publication(self.store, 2, 'rt_telegram', text=FLAGGED,
                                     findings=[finding('enemy_image')])
        return first, second

    def test_rating_unions_categories_and_counts_a_crosspost_once_in_both_sides_and_chart(self):
        self.copies()
        save_publication(self.store, 3, 'rt_telegram', text=BODY, findings=[])
        item = self.publisher()
        self.assertEqual((item['raw_publications'], item['collected'], item['flagged'], item['score_percent']), (3, 2, 1, 50))
        self.assertEqual(item['duplicates_excluded'], 1)
        self.assertEqual(item['by_type'], {'fear': 1, 'enemy_image': 1})
        self.assertEqual(sum(p['collected'] for p in item['series']), 2)
        self.assertEqual(sum(p['flagged'] for p in item['series']), 1)
        self.assertEqual(item['series'][-1]['score_percent'], 50)

    def test_a_marker_on_either_variant_is_not_lost(self):
        save_publication(self.store, 1, text=BODY, findings=[])
        save_publication(self.store, 2, 'rt_telegram', text=BODY, findings=[finding()])
        self.assertEqual((self.publisher()['collected'], self.publisher()['flagged']), (1, 1))

    def test_unanalyzed_variant_does_not_masquerade_as_complete(self):
        _, second = self.copies()
        self.store.db.execute('DELETE FROM analyses WHERE revision_id=(SELECT current_revision_id FROM articles WHERE id=?)',
                              (second['id'],))
        item = self.publisher()
        self.assertEqual((item['collected'], item['analyzed']), (1, 0))
        self.assertIsNone(item['score_percent'])

    def test_copy_does_not_reenter_window_or_move_its_hour(self):
        first = (datetime.fromisoformat(START) - timedelta(hours=1)).isoformat()
        save_publication(self.store, 1, text=FLAGGED, published=first)
        save_publication(self.store, 2, 'rt_telegram', text=FLAGGED, published=END)
        item = self.publisher()
        self.assertEqual((item['collected'], item['raw_publications'], item['duplicates_excluded']), (0, 1, 1))
        self.assertIsNone(item['score_percent'])

    def test_future_copy_cannot_erase_the_current_window_member(self):
        save_publication(self.store, 1, text=BODY)
        future = (datetime.fromisoformat(END) + timedelta(hours=1)).isoformat()
        save_publication(self.store, 2, 'rt_telegram', text=BODY, published=future)
        self.assertEqual((self.publisher()['collected'], self.publisher()['raw_publications']), (1, 1))

    def test_public_report_limits_unique_groups_keeps_original_spans_and_platform_variants(self):
        self.copies()
        result = snapshot(self.store, limit=1)
        self.assertEqual(result['totals']['displayed'], 1)
        item = result['articles'][0]
        self.assertEqual(result['deduplication']['duplicates_excluded'], 1)
        variants = [item, *item['variants']]
        self.assertEqual({v['source_id'] for v in variants}, {'rt', 'rt_telegram'})
        self.assertEqual(len({v['publication_id'] for v in variants}), 1)
        for variant in variants:
            self.assertEqual(variant['findings'], [{k: f[k] for k in variant['findings'][0]}
                             for f in self.store.article(variant['id'])['analysis']['findings']])
            self.assertNotIn('text', variant)
        self.assertEqual(self.store.status()['articles_collected'], 2)
        self.assertEqual(json.dumps(snapshot(self.store, 1)['articles']), json.dumps(result['articles']))

    def test_business_mentions_are_counted_once_and_retain_the_real_source(self):
        text = 'Клиника «XXI век» опубликовала новое расписание работы врачей и своего медицинского центра.'
        save_publication(self.store, 1, text=text)
        save_publication(self.store, 2, 'rt_telegram', text=text)
        report = business_snapshot(self.store, END)
        self.assertEqual(report['coverage']['duplicates_excluded'], 1)
        self.assertEqual(len(report['articles']), 1)
        self.assertEqual(report['articles'][0]['watchlists'], ['mc21'])
        self.assertNotIn('text', report['articles'][0])


if __name__ == '__main__':
    unittest.main()
