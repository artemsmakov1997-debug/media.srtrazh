"""Requested vocabulary, word senses and attribution; no source-specific labels."""

import json
import unittest

from media_strazh.analysis import MAX_FINDINGS, VERSION, analyze
from media_strazh.rules import RULES


DOCUMENTS = {
    'geopolitical_west': {'text': 'Запад ввёл новые санкции.'},
    'collective_west': {'text': 'Коллективный Запад поддержал решение.'},
    'western_partners': {'text': 'Западные партнёры предложили переговоры.'},
    'putinoid_group': {'text': 'Путиноиды поддержали решение президента.'},
    'vatnik_group': {'text': 'Эти ватники снова голосуют за президента.'},
    'occupier_actor': {'text': 'Оккупанты вошли в город.'},
    'liberator_actor': {'text': 'Освободители города выступили на площади.'},
    'propagandist_actor': {'text': 'Журналиста назвали пропагандистом.'},
}
TARGETS = {key: ('dysphemism.' if key.endswith('_group') else 'terminology.') + key for key in DOCUMENTS}
NEW_IDS = set(TARGETS.values())
SLURS = {'dysphemism.putinoid_group', 'dysphemism.vatnik_group'}


class PoliticalVocabularyTests(unittest.TestCase):
    def find(self, text, rule):
        return [f for f in analyze({'text': text})['findings'] if f['rule_id'] == rule]

    def test_all_eight_new_rules_have_reviewable_user_examples(self):
        self.assertEqual(len(NEW_IDS), 8)
        self.assertTrue(NEW_IDS <= {r.id for r in RULES})
        for key, doc in DOCUMENTS.items():
            self.assertEqual(len(self.find(doc['text'], TARGETS[key])), 1, key)

    def test_both_fields_preserve_original_unicode_spans_and_unit_weight(self):
        for key, doc in DOCUMENTS.items():
            for field in ('text', 'title'):
                document = {'text': 'Опубликован материал.', field: '📰 ' + doc['text']}
                result = analyze(document)
                hits = [f for f in result['findings'] if f['rule_id'] == TARGETS[key]]
                self.assertEqual(len(hits), 1, (key, field))
                self.assertEqual(result['algorithm_version'], VERSION)
                for f in hits:
                    self.assertEqual(f['rating_weight'], 1)
                    self.assertTrue(f['explanation'] and f['review_question'])
                    for e in f['evidence']:
                        self.assertEqual(document[e['field']][e['start']:e['end']], e['quote'])
                        s = e['sentence']
                        self.assertEqual(document[e['field']][s['start']:s['end']], s['text'])
                json.loads(json.dumps(result, ensure_ascii=False))

    def test_designations_remain_informational_and_slurs_remain_review_candidates(self):
        for key, doc in DOCUMENTS.items():
            f = self.find(doc['text'], TARGETS[key])[0]
            self.assertEqual(f['status'], 'needs_review' if f['rule_id'] in SLURS else 'context_only')
            self.assertEqual(bool(f['evidence'][0]['context'].get('informational_notice')), f['rule_id'] not in SLURS)

    def test_quotes_and_teaching_language_preserve_who_is_speaking(self):
        for key, doc in DOCUMENTS.items():
            rule = TARGETS[key]
            quoted = self.find('Редактор заявил: «' + doc['text'] + '»', rule)[0]
            self.assertTrue(quoted['evidence'][0]['context']['in_quotes'])
            self.assertEqual(quoted['status'], 'quoted_candidate' if rule in SLURS else 'context_only')
            discussed = self.find('Фраза «' + doc['text'] + '»', rule)[0]
            self.assertEqual(discussed['status'], 'context_only')

    def test_case_variants_and_cyrillic_yo_in_partners(self):
        for phrase in ('западные партнеры', 'ЗАПАДНЫЕ ПАРТНЁРЫ', 'с западными партнёрами',
                       'о западных партнерах', 'западному партнёру'):
            self.assertTrue(self.find(phrase + ' обсуждали переговоры.', 'terminology.western_partners'))
        for phrase in ('Коллективный Запад', 'коллективного запада', 'КОЛЛЕКТИВНЫМ ЗАПАДОМ', 'о коллективном Западе'):
            self.assertTrue(self.find(phrase + ' говорится в публикации.', 'terminology.collective_west'))

    def test_collective_west_does_not_create_a_second_bare_west_notice(self):
        result = analyze(DOCUMENTS['collective_west'])
        self.assertEqual([f['rule_id'] for f in result['findings']], ['terminology.collective_west'])
        self.assertEqual(result['summary']['marker_fragments'], 1)

    def test_declensions_and_gendered_role_forms(self):
        forms = {
            'dysphemism.putinoid_group': ['путиноид', 'путиноида', 'путиноиды', 'путиноидов', 'путиноидами', 'путиноидка', 'путиноидок'],
            'dysphemism.vatnik_group': ['ватник', 'ватника', 'ватники', 'ватников', 'ватниками', 'ватница', 'ватниц'],
            'terminology.occupier_actor': ['оккупант', 'оккупанта', 'оккупанты', 'оккупантов', 'оккупантами', 'оккупантки', 'оккупанток'],
            'terminology.liberator_actor': ['освободитель', 'освободителя', 'освободители', 'освободителей', 'освободителями', 'освободительница', 'освободительниц'],
            'terminology.propagandist_actor': ['пропагандист', 'пропагандиста', 'пропагандисты', 'пропагандистов', 'пропагандистами', 'пропагандистка', 'пропагандисток'],
        }
        for rule, variants in forms.items():
            for word in variants:
                self.assertTrue(self.find('В политической дискуссии прозвучало: ' + word + '.', rule), (rule, word))

    def test_label_attribution_and_direct_address_do_not_require_a_named_politician(self):
        for text in ('Пользователей назвали ватниками.', 'Ты — ватник.', 'Вы ватники.',
                     'Эти ватники считают иначе.'):
            self.assertTrue(self.find(text, 'dysphemism.vatnik_group'), text)

    def test_literal_clothing_is_excluded_even_with_a_political_title(self):
        controls = ['Рабочим выдали ватники.', 'На фабрике шьют новые ватники.',
                    'Он купил ватник.', 'Президент надел ватник.',
                    'У ватника оторвался рукав.', 'В магазине продают ватники.',
                    'Одежда на складе: ватники и куртки.']
        for text in controls:
            result = analyze({'title': 'Заявление президента', 'text': text})
            self.assertNotIn('dysphemism.vatnik_group', {f['rule_id'] for f in result['findings']}, text)

    def test_geographic_direction_regions_weather_and_titles_are_not_political_west(self):
        for text in ('Президент поехал на запад.', 'Поезд направился на запад России.',
                     'Президент посмотрел на Запад.', 'Поезд поехал на дальний запад.',
                     'Солнце садится на западе.', 'Ветер дует с запада.',
                     'Президент посетил запад Ленинградской области.',
                     'Президент направился на северо-запад.', 'Президент направился на юго‑запад.',
                     'Запад области получит новый прогноз погоды.',
                     'В книге «Запад» рассказано о путешествии.'):
            self.assertFalse(self.find(text, 'terminology.geopolitical_west'), text)

    def test_geopolitical_cases_object_position_and_indirect_roles(self):
        for text in ('На Западе считают санкции необходимыми.', 'Россия ведёт переговоры с Западом.',
                     'Экономические отношения с Западом изменились.', 'Страны Запада обсудили проект.',
                     'Запад потребовал новых уступок.', 'Запад пытается сорвать планы.',
                     'Запад хочет поражения.', 'Запад — наш противник.', 'Журналист критикует Запад.'):
            self.assertTrue(self.find(text, 'terminology.geopolitical_west'), text)

    def test_actual_speakers_who_are_actors_are_not_confused_with_fiction_titles(self):
        self.assertTrue(self.find('Актёр назвал журналиста пропагандистом.', 'terminology.propagandist_actor'))
        for text in ('Фильм «Коллективный Запад» показали на фестивале.',
                     'В фильме «Коллективный Запад» показали заседание.',
                     'Книга «Пропагандист» поступила в продажу.', 'Бренд «Ватники» открыл магазин.',
                     'Фильм «Освободители» показали в кинотеатре.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_pets_software_and_health_promotion_are_not_conflict_or_media_roles(self):
        for text in ('Котов назвали оккупантами кухни.', 'Кот — освободитель дивана.',
                     'Освободитель памяти удаляет временные файлы.',
                     'Врач — пропагандист здорового образа жизни.', 'Он пропагандист науки.',
                     'Пропагандисты спорта выступили в школе.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_territory_adjectives_still_require_the_territory_not_a_prisoner_or_tax(self):
        for text, target in [('В оккупированных районах отключили электричество.', 'occupied'),
                             ('На освобождённых территориях открыли школы.', 'liberated'),
                             ('В освобожденных сёлах открыли школы.', 'liberated')]:
            self.assertTrue(self.find(text, 'terminology.' + target + '_territory'))
        for text in ('Освобождённых из плена солдат встретили родные.', 'Город освобождён от налогов.'):
            self.assertFalse([f for f in analyze({'text': text})['findings'] if f['category'] == 'territory_terminology'])

    def test_terrorist_regime_remains_detected_and_predicate_variants_are_added(self):
        for text in ('Террористический режим объявил решение.', 'О террористическом режиме сообщили в публикации.',
                     'Этот режим — террористический.', 'Этот режим является террористическим.',
                     'Террористские власти заявили о решении.'):
            self.assertTrue(self.find(text, 'enemy.criminal_regime'), text)
        for text in ('Введён режим контртеррористической операции.',
                     'Режим повышенной террористической опасности отменён.',
                     'Фильм «Террористический режим» показали на фестивале.'):
            self.assertFalse(self.find(text, 'enemy.criminal_regime'), text)

    def test_negation_is_preserved_for_a_slur_without_inventing_author_endorsement(self):
        for text, rule in [('Он не ватник.', 'dysphemism.vatnik_group'),
                           ('Он не путиноид.', 'dysphemism.putinoid_group')]:
            f = self.find(text, rule)[0]
            self.assertEqual(f['status'], 'context_only')
            self.assertTrue(f['evidence'][0]['context']['nearby_negation'])

    def test_no_substring_matches_in_unrelated_or_adjectival_words(self):
        for text in ('Западня закрылась.', 'Обсудили пропагандистские приёмы.', 'Освободительный клапан установлен.'):
            self.assertFalse({f['rule_id'] for f in analyze({'text': text})['findings']} & NEW_IDS, text)

    def test_source_url_and_time_do_not_change_vocabulary_decisions(self):
        for doc in DOCUMENTS.values():
            expected = analyze(doc)['findings']
            for source in ('RT', 'Медиазона', 'ИноСМИ', 'Неизвестное издание'):
                self.assertEqual(analyze({**doc, 'source': source, 'url': 'https://example.org/news',
                                          'published_at': '2026-10-28T12:00:00+03:00'})['findings'], expected)

    def test_repeated_notices_remain_within_the_existing_budget(self):
        result = analyze({'text': (DOCUMENTS['collective_west']['text'] + '\n') * 600})
        self.assertEqual(len(result['findings']), MAX_FINDINGS)
        self.assertTrue(result['summary']['findings_truncated'])


if __name__ == '__main__':
    unittest.main()
